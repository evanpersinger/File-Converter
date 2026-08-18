"""Tests for the Markdown preprocessing in md_pdf.py.

Pandoc and xelatex are not under test, and neither is reachable from a unit test
anyway. What is testable is everything that runs before them: the unicode -> LaTeX
maps, the delimiter normalization, and the code-protection that has to survive all of
it. These are the inverse of pdf_md.py's, so the last section checks the pair lines up.
"""

import pytest

from md_pdf import (
    _is_ascii_diagram_line,
    clean_control_chars,
    convert_symbols,
    ensure_list_spacing,
    normalize_math_delimiters,
    wrap_ascii_diagrams,
)
from pdf_md import normalize_math


# Unicode -> LaTeX


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("α", r"$\alpha$"),
        ("Ω", r"$\Omega$"),
        ("∑", r"$\sum$"),
        ("∞", r"$\infty$"),
        ("∀", r"$\forall$"),
    ],
)
def test_greek_and_operators_become_latex_commands(source: str, expected: str) -> None:
    assert convert_symbols(source) == expected


@pytest.mark.parametrize("symbol", ["≤", "≥", "±", "≈"])
def test_some_symbols_stay_unicode_but_move_into_math_mode(symbol: str) -> None:
    """UNICODE_MATH_KEEP exists because these render better as the raw character than
    as a LaTeX command, but they still have to sit inside $..$ to render at all."""
    assert convert_symbols(symbol) == f"${symbol}$"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x²", r"$x^{2}$"),
        ("x⁻¹", r"$x^{-1}$"),
        ("xᵢ", r"$x_{i}$"),
        ("x₁₂", r"$x_{12}$"),
    ],
)
def test_unicode_scripts_become_latex_scripts(source: str, expected: str) -> None:
    assert convert_symbols(source) == expected


def test_a_greek_base_keeps_its_command_under_a_subscript() -> None:
    """The base is looked up in GREEK_TO_LATEX before the script is attached, so this
    must not come out as a literal theta character wrapped in math mode."""
    assert convert_symbols("θ₀") == r"$\theta_{0}$"


def test_a_barred_variable_becomes_a_bar_command() -> None:
    assert convert_symbols("x̄") == r"$\bar{x}$"


def test_adjacent_math_blocks_are_merged() -> None:
    """Converting symbols one at a time leaves a run of separate $..$ blocks, which
    xelatex sets with visible gaps. They get folded back into one."""
    assert convert_symbols("$a$ + $b$") == "$a + b$"


# Code protection


def test_inline_code_is_not_touched() -> None:
    assert convert_symbols("use `x_i` and `α` here") == "use `x_i` and `α` here"


def test_fenced_code_block_is_not_touched() -> None:
    source = "```\nα = x²\n```"
    assert convert_symbols(source) == source


# Delimiters


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\[x + y\]", "$$x + y$$"),
        (r"\(x + y\)", "$x + y$"),
    ],
)
def test_latex_delimiters_are_normalized_to_dollars(source: str, expected: str) -> None:
    """raw_tex does not reliably handle \\[..\\], so both forms are rewritten to the
    dollar syntax pandoc's tex_math_dollars actually reads."""
    assert normalize_math_delimiters(source) == expected


@pytest.mark.parametrize(("dash", "source"), [("—", "a — b"), ("–", "a – b")])
def test_em_and_en_dashes_are_flattened(dash: str, source: str) -> None:
    assert normalize_math_delimiters(source) == "a - b"


def test_space_after_an_opening_dollar_is_trimmed() -> None:
    """tex_math_dollars requires the opening $ to be followed by a non-space, or the
    block is not read as math at all."""
    assert normalize_math_delimiters(r"$ \alpha$") == r"$\alpha$"


# Control characters and list spacing


@pytest.mark.parametrize(("source", "expected"), [("a\x0bb", "a\nb"), ("a\x0cb", "a\nb")])
def test_vertical_whitespace_controls_become_newlines(source: str, expected: str) -> None:
    assert clean_control_chars(source) == expected


def test_other_control_characters_are_stripped() -> None:
    assert clean_control_chars("a\x07b\x1fc") == "abc"


