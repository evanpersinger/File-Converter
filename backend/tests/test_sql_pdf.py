"""Tests for sql_pdf.py.

The converter prints SQL as written, so the things to pin are that the source text
survives into the PDF unchanged (including the characters reportlab would otherwise
read as markup), that the folder loop only picks up .sql files, and the two failure
messages callers show verbatim.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from pypdf import PdfReader

import sql_pdf
from sql_pdf import convert_sql_files, create_pdf_from_sql

SandboxSetupDirs = Callable[[ModuleType], tuple[Path, Path]]


def pdf_text(path: Path) -> str:
    return "".join(page.extract_text() for page in PdfReader(path).pages)


def test_pdf_contains_title_and_source_as_written(tmp_path: Path) -> None:
    """`<`, `>` and `&` are ordinary SQL but markup to reportlab's Paragraph. They must
    reach the page as themselves, and nothing gets reformatted or highlighted."""
    sql = tmp_path / "query.sql"
    sql.write_text("SELECT a & b FROM t\nWHERE x < 1 AND y > 2;\n", encoding="utf-8")
    out = tmp_path / "query.pdf"

    assert create_pdf_from_sql(sql, out) is True

    text = pdf_text(out)
    assert "SQL File: query" in text
    assert "SELECT a & b FROM t" in text
    assert "WHERE x < 1 AND y > 2;" in text


def test_missing_source_returns_false_instead_of_raising(tmp_path: Path) -> None:
    assert create_pdf_from_sql(tmp_path / "nope.sql", tmp_path / "nope.pdf") is False


def test_folder_run_converts_only_sql_files(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    input_dir, output_dir = sandbox_setup_dirs(sql_pdf)
    (input_dir / "b.sql").write_text("SELECT 2;", encoding="utf-8")
    (input_dir / "a.sql").write_text("SELECT 1;", encoding="utf-8")
    (input_dir / "notes.txt").write_text("not sql", encoding="utf-8")

    summary = convert_sql_files()

    assert sorted(p.name for p in output_dir.iterdir()) == ["a.pdf", "b.pdf"]
    assert summary == "Converted 2 file(s) to output/: a.pdf, b.pdf"


def test_folder_run_with_no_sql_files_says_so(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    input_dir, output_dir = sandbox_setup_dirs(sql_pdf)
    (input_dir / "notes.txt").write_text("not sql", encoding="utf-8")

    assert convert_sql_files().startswith("No SQL files found")
    assert list(output_dir.iterdir()) == []
