"""server.py

Local web UI backend for the file converters. Upload one file, pick a target
format, get the converted file back.

The tricky part is isolation. The batch converters process *everything* in their
input folder, so if the real backend/input/ has leftover files, a web request that
uploaded one file would convert all of them. Instead of touching the real folders,
each request gets a scratch workspace under .webui_jobs/<uuid>/ and the converter
modules are temporarily pointed at it.

Every converter resolves its input/output directories in one of five ways, so there
are five ways to redirect it. See the `via_*` helpers below.

CONCURRENCY: redirection works by mutating module-level state, which is
process-global. Two conversions running at once would corrupt each other's paths.
_LOCK plus a single uvicorn worker is what makes this safe. If you ever add workers
or make the convert handler `async def` without holding the lock, this breaks
silently and confusingly.

Run it:
    uv run uvicorn server:app --app-dir backend --reload --port 8000 --loop asyncio

--loop asyncio is not optional if you want the OpenAI Vision conversion to work:
vision_parse calls nest_asyncio.apply(), which cannot patch uvloop (the loop
uvicorn[standard] picks by default). Every other conversion works either way.
"""

from __future__ import annotations

import io
import os
import shutil
import threading
import traceback
import zipfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Callable, Iterator
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

# Converter modules. Imported as plain top-level modules, which works because this
# file lives alongside them in backend/ and uvicorn is started with --app-dir backend.
import combine_files  # noqa: F401  (imported for the stray-import check only)
import csv_md
import csv_xlsx
import docx_pdf
import heic_jpg
import heic_md
import heic_png
import html_pdf
import ipynb_pdf
import jpg_md
import jpg_ocr
import jpg_pdf
import jpg_png
import md_pdf
import pdf_md
import pdf_png
import png_pdf
import pptx_md
import pptx_pdf
import R_Rmd
import Rmd_pdf
import sql_pdf
import ss_txt
import txt_pdf
import xlsx_csv

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
JOBS_ROOT = (REPO / ".webui_jobs").resolve()
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

# The .env lives at the repo root, one level up from this file.
load_dotenv(REPO / ".env")

# Serialises the process-global module patching. See the CONCURRENCY note above.
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Import sanity check
# ---------------------------------------------------------------------------
# This project is also installed as a wheel (with backend/ flattened to top level),
# so `import csv_md` can resolve to site-packages instead of backend/. If that
# happened, we would be patching a different copy of the module than the one doing
# the work, and conversions would silently write into site-packages. Fail loudly.
_CONVERTER_MODULES = [
    csv_md, csv_xlsx, docx_pdf, heic_jpg, heic_md, heic_png, html_pdf, ipynb_pdf,
    jpg_md, jpg_ocr, jpg_pdf, jpg_png, md_pdf, pdf_md, pdf_png, png_pdf, pptx_md,
    pptx_pdf, R_Rmd, Rmd_pdf, sql_pdf, ss_txt, txt_pdf, xlsx_csv, combine_files,
]
_stray = [m.__name__ for m in _CONVERTER_MODULES
          if Path(m.__file__).resolve().parent != BACKEND]
if _stray:
    raise RuntimeError(
        f"These converter modules were imported from outside {BACKEND}: {_stray}. "
        "Start the server with `uvicorn server:app --app-dir backend` so the local "
        "copies shadow the installed wheel."
    )


# ---------------------------------------------------------------------------
# Isolation primitives
# ---------------------------------------------------------------------------
@contextmanager
def job_workspace() -> Iterator[tuple[Path, Path, Path]]:
    """Yield a fresh (job_dir, input_dir, output_dir), deleted on exit no matter what.

    .resolve() matters: the __file__-patched converters call
    Path(__file__).resolve().parent, so the dirs have to already be resolved or the
    comparison mismatches (on macOS /tmp is a symlink to /private/tmp, which is also
    why the scratch dir lives inside the repo rather than the system temp dir).
    """
    job_dir = (JOBS_ROOT / uuid4().hex).resolve()
    job_in, job_out = job_dir / "input", job_dir / "output"
    job_in.mkdir(parents=True)
    job_out.mkdir(parents=True)
    try:
        yield job_dir, job_in, job_out
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