def test_tabs_and_newlines_survive() -> None:
    assert clean_control_chars("a\tb\nc") == "a\tb\nc"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("text\n- item", "text\n\n- item"),
        ("text\n* item", "text\n\n* item"),
        ("text\n1. item", "text\n\n1. item"),
    ],
)
def test_a_blank_line_is_inserted_before_a_list(source: str, expected: str) -> None:
    """Without the blank line pandoc reads the list as a continuation of the paragraph."""
    assert ensure_list_spacing(source) == expected


def test_an_already_spaced_list_is_left_alone() -> None:
    source = "text\n\n- item"
    assert ensure_list_spacing(source) == source


# Round trip against pdf_md.py


@pytest.mark.parametrize(
    ("latex", "unicode_form", "back_to_latex"),
    [
        (r"\alpha", "α", r"$\alpha$"),
        (r"\Omega", "Ω", r"$\Omega$"),
        (r"\sum", "∑", r"$\sum$"),
        ("x^2", "x²", r"$x^{2}$"),
        ("x_i", "xᵢ", r"$x_{i}$"),
    ],
)
def test_the_two_directions_line_up(
    latex: str, unicode_form: str, back_to_latex: str
) -> None:
    """pdf_md maps LaTeX down to unicode and md_pdf maps it back up. A symbol added to
    one table without the other silently breaks a pdf -> md -> pdf round trip, and this
    is the test that catches it."""
    assert normalize_math(latex) == unicode_form
    assert convert_symbols(unicode_form) == back_to_latex


# ASCII diagrams


@pytest.mark.parametrize(
    "line",
    [
        "A --> B",
        "A <-- B",
        "|        |         |",
        "5        |         8",
        "1        6         3",
    ],
)
def test_diagram_lines_are_recognized(line: str) -> None:
    assert _is_ascii_diagram_line(line) is True


@pytest.mark.parametrize(
    "line",
    [
        "",
        "This is a sentence.",
        "1 2 3",
        "| a | b |",
        "|---|---|",
    ],
)
def test_prose_and_ordinary_table_rows_are_not_diagram_lines(line: str) -> None:
    """'1 2 3' is the near-miss worth pinning: it is digits and spaces, but the gaps
    are single spaces, so it is a sentence rather than positioned edge weights."""
    assert _is_ascii_diagram_line(line) is False


def test_a_diagram_block_is_wrapped_in_a_fence() -> None:
    """Unfenced, pandoc collapses the runs of spaces and the diagram falls apart."""
    assert wrap_ascii_diagrams("A --> B\nB --> C") == "```\nA --> B\nB --> C\n```"


def test_a_lone_diagram_line_is_left_alone() -> None:
    """One line is more likely a sentence containing an arrow than a diagram, so the
    block has to be at least two lines before it gets fenced."""
    assert wrap_ascii_diagrams("A --> B") == "A --> B"


def test_an_existing_code_fence_is_not_double_wrapped() -> None:
    source = "```\nA --> B\nB --> C\n```"
    assert wrap_ascii_diagrams(source) == source


def test_a_numeric_markdown_table_survives() -> None:
    """A table whose cells are all numbers looks exactly like a diagram to the
    heuristic: strip the pipes, spaces and digits and nothing is left. Wrapping its
    data rows in a fence splits the table away from its own header."""
    source = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    assert wrap_ascii_diagrams(source) == source


# Symbols outside the maps


@pytest.mark.parametrize("source", ["a ⨁ b", "ℵ", "a ⊗ b"])
def test_unmapped_symbols_pass_through_untouched(source: str) -> None:
    """Nothing in the maps matches these, and guessing a LaTeX command for them would
    be worse than leaving the character for the font to handle."""
    assert convert_symbols(source) == source


def test_an_uncommon_but_mapped_operator_still_converts() -> None:
    assert convert_symbols("⋈") == r"$\bowtie$"


def test_a_superscript_outside_the_map_is_left_alone() -> None:
    assert convert_symbols("xᵃ") == "xᵃ"


def test_a_partly_mappable_script_run_converts_only_the_mappable_part() -> None:
    """Note this is the opposite of pdf_md's rule, where _map_chars refuses to convert
    a run at all unless every character in it maps. Here the run is split."""
    assert convert_symbols("x²ᵃ") == r"$x^{2}$ᵃ"
