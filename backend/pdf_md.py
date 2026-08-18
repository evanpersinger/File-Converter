r"""Convert PDF files to Markdown.

Strategy (per page, so mixed PDFs work):
    - Searchable pages -> pymupdf4llm.to_markdown() for real markdown
      (headings, lists, tables, code blocks).
    - Scanned/image pages -> rendered at 300 DPI and read with tesseract OCR.
Pages are stitched back together in original order.

Math notation is normalized afterwards:
    - LaTeX math (\( .. \), \[ .. \], $ .. $, $$ .. $$) is kept as real LaTeX,
      with delimiters normalized to markdown's $ / $$ so math viewers render it.
    - Loose notation in plain text (LaTeX commands like \alpha, ASCII operators
      like <=, super/subscripts like x^2) is converted to unicode.
Code spans/blocks are protected so identifiers aren't touched.

English only for the OCR path: TESSERACT_LANG is 'eng', so a scanned page in another
language comes back as whatever English words its shapes resemble rather than as an
error. Searchable pages are unaffected, their text is read directly.
"""

import os
import re
import shutil
from pathlib import Path

import fitz  # PyMuPDF
import pymupdf4llm
import pytesseract
from PIL import Image
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OCR_DPI = 300                      # 300 is the OCR sweet spot; 600 is 4x slower for little gain
TEXT_MIN_CHARS = 20                # a page with fewer real chars is treated as scanned -> OCR
TESSERACT_CONFIG = r"--oem 3 --psm 3"  # psm 3 = auto page layout, good for full pages
TESSERACT_LANG = "eng"
ENABLE_MATH = True                 # normalize math notation to unicode
EXTRACT_IMAGES = False             # if True, save embedded images and link them in the markdown

# Point pytesseract at the tesseract binary if it's on PATH.
# (Correct attribute is `tesseract_cmd`; the old code set `pytesseract_cmd`, a no-op.)
_tesseract_path = shutil.which("tesseract")
if _tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_path

script_dir = os.path.dirname(os.path.abspath(__file__))
input_folder = os.path.join(script_dir, "input")
output_folder = os.path.join(script_dir, "output")
image_folder = os.path.join(output_folder, "images")

# ---------------------------------------------------------------------------
# Math normalization
# ---------------------------------------------------------------------------
SUPERSCRIPT_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻",
    "=": "⁼", "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ",
}
SUBSCRIPT_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋",
    "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}

# Backslash-prefixed LaTeX commands are unambiguous, so replacing them is safe.
LATEX_SYMBOLS = {
    # lowercase greek
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ",
    r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
    r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    # uppercase greek
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ",
    r"\Psi": "Ψ", r"\Omega": "Ω",
    # operators / calculus / logic / set theory
    r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\oint": "∮",
    r"\partial": "∂", r"\nabla": "∇", r"\infty": "∞", r"\sqrt": "√",
    r"\pm": "±", r"\mp": "∓", r"\times": "×", r"\div": "÷",
    r"\cdot": "·", r"\ast": "∗", r"\leq": "≤", r"\le": "≤",
    r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝", r"\sim": "∼",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆",
    r"\supset": "⊃", r"\supseteq": "⊇", r"\cup": "∪", r"\cap": "∩",
    r"\emptyset": "∅", r"\forall": "∀", r"\exists": "∃",
    r"\neg": "¬", r"\land": "∧", r"\lor": "∨",
    r"\rightarrow": "→", r"\to": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\leftrightarrow": "↔",
    r"\Leftrightarrow": "⇔", r"\mapsto": "↦",
    r"\degree": "°", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
}


def _map_chars(s, table, prefix):
    """Map every char in `s` via `table`; if any char is unmappable, keep the
    original `prefix + s` form so nothing is silently lost."""
    out = []
    for ch in s:
        if ch not in table:
            return prefix + s
        out.append(table[ch])
    return "".join(out)


