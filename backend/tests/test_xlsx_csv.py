"""Tests for xlsx_csv.py.

A workbook can hold things a CSV cannot: several sheets, formulas, formatting. What
this converter does when it meets them is the interesting part, since a CSV that comes
out looking fine is indistinguishable from one that quietly lost half the file.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

import xlsx_csv

Sandbox = Callable[[ModuleType], tuple[Path, Path]]


# Batch contract


def test_reports_when_input_is_empty(sandbox: Sandbox) -> None:
    sandbox(xlsx_csv)
    assert xlsx_csv.convert_xlsx_to_csv() == "No Excel files found in input folder"


def test_reports_when_the_file_is_already_a_csv(sandbox: Sandbox) -> None:
    input_dir, _ = sandbox(xlsx_csv)
    (input_dir / "data.csv").write_text("a\n1\n", encoding="utf-8")

    assert xlsx_csv.convert_xlsx_to_csv() == "That file is already in csv format"


def test_converts_a_single_workbook(sandbox: Sandbox) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(input_dir / "data.xlsx", index=False)

    summary = xlsx_csv.convert_xlsx_to_csv()

    assert "data.csv" in summary
    assert (output_dir / "data.csv").read_text(encoding="utf-8") == "a,b\n1,3\n2,4\n"


def test_converts_several_workbooks(sandbox: Sandbox) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"a": [1]}).to_excel(input_dir / "one.xlsx", index=False)
    pd.DataFrame({"b": [2]}).to_excel(input_dir / "two.xlsx", index=False)

    summary = xlsx_csv.convert_xlsx_to_csv()

    assert "Converted 2 file(s)" in summary
    assert sorted(p.name for p in output_dir.iterdir()) == ["one.csv", "two.csv"]


def test_a_file_that_is_not_a_workbook_is_reported_rather_than_raised(
    sandbox: Sandbox,
) -> None:
    input_dir, _ = sandbox(xlsx_csv)
    (input_dir / "broken.xlsx").write_bytes(b"this is not a workbook")

    summary = xlsx_csv.convert_xlsx_to_csv()

    assert summary.startswith("No files converted. 1 failed:")
    assert "broken.xlsx" in summary


def test_one_bad_file_does_not_stop_the_good_ones(sandbox: Sandbox) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"a": [1]}).to_excel(input_dir / "good.xlsx", index=False)
    (input_dir / "broken.xlsx").write_bytes(b"this is not a workbook")

    summary = xlsx_csv.convert_xlsx_to_csv()

    assert "good.csv" in summary
    assert "1 failed" in summary
    assert (output_dir / "good.csv").exists()


def test_the_row_index_is_not_written_as_a_column(sandbox: Sandbox) -> None:
    """index=False on both legs, otherwise every round trip grows an extra unnamed
    column on the left."""
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"a": [1, 2]}).to_excel(input_dir / "data.xlsx", index=False)

    xlsx_csv.convert_xlsx_to_csv()

    assert (output_dir / "data.csv").read_text(encoding="utf-8").splitlines()[0] == "a"


# What a CSV cannot hold


def test_every_sheet_reaches_the_output(sandbox: Sandbox) -> None:
    """pd.read_excel reads only the first sheet unless told otherwise. A three-sheet
    workbook converts with no error and no warning, and two thirds of the data is
    simply not in the output file."""
    input_dir, output_dir = sandbox(xlsx_csv)
    path = input_dir / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Second", index=False)
        pd.DataFrame({"c": [3]}).to_excel(writer, sheet_name="Third", index=False)

    xlsx_csv.convert_xlsx_to_csv()

    written = "".join(p.read_text(encoding="utf-8") for p in output_dir.iterdir())
    assert "a" in written
    assert "b" in written
    assert "c" in written


def test_unicode_survives(sandbox: Sandbox) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"word": ["café", "日本語"]}).to_excel(
        input_dir / "data.xlsx", index=False
    )

    xlsx_csv.convert_xlsx_to_csv()

    text = (output_dir / "data.csv").read_text(encoding="utf-8")
    assert "café" in text
    assert "日本語" in text


def test_each_sheet_gets_its_own_named_file(sandbox: Sandbox) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    path = input_dir / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Second", index=False)

    summary = xlsx_csv.convert_xlsx_to_csv()

    assert sorted(p.name for p in output_dir.iterdir()) == [
        "book_First.csv",
        "book_Second.csv",
    ]
    assert (output_dir / "book_First.csv").read_text(encoding="utf-8") == "a\n1\n"
    assert (output_dir / "book_Second.csv").read_text(encoding="utf-8") == "b\n2\n"
    assert "Converted 2 file(s)" in summary


def test_a_single_sheet_workbook_keeps_the_plain_name(sandbox: Sandbox) -> None:
    """Naming every output after its sheet would rename the common case to serve the
    rare one, so a one-sheet workbook still produces book.csv."""
    input_dir, output_dir = sandbox(xlsx_csv)
    pd.DataFrame({"a": [1]}).to_excel(input_dir / "book.xlsx", sheet_name="Only", index=False)

    xlsx_csv.convert_xlsx_to_csv()

    assert [p.name for p in output_dir.iterdir()] == ["book.csv"]


@pytest.mark.parametrize(
    ("sheet_name", "expected"),
    [
        ("Q1 Sales", "Q1 Sales"),
        ("2024/2025", "2024_2025"),
        (r"a\b", "a_b"),
        ("what?", "what_"),
        ("...", "sheet"),
    ],
)
def test_sheet_names_are_made_safe_for_a_filename(sheet_name: str, expected: str) -> None:
    """Excel allows characters in a tab name that would break the path or, with a
    slash, write the CSV somewhere other than the output folder entirely."""
    assert xlsx_csv._safe_name(sheet_name) == expected


def test_a_sheet_named_with_a_separator_stays_inside_the_output_folder(
    sandbox: Sandbox,
) -> None:
    input_dir, output_dir = sandbox(xlsx_csv)
    path = input_dir / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Q1", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="24-25", index=False)

    xlsx_csv.convert_xlsx_to_csv()

    assert all(p.parent == output_dir for p in output_dir.iterdir())
    assert len(list(output_dir.iterdir())) == 2