_MISSING = object()


@contextmanager
def patched(module, **attrs):
    """Temporarily set module attributes, restoring the originals unconditionally."""
    saved = {k: getattr(module, k, _MISSING) for k in attrs}
    try:
        for key, value in attrs.items():
            setattr(module, key, value)
        yield
    finally:
        for key, old in saved.items():
            if old is _MISSING:
                delattr(module, key)
            else:
                setattr(module, key, old)


# The five redirection mechanisms. Each returns an `invoke(job_in, job_out, staged)`.
# `call` receives the absolute path of the staged upload.

def via_globals(module, call: Callable):
    """Module has `input_folder` / `output_folder` string globals read at call time."""
    def invoke(job_dir: Path, job_in: Path, job_out: Path, staged: Path):
        with patched(module, input_folder=str(job_in), output_folder=str(job_out)):
            return call(staged)
    return invoke


def via_setup_dirs(module, call: Callable):
    """Module gets its dirs from a `setup_directories()` function (txt_pdf, sql_pdf)."""
    def invoke(job_dir: Path, job_in: Path, job_out: Path, staged: Path):
        with patched(module, setup_directories=lambda: (job_in, job_out)):
            return call(staged)
    return invoke


def via_file_attr(module, call: Callable):
    """Module computes `Path(__file__).resolve().parent / "input"` *inside* the
    function body, so the globals above don't exist to patch. Pointing __file__ at a
    fake path inside the job dir makes script_dir resolve to the job dir instead.

    Applies to html_pdf, ipynb_pdf and ss_txt.
    """
    def invoke(job_dir: Path, job_in: Path, job_out: Path, staged: Path):
        fake = job_dir / Path(module.__file__).name
        with patched(module, __file__=str(fake)):
            return call(staged)
    return invoke


def openai_pdf_invoke(job_dir: Path, job_in: Path, job_out: Path, staged: Path):
    """PDF -> Markdown via OpenAI Vision.

    openai_pdf_md is imported lazily, not at module scope, because vision_parse calls
    nest_asyncio.apply() at import time and that raises under uvloop (which
    uvicorn[standard] selects by default). Keeping it out of module scope means a bad
    event loop breaks only this one conversion instead of preventing the server from
    starting at all. Run with `--loop asyncio` for this conversion to work.
    """
    import openai_pdf_md

    with patched(openai_pdf_md, input_dir=job_in, output_dir=job_out):
        return openai_pdf_md.convert_pdf_to_markdown_openai()


def via_params(call: Callable):
    """Converter already accepts input_dir / output_dir arguments. No patching needed.

    Applies to docx_pdf, R_Rmd and Rmd_pdf.
    """
    def invoke(job_dir: Path, job_in: Path, job_out: Path, staged: Path):
        return call(staged, job_in, job_out)
    return invoke


# ---------------------------------------------------------------------------
# System dependency probes
# ---------------------------------------------------------------------------
_LIBREOFFICE_APP = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")

DEPS: dict[str, Callable[[], bool]] = {
    "tesseract": lambda: bool(which("tesseract")),
    "pandoc": lambda: bool(which("pandoc")),
    "latex": lambda: bool(which("xelatex") or which("pdflatex")),
    "libreoffice": lambda: bool(
        which("soffice") or which("libreoffice") or _LIBREOFFICE_APP.exists()
    ),
    "openai_key": lambda: bool(os.environ.get("OPENAI_API_KEY")),
}

