"""Tests for combine_files.py.

Three things are worth pinning here. The classification helpers, since every later
decision hangs off them. The rejection paths, because the module's own comment records
that mixing formats once wrote junk and reported success. And the alias table, which
the frontend keeps a hand-maintained copy of.
"""

import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

import combine_files
from combine_files import (
    SUFFIX_ALIASES,
    canonical_suffix,
    get_file_type,
    natural_sort_key,
)

SandboxSetupDirs = Callable[[ModuleType], tuple[Path, Path]]

APP_TSX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "App.tsx"


# Classification helpers


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.jpeg", ".jpg"),
        ("photo.JPEG", ".jpg"),
        ("scan.tif", ".tiff"),
        ("page.htm", ".html"),
        ("photo.png", ".png"),
        ("photo.PNG", ".png"),
        ("notes.txt", ".txt"),
    ],
)
def test_alternate_spellings_fold_onto_one_suffix(filename: str, expected: str) -> None:
    """IMG_1.jpg and IMG_2.jpeg are the same format, so combining them must not be
    rejected as a mix on a technicality."""
    assert canonical_suffix(Path(filename)) == expected


def test_files_sort_numerically_not_lexically() -> None:
    """Lexically Q10 sorts before Q2, which silently reorders a combined document."""
    names = [Path("Q1.txt"), Path("Q10.txt"), Path("Q2.txt")]
    assert [p.name for p in sorted(names, key=natural_sort_key)] == [
        "Q1.txt",
        "Q2.txt",
        "Q10.txt",
    ]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.jpg", "image"),
        ("a.jpeg", "image"),
        ("a.png", "image"),
        ("a.gif", "image"),
        ("a.bmp", "image"),
        ("a.tiff", "image"),
        ("a.webp", "image"),
        ("a.pdf", "pdf"),
        ("a.PDF", "pdf"),
        ("a.txt", "text"),
        ("a.md", "text"),
    ],
)
def test_file_type_is_detected_from_the_extension(filename: str, expected: str) -> None:
    assert get_file_type(Path(filename)) == expected


def test_an_svg_is_treated_as_text() -> None:
    """SVG is a picture but it is also XML, and it is not in the image list, so it
    falls to the text branch and gets concatenated rather than stacked."""
    assert get_file_type(Path("logo.svg")) == "text"


# The alias table the frontend duplicates


def test_the_frontend_alias_table_matches_this_one() -> None:
    """App.tsx keeps its own copy of this map to decide when the Combine button is
    enabled, kept in step by a comment and nothing else. If the two drift, the button
    lies about what the backend will accept."""
    if not APP_TSX.exists():
        pytest.skip("frontend/src/App.tsx not present")

    body = re.search(r"EXT_ALIASES[^{]*\{(.*?)\}", APP_TSX.read_text(), re.S)
    assert body is not None, "EXT_ALIASES not found in App.tsx"

    frontend = dict(re.findall(r"'([^']+)':\s*'([^']+)'", body.group(1)))
    assert frontend == SUFFIX_ALIASES


# Rejection paths


def test_an_empty_list_is_rejected(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    sandbox_setup_dirs(combine_files)
    assert combine_files.combine_files([]) is False


def test_a_missing_file_is_rejected(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    sandbox_setup_dirs(combine_files)
    assert combine_files.combine_files(["nope.txt"]) is False


def test_mixed_extensions_are_rejected(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    """The module's own comment records the old behaviour: a .pdf among .txt files
    landed in the text branch and its raw bytes went into the output as junk."""
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    (input_dir / "a.txt").write_text("alpha\n")
    (input_dir / "b.md").write_text("beta\n")

    assert combine_files.combine_files(["a.txt", "b.md"]) is False
    assert list(output_dir.iterdir()) == []


def test_hidden_files_are_skipped(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    input_dir, _ = sandbox_setup_dirs(combine_files)
    (input_dir / ".DS_Store").write_bytes(b"\x00\x01")

    assert combine_files.combine_files([".DS_Store"]) is False


# Combining


def test_two_spellings_of_one_format_are_accepted(
    sandbox_setup_dirs: SandboxSetupDirs,
) -> None:
    """This is the alias table doing its job end to end."""
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    Image.new("RGB", (8, 8), "red").save(input_dir / "one.jpg", "JPEG")
    Image.new("RGB", (8, 8), "blue").save(input_dir / "two.jpeg", "JPEG")

    assert combine_files.combine_files(["one.jpg", "two.jpeg"]) is True
    assert (output_dir / "combined.jpg").exists()


def test_images_are_stacked_vertically(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    Image.new("RGB", (8, 8), "red").save(input_dir / "one.png", "PNG")
    Image.new("RGB", (8, 8), "blue").save(input_dir / "two.png", "PNG")

    assert combine_files.combine_files(["one.png", "two.png"]) is True
    with Image.open(output_dir / "combined.png") as img:
        assert img.size == (8, 16)


def test_a_narrower_image_is_centred(sandbox_setup_dirs: SandboxSetupDirs) -> None:
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    Image.new("RGB", (4, 8), "red").save(input_dir / "one.png", "PNG")
    Image.new("RGB", (10, 8), "blue").save(input_dir / "two.png", "PNG")

    assert combine_files.combine_files(["one.png", "two.png"]) is True
    with Image.open(output_dir / "combined.png") as img:
        assert img.size == (10, 16)


def test_text_files_keep_the_order_they_were_passed(
    sandbox_setup_dirs: SandboxSetupDirs,
) -> None:
    """The list order is deliberately left alone rather than sorted, so the caller
    decides the merge order."""
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    (input_dir / "one.txt").write_text("alpha\n")
    (input_dir / "two.txt").write_text("beta\n")

    assert combine_files.combine_files(["two.txt", "one.txt"]) is True
    merged = (output_dir / "combined.txt").read_text()
    assert merged.index("beta") < merged.index("alpha")


def test_a_separator_names_each_file_after_the_first(
    sandbox_setup_dirs: SandboxSetupDirs,
) -> None:
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    (input_dir / "one.txt").write_text("alpha\n")
    (input_dir / "two.txt").write_text("beta\n")

    combine_files.combine_files(["one.txt", "two.txt"])
    merged = (output_dir / "combined.txt").read_text()

    assert merged.startswith("alpha")
    assert "File: two.txt" in merged
    assert "File: one.txt" not in merged


def test_an_input_prefix_on_the_path_is_tolerated(
    sandbox_setup_dirs: SandboxSetupDirs,
) -> None:
    """Callers pass names relative to the input folder, but 'input/a.txt' is an easy
    mistake to make and is stripped rather than treated as a missing file."""
    input_dir, output_dir = sandbox_setup_dirs(combine_files)
    (input_dir / "a.txt").write_text("alpha\n")
    (input_dir / "b.txt").write_text("beta\n")

    assert combine_files.combine_files(["input/a.txt", "input/b.txt"]) is True
    assert (output_dir / "combined.txt").exists()