def _to_superscript(s):
    return _map_chars(s, SUPERSCRIPT_MAP, "^")


def _to_subscript(s):
    return _map_chars(s, SUBSCRIPT_MAP, "_")


def _apply_math(text, ocr):
    # LaTeX commands (longest first so \varepsilon wins over \epsilon-ish prefixes)
    for cmd in sorted(LATEX_SYMBOLS, key=len, reverse=True):
        text = text.replace(cmd, LATEX_SYMBOLS[cmd])

    # ASCII operators
    text = text.replace("<=", "≤").replace(">=", "≥")
    text = text.replace("!=", "≠").replace("~=", "≈")
    text = text.replace("+/-", "±").replace("-/+", "∓")
    text = re.sub(r"(?<![<>=+\-])->", "→", text)   # arrow, but not part of --> etc.

    # sqrt: join a √ left dangling on its own line, then sqrt( / sqrt<space>
    text = re.sub(r"√\s*\n\s*", "√", text)
    text = re.sub(r"\bsqrt\s*\(", "√(", text)
    text = re.sub(r"\bsqrt\s+", "√", text)

    # explicit superscript: x^2, x^{10}, x^n, x^{-1}
    text = re.sub(
        r"([A-Za-z0-9\)\]])\^(\{[^}]+\}|-?\d+|[A-Za-z](?![A-Za-z]))",
        lambda m: m.group(1) + _to_superscript(m.group(2).strip("{}")),
        text,
    )
    # explicit subscript: x_1, x_i, x_{ij}  (multi-letter only via braces, so snake_case is safe)
    text = re.sub(
        r"([A-Za-z0-9\)\]])_(\{[^}]+\}|-?\d+|[A-Za-z](?![A-Za-z]))",
        lambda m: m.group(1) + _to_subscript(m.group(2).strip("{}")),
        text,
    )

    # em/en dashes commonly stand in for a minus sign
    text = text.replace("—", "-").replace("–", "-")

    if ocr:
        # A lone variable letter followed by a single digit at a token boundary
        # (x2 -> x²) but never inside a word (COVID19, GPT4 stay put).
        text = re.sub(
            r"(?<![A-Za-z0-9])([A-Za-z])(\d)(?![A-Za-z0-9])",
            lambda m: m.group(1) + _to_superscript(m.group(2)),
            text,
        )
        # tidy OCR whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def normalize_math(text, ocr=False):
    """Normalize math notation, leaving code spans and LaTeX math intact.

    Code spans/blocks are protected untouched. LaTeX math delimiters are
    normalized to markdown's `$..$` / `$$..$$` (\\( \\) -> $ $, \\[ \\] -> $$ $$)
    and their LaTeX contents preserved so a math-aware viewer renders them.
    Any remaining loose notation in plain text is converted to unicode.
    """
    if not ENABLE_MATH or not text:
        return text

    protected = []

    def stash(s):
        protected.append(s)
        return f"\x00{len(protected) - 1}\x00"

    # 1. protect fenced code blocks, then inline code
    text = re.sub(r"```.*?```", lambda m: stash(m.group(0)), text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", lambda m: stash(m.group(0)), text)

    # 2. normalize LaTeX math delimiters to $ / $$ and protect their contents.
    #    \[ \] and \( \) are unambiguous; $$ .. $$ is display math. A single
    #    $ .. $ is only treated as math when it contains \, ^ or _, so that
    #    plain prices like "$5 and $10" are left alone.
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: stash(f"$${m.group(1).strip()}$$"), text, flags=re.S)
    text = re.sub(r"\\\((.+?)\\\)", lambda m: stash(f"${m.group(1).strip()}$"), text, flags=re.S)
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: stash(f"$${m.group(1).strip()}$$"), text, flags=re.S)
    text = re.sub(
        r"\$(?!\$)([^$\n]*?[\\^_][^$\n]*?)\$",
        lambda m: stash(f"${m.group(1).strip()}$"),
        text,
    )

    # 3. convert remaining loose notation in plain text
    text = _apply_math(text, ocr)

    # 4. restore protected spans (loop in case a span nested another)
    for _ in range(5):
        if "\x00" not in text:
            break
        text = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------------------