DEP_LABELS = {
    "tesseract": ("Tesseract OCR is not installed", "brew install tesseract"),
    "pandoc": ("Pandoc is not installed", "brew install pandoc"),
    "latex": ("No LaTeX engine found", "brew install --cask mactex"),
    "libreoffice": ("LibreOffice is not installed", "brew install --cask libreoffice"),
    "openai_key": ("OPENAI_API_KEY is not set", "add OPENAI_API_KEY to the .env file"),
}


def missing_deps(requires: tuple[str, ...]) -> list[str]:
    return [dep for dep in requires if not DEPS[dep]()]


# ---------------------------------------------------------------------------
# Conversion registry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Conversion:
    source_exts: tuple[str, ...]
    target_id: str
    label: str
    target_ext: str
    invoke: Callable
    requires: tuple[str, ...] = ()
    note: str | None = None


IMAGE_ONLY_OCR = (".png", ".gif", ".bmp", ".tiff", ".webp")

REGISTRY: list[Conversion] = [
    # --- spreadsheets / data -------------------------------------------------
    Conversion((".csv",), "csv->md", "Markdown", ".md",
               via_globals(csv_md, lambda s: csv_md.convert_csv_to_markdown())),
    Conversion((".csv",), "csv->xlsx", "Excel", ".xlsx",
               via_globals(csv_xlsx, lambda s: csv_xlsx.convert_csv_to_xlsx())),
    Conversion((".xlsx",), "xlsx->csv", "CSV", ".csv",
               via_globals(xlsx_csv, lambda s: xlsx_csv.convert_xlsx_to_csv()),
               note="Multi-sheet workbooks convert the first sheet only."),

    # --- PDF -----------------------------------------------------------------
    Conversion((".pdf",), "pdf->md", "Markdown", ".md",
               via_globals(pdf_md, lambda s: pdf_md.convert_pdf_to_markdown()),
               requires=("tesseract",)),
    Conversion((".pdf",), "pdf->png", "PNG", ".png",
               via_globals(pdf_png, lambda s: pdf_png.convert_pdf_to_png()),
               note="One PNG per page. Multi-page PDFs come back as a zip."),
    Conversion((".pdf",), "pdf->md-ai", "Markdown (AI, costs money)", ".md",
               openai_pdf_invoke,
               requires=("openai_key",),
               note="Sends the PDF to OpenAI's Vision API. Slower, and it bills your key."),

    # --- office --------------------------------------------------------------
    Conversion((".pptx",), "pptx->md", "Markdown", ".md",
               via_globals(pptx_md, lambda s: pptx_md.convert_pptx_to_markdown())),
    Conversion((".pptx",), "pptx->pdf", "PDF", ".pdf",
               via_globals(pptx_pdf, lambda s: pptx_pdf.convert_pptx_to_pdf()),
               requires=("libreoffice",)),
    Conversion((".docx",), "docx->pdf", "PDF", ".pdf",
               via_params(lambda s, i, o: docx_pdf.convert_docx_to_pdf(
                   str(s), None, input_dir=str(i), output_dir=str(o)))),

    # --- images --------------------------------------------------------------
    Conversion((".heic",), "heic->jpg", "JPG", ".jpg",
               via_globals(heic_jpg, lambda s: heic_jpg.convert_heic_to_jpg())),
    Conversion((".heic",), "heic->png", "PNG", ".png",
               via_globals(heic_png, lambda s: heic_png.convert_heic_to_png())),
    Conversion((".heic",), "heic->md", "Markdown", ".md",
               via_globals(heic_md, lambda s: heic_md.convert_heic_to_markdown()),
               requires=("tesseract",)),
    Conversion((".jpg", ".jpeg"), "jpg->md", "Markdown", ".md",
               via_globals(jpg_md, lambda s: jpg_md.convert_jpg_to_markdown()),
               requires=("tesseract",)),
    Conversion((".jpg", ".jpeg"), "jpg->txt", "Text", ".txt",
               via_globals(jpg_ocr, lambda s: jpg_ocr.convert_jpg_to_ocr()),
               requires=("tesseract",)),
    Conversion((".jpg", ".jpeg"), "jpg->pdf", "PDF", ".pdf",
               via_globals(jpg_pdf, lambda s: jpg_pdf.convert_jpg_to_pdf())),
    Conversion((".jpg", ".jpeg"), "jpg->png", "PNG", ".png",
               via_globals(jpg_png, lambda s: jpg_png.convert_jpg_to_png())),
    Conversion((".png",), "png->pdf", "PDF", ".pdf",
               via_globals(png_pdf, lambda s: png_pdf.convert_png_to_pdf())),

    # ss_txt is the only OCR route for these formats (jpg/jpeg are served by jpg_ocr,
    # so registering ss_txt for them too would just be a duplicate "Text" option).
    Conversion(IMAGE_ONLY_OCR, "img->txt", "Text", ".txt",
               via_file_attr(ss_txt, lambda s: ss_txt.convert_screenshots_to_text()),
               requires=("tesseract",)),
    Conversion(IMAGE_ONLY_OCR, "img->txt-tables", "Text (tables/layout)", ".txt",
               via_file_attr(
                   ss_txt,
                   lambda s: ss_txt.convert_screenshots_to_text(structured=True)),
               requires=("tesseract",),
               note="Slower. Uses table detection, better for grids and columns."),

    # --- text / markup / code ------------------------------------------------
    Conversion((".md",), "md->pdf", "PDF", ".pdf",
               via_globals(md_pdf, lambda s: md_pdf.convert_md_to_pdf(str(s))),
               requires=("pandoc", "latex")),
    Conversion((".txt",), "txt->pdf", "PDF", ".pdf",
               via_setup_dirs(txt_pdf, lambda s: txt_pdf.convert_txt_to_pdf(str(s)))),
    Conversion((".html", ".htm"), "html->pdf", "PDF", ".pdf",
               via_file_attr(html_pdf,
                             lambda s: html_pdf.convert_html_to_pdf(str(s))),
               requires=("pandoc", "latex"),
               note=(None if which("wkhtmltopdf") else
                     "wkhtmltopdf is not installed, so this falls back to Pandoc and "
                     "CSS/layout will not be preserved. brew install wkhtmltopdf")),
    Conversion((".sql",), "sql->pdf", "PDF", ".pdf",
               via_setup_dirs(sql_pdf, lambda s: sql_pdf.convert_sql_files())),
    Conversion((".ipynb",), "ipynb->pdf", "PDF", ".pdf",
               via_file_attr(
                   ipynb_pdf,
                   lambda s: ipynb_pdf.convert_notebook_to_pdf(str(s))),
               requires=("latex",)),

    # --- R -------------------------------------------------------------------
    Conversion((".r",), "r->rmd", "R Markdown", ".Rmd",
               via_params(lambda s, i, o: R_Rmd.convert_r_to_rmd(
                   str(s), None, input_dir=str(i), output_dir=str(o)))),
    Conversion((".rmd",), "rmd->pdf", "PDF", ".pdf",
               via_params(lambda s, i, o: Rmd_pdf.convert_rmd_to_pdf(
                   str(s), None, input_dir=str(i), output_dir=str(o))),
               requires=("pandoc",)),
]

