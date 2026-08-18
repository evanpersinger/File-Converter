"""Tests for the text-processing side of ss_txt.py.

Tesseract itself is not under test, and the OCR passes need a real screenshot to be
meaningful. Everything that runs on the text once it comes back out is pure, though,
and that is where the guessing happens: rejoining split lines and correcting the
characters OCR habitually gets wrong.
"""

from pathlib import Path

import pytest

from ss_txt import (
    IMAGE_EXTENSIONS,
    are_texts_similar,
    clean_text,
    fix_common_ocr_errors,
    find_images,
    join_continuation_lines,
)


# Rejoining lines OCR split


def test_a_line_starting_lowercase_joins_the_one_above() -> None:
    """OCR breaks a wrapped sentence at the visual line end, not the sentence end."""
    assert join_continuation_lines(["The quick", "brown fox"]) == ["The quick brown fox"]


def test_a_line_starting_uppercase_stays_separate() -> None:
    assert join_continuation_lines(["First line", "Second line"]) == [
        "First line",
        "Second line",
    ]


def test_a_trailing_comma_pulls_in_the_next_line() -> None:
    assert join_continuation_lines(["one,", "two"]) == ["one, two"]


def test_a_blank_line_is_a_hard_boundary() -> None:
    """A blank line is a paragraph break, so a lowercase start after it is a new
    paragraph rather than a continuation."""
    assert join_continuation_lines(["one", "", "two"]) == ["one", "", "two"]


def test_a_table_line_is_a_hard_boundary_and_is_left_alone() -> None:
    lines = ["intro", "| a | b |", "| 1 | 2 |"]
    assert join_continuation_lines(lines) == lines


# Whitespace cleanup


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\n\n\n\n\nb", "a\n\nb"),
        ("a     b", "a b"),
        # Uppercase, so join_continuation_lines leaves the break in place and the
        # leading-space rule is what is actually being exercised.
        ("a\n    B", "a\nB"),
        # Lowercase instead, and the line is treated as a continuation and joined.
        ("a\n    b", "a b"),
        ("   padded   ", "padded"),
        ("", ""),
    ],
)
def test_whitespace_is_normalized(source: str, expected: str) -> None:
    assert clean_text(source) == expected


# Deduping repeated OCR passes


def test_identical_text_is_similar() -> None:
    """Several preprocessing passes run over the same image, so near-duplicate results
    have to be recognised before the best one is picked."""
    assert are_texts_similar("hello world", "hello world") is True


def test_case_and_spacing_do_not_make_text_different() -> None:
    assert are_texts_similar("Hello   World", "hello world") is True


def test_unrelated_text_is_not_similar() -> None:
    assert are_texts_similar("alpha beta gamma", "nothing whatsoever here") is False


@pytest.mark.parametrize(("a", "b"), [("", "x"), ("x", ""), ("", "")])
def test_empty_text_is_never_similar(a: str, b: str) -> None:
    assert are_texts_similar(a, b) is False


# Correcting characters OCR gets wrong


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("©2", "2"),
        # In context, since on a line of its own the lone ')' left behind is then
        # dropped as an artifact.
        ("x ©) y", "x ) y"),
        ("Os6", "6"),
        ("l0", "0"),
        ("l7", "7"),
        ("O5", "5"),
        ("I0", "10"),
        ("I1", "11"),
    ],
)
def test_misread_characters_are_corrected(source: str, expected: str) -> None:
    """The digit zero, capital O and lowercase l are near-identical in most screenshot
    fonts, and MCQ bubbles come back as ©."""
    assert fix_common_ocr_errors(source) == expected


def test_a_stray_single_character_line_is_dropped() -> None:
    """A lone punctuation mark on its own line is an artifact, but a lone digit or
    letter could be real content."""
    assert fix_common_ocr_errors("real line\n.\n7") == "real line\n7"


def test_empty_input_is_returned_unchanged() -> None:
    assert fix_common_ocr_errors("") == ""


@pytest.mark.parametrize(
    "sentence",
    [
        "Meet me at the door",
        "it is fine",
        "say hi to him",
    ],
)
def test_ordinary_words_are_not_corrupted(sentence: str) -> None:
    """The two-character rules match any short word, so left on they turn 'at' into
    'a1', 'it' into 'i1' and 'hi' into 'h1'. They are cell-only for that reason."""
    assert fix_common_ocr_errors(sentence) == sentence


@pytest.mark.parametrize(
    ("source", "expected"),
    [("at", "a1"), ("bi", "b1"), ("cl", "c1"), ("bt", "b1")],
)
def test_two_character_cell_labels_are_still_corrected(source: str, expected: str) -> None:
    """Opting in restores the corrections. In a table cell the trailing character
    really is a misread 1, which is why the rules exist at all."""
    assert fix_common_ocr_errors(source, table_cells=True) == expected


def test_the_cell_rules_are_off_unless_asked_for() -> None:
    """Default off, so a caller that has not thought about it gets the safe behaviour."""
    assert fix_common_ocr_errors("at") == "at"
    assert fix_common_ocr_errors("at", table_cells=True) == "a1"


# Finding the input


def test_images_are_found_by_extension(tmp_path: Path) -> None:
    for name in ("a.png", "b.JPG", "c.tiff", "notes.txt", "data.csv"):
        (tmp_path / name).touch()

    assert find_images(tmp_path) == ["a.png", "b.JPG", "c.tiff"]


def test_the_supported_extensions_are_all_lowercase_and_dotted() -> None:
    for ext in IMAGE_EXTENSIONS:
        assert ext.startswith(".")
        assert ext == ext.lower()
