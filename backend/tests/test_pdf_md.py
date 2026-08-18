"""Tests for the math and symbol normalization in pdf_md.py.

normalize_math() is the one piece of the PDF -> Markdown path that is pure text in,
text out, so it is testable without building a PDF fixture. The cases below are the
behaviours the module docstring promises: LaTeX commands become unicode, real LaTeX
math survives with only its delimiters normalized, and code spans are never touched.
"""

import pytest

from pdf_md import normalize_math


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\alpha + \beta", "α + β"),
        (r"\Sigma and \Omega", "Σ and Ω"),
        (r"\infty", "∞"),
        (r"\rightarrow", "→"),
        (r"\forall x \in S", "∀ x ∈ S"),
    ],
)
def test_latex_commands_become_unicode(source: str, expected: str) -> None:
    assert normalize_math(source) == expected


@pytest.mark.parametrize(("source", "expected"), [(r"\leq", "≤"), (r"\geq", "≥")])
def test_longest_latex_command_wins(source: str, expected: str) -> None:
    """\\leq must be matched whole. If the shorter \\le were substituted first the
    trailing q would be stranded as "≤q"."""
    assert normalize_math(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a <= b", "a ≤ b"),
        ("a >= b", "a ≥ b"),
        ("a != b", "a ≠ b"),
        ("a ~= b", "a ≈ b"),
        ("+/-", "±"),
        ("-/+", "∓"),
        ("a -> b", "a → b"),
    ],
)
def test_ascii_operators_become_unicode(source: str, expected: str) -> None:
    assert normalize_math(source) == expected


def test_long_dash_is_not_read_as_an_arrow() -> None:
    """The arrow rule has a lookbehind so ASCII art like --> is left as typed."""
    assert normalize_math("a --> b") == "a --> b"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x^2", "x²"),
        ("x^{10}", "x¹⁰"),
        ("x^n", "xⁿ"),
        ("x^{-1}", "x⁻¹"),
        ("x_1", "x₁"),
        ("x_i", "xᵢ"),
        ("x_{ij}", "xᵢⱼ"),
    ],
)
def test_superscripts_and_subscripts_are_mapped(source: str, expected: str) -> None:
    assert normalize_math(source) == expected


def test_unmappable_script_falls_back_to_plain_form() -> None:
    """No unicode superscript exists for 'a' or 'b', so the whole run is left readable
    rather than half-converted."""
    assert normalize_math("x^{ab}") == "x^ab"


def test_snake_case_identifier_is_left_alone() -> None:
    """Multi-letter subscripts need braces precisely so ordinary identifiers survive."""
    assert normalize_math("snake_case") == "snake_case"


def test_inline_code_is_not_touched() -> None:
    assert normalize_math("use `x_i` here") == "use `x_i` here"


def test_fenced_code_block_is_not_touched() -> None:
    source = "```\nx^2 and \\alpha\n```"
    assert normalize_math(source) == source


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\(x^2\)", "$x^2$"),
        (r"\[E = mc^2\]", "$$E = mc^2$$"),
        ("$$a^2 + b^2$$", "$$a^2 + b^2$$"),
    ],
)
def test_latex_math_keeps_its_contents_and_normalizes_delimiters(
    source: str, expected: str
) -> None:
    """Inside math the LaTeX is left as LaTeX for a math-aware viewer to render, so
    x^2 must NOT come back as x²."""
    assert normalize_math(source) == expected


def test_currency_is_not_treated_as_math() -> None:
    """A single $..$ only counts as math when it contains \\, ^ or _."""
    assert normalize_math("costs $5 and $10 total") == "costs $5 and $10 total"


@pytest.mark.parametrize(("source", "expected"), [("x2", "x²"), ("n2", "n²")])
def test_ocr_mode_promotes_a_lone_trailing_digit(source: str, expected: str) -> None:
    assert normalize_math(source, ocr=True) == expected
    assert normalize_math(source, ocr=False) == source


@pytest.mark.parametrize("source", ["COVID19", "GPT4"])
def test_ocr_mode_leaves_digits_inside_words(source: str) -> None:
    assert normalize_math(source, ocr=True) == source


@pytest.mark.parametrize("source", ["", None])
def test_falsy_input_is_returned_unchanged(source: str | None) -> None:
    assert normalize_math(source) == source


def test_normalization_is_idempotent() -> None:
    """Re-running over already-converted text must not double-convert, since a
    document can pass through this path more than once."""
    source = r"\alpha x^2 <= \beta and `x_i` stays"
    once = normalize_math(source)
    assert normalize_math(once) == once