# Deliberately NOT registered:
#   combine_files  - needs 2+ files, this UI uploads exactly one.
#   jpg -> pdf -> md and images -> combined image -> pdf -> md are the two known-bad
#     flows in the README. Both are *chains*; this UI does exactly one hop with no way
#     to feed an output back in, so they're unreachable by construction. Plain
#     jpg -> pdf stays available, since what's broken is using its output as OCR input.

BY_TARGET_ID = {c.target_id: c for c in REGISTRY}

# Every distinct output format, for the button grid in the UI. Derived from the
# registry, so a new converter with a new target extension gets a button for free.
ALL_FORMATS = [
    {"ext": ext, "name": ext.lstrip(".").upper()}
    for ext in sorted({c.target_ext for c in REGISTRY}, key=str.lower)
]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="File Converter")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/formats")
def formats() -> dict:
    """Source extension -> available targets, plus what's unavailable and why.

    Probed live rather than cached at import, so installing Tesseract and reloading
    the page is enough to make OCR targets appear.

    Both maps carry the target extension, since the UI groups conversions into one
    button per output format and needs it to know which button an entry belongs to.
    """
    by_extension: dict[str, list[dict]] = {}
    unavailable: dict[str, list[dict]] = {}

    for conv in REGISTRY:
        missing = missing_deps(conv.requires)
        for ext in conv.source_exts:
            if missing:
                reason, hint = DEP_LABELS[missing[0]]
                unavailable.setdefault(ext, []).append({
                    "id": conv.target_id,
                    "label": conv.label,
                    "ext": conv.target_ext,
                    "reason": reason,
                    "hint": hint,
                })
            else:
                entry = {"id": conv.target_id, "label": conv.label, "ext": conv.target_ext}
                if conv.note:
                    entry["note"] = conv.note
                by_extension.setdefault(ext, []).append(entry)

    return {
        "allFormats": ALL_FORMATS,
        "byExtension": by_extension,
        "unavailable": unavailable,
    }