# PDF -> markdown
# ---------------------------------------------------------------------------
def _ocr_page(page):
    """Render a page to an image and OCR it."""
    pix = page.get_pixmap(dpi=OCR_DPI)
    mode = "RGBA" if pix.alpha else "RGB"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        img = img.convert("RGB")
    return pytesseract.image_to_string(img, config=TESSERACT_CONFIG, lang=TESSERACT_LANG)


def pdf_to_markdown(pdf_path):
    """Convert a single PDF to a markdown string."""
    doc = fitz.open(pdf_path)
    if doc.is_encrypted:
        # try an empty password; skip if it's really locked
        if not doc.authenticate(""):
            doc.close()
            raise ValueError("PDF is password protected")

    n_pages = doc.page_count

    # Classify each page: enough embedded text -> searchable, else -> OCR.
    text_pages, ocr_pages = [], []
    for i in range(n_pages):
        if len(doc[i].get_text("text").strip()) >= TEXT_MIN_CHARS:
            text_pages.append(i)
        else:
            ocr_pages.append(i)

    md_by_page = {}

    # Searchable pages -> real markdown via pymupdf4llm
    if text_pages:
        md_kwargs = dict(pages=text_pages, page_chunks=True, show_progress=False)
        if EXTRACT_IMAGES:
            os.makedirs(image_folder, exist_ok=True)
            md_kwargs.update(write_images=True, image_path=image_folder, image_format="png")
        chunks = pymupdf4llm.to_markdown(doc, **md_kwargs)
        for page_no, chunk in zip(text_pages, chunks):
            md_by_page[page_no] = normalize_math(chunk["text"].strip(), ocr=False)

    # Scanned/image pages -> OCR
    if ocr_pages:
        for i in tqdm(ocr_pages, desc=f"OCR {Path(pdf_path).name}", unit="page", leave=False):
            raw = _ocr_page(doc[i])
            md_by_page[i] = normalize_math(raw.strip(), ocr=True)

    doc.close()

    kind = "searchable" if not ocr_pages else ("scanned" if not text_pages else "mixed")
    print(f"  {n_pages} page(s): {len(text_pages)} searchable, {len(ocr_pages)} OCR ({kind})")

    parts = [md_by_page.get(i, "") for i in range(n_pages)]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def convert_pdf_to_markdown() -> str:
    """Convert every PDF in the input folder to Markdown in the output folder.

    Searchable pages become real Markdown; scanned pages fall back to OCR, handled
    page by page so mixed PDFs work. This runs locally and is free, unlike the
    OpenAI Vision version in openai_pdf_md.py.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    os.makedirs(output_folder, exist_ok=True)

    entries = os.listdir(input_folder) if os.path.isdir(input_folder) else []
    pdf_files = sorted(f for f in entries if f.lower().endswith(".pdf"))

    print(f"Looking for PDF files in: {input_folder}")

    if not pdf_files:
        if any(f.lower().endswith(".md") for f in entries):
            return "That file is already in md format"
        return "No PDF files found in input folder"

    print(f"Found {len(pdf_files)} PDF file(s)")

    converted = []
    errors = []

    for filename in pdf_files:
        pdf_path = os.path.join(input_folder, filename)
        md_filename = os.path.splitext(filename)[0] + ".md"
        md_path = os.path.join(output_folder, md_filename)
        print(f"Processing {filename}...")
        try:
            markdown = pdf_to_markdown(pdf_path)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"  Converted {filename} -> {md_filename}")
            converted.append(md_filename)
        except Exception as e:
            print(f"  Error converting {filename}: {e}")
            errors.append(f"{filename}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


def main():
    print(convert_pdf_to_markdown())


if __name__ == "__main__":
    main()