def _error(message: str, hint: str | None = None, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message, "hint": hint}, status_code=status)


@app.post("/api/convert")
def convert(file: UploadFile = File(...), target: str = Form(...)):
    conv = BY_TARGET_ID.get(target)
    if conv is None:
        return _error(f"Unknown conversion '{target}'.")

    raw_name = Path(file.filename or "").name  # strips any directory components
    if not raw_name:
        return _error("No filename on the upload.")

    stem = Path(raw_name).stem
    ext = Path(raw_name).suffix.lower()

    if ext not in conv.source_exts:
        return _error(
            f"'{conv.label}' does not accept {ext or 'files with no extension'}.",
            f"It accepts: {', '.join(conv.source_exts)}",
        )

    missing = missing_deps(conv.requires)
    if missing:
        reason, hint = DEP_LABELS[missing[0]]
        return _error(f"Cannot run this conversion. {reason}.", hint)

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _error(f"File is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    if not data:
        return _error("The uploaded file is empty.")

    captured = io.StringIO()

    with _LOCK, job_workspace() as (job_dir, job_in, job_out):
        # Lowercase the extension on the way in. Most batch converters glob
        # lowercase-only patterns (png_pdf globs '*.png'), and APFS being
        # case-insensitive by default is a filesystem accident, not a guarantee.
        staged = job_in / f"{stem}{ext}"
        staged.write_bytes(data)

        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                result = conv.invoke(job_dir, job_in, job_out, staged)
        except Exception as exc:
            traceback.print_exc()
            return _error(
                f"{conv.label} conversion failed.",
                f"{exc!r}\n{_tail(captured.getvalue())}",
                status=500,
            )

        produced = sorted(p for p in job_out.rglob("*") if p.is_file())
        if not produced:
            # Batch converters return a diagnostic string; single-file ones return
            # False and print the real reason, which is why stdout is captured.
            detail = result if isinstance(result, str) else _tail(captured.getvalue())
            return _error(f"{conv.label} conversion produced no output.", detail or None)

        if len(produced) == 1:
            payload = produced[0].read_bytes()
            filename = f"{stem}{conv.target_ext}"
            media_type = "application/octet-stream"
        else:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in produced:
                    archive.write(path, path.relative_to(job_out))
            payload = buffer.getvalue()
            filename = f"{stem}.zip"
            media_type = "application/zip"

    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _tail(text: str, lines: int = 15) -> str:
    """Last few lines of captured converter output, for error messages."""
    kept = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(kept[-lines:])
