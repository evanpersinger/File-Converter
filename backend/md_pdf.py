"""Convert Markdown files to PDF using pandoc (xelatex engine).

For each .md in input/ (or a file passed as an argument), the markdown is
preprocessed and then rendered to a PDF in output/.

Preprocessing (mirrors the inverse of pdf_md.py):
    - Normalize math delimiters: \\[ .. \\] -> $$ .. $$, \\( .. \\) -> $ .. $,
      and fix escaped/space-padded $ so pandoc's tex_math_dollars sees clean math.
    - Convert unicode math back to LaTeX so xelatex renders it: greek letters,
      operators/relations/arrows/set-theory, unicode super/subscripts (x², xᵢ),
      and bar variables (x̄ -> \\bar{x}). Code spans/blocks are protected first.
    - Tables: normalize pipe spacing, protect against mid-table page breaks,
      turn spanning header rows into centered captions, mbox negative numbers.
    - Wrap ASCII-art / graph diagrams in code fences so their spacing survives.
Mermaid diagram blocks are rendered via mermaid-filter when it's installed.

Robustness: the full-fidelity render is attempted first. If xelatex chokes on
the input (e.g. an undefined LaTeX command like a mistyped \\gama), we fall back
to a safe render with math/raw-LaTeX disabled so you still get a PDF, and report
the command that likely broke it.
"""

import os
import re
import sys
import subprocess
import tempfile
import traceback
from pathlib import Path
from shutil import which

# Config: paths (absolute, based on this script's location so it runs anywhere)
script_dir = os.path.dirname(os.path.abspath(__file__))
input_folder = os.path.join(script_dir, "input")
output_folder = os.path.join(script_dir, "output")

# Config: pandoc reader extensions
# Full fidelity: math, pipe tables, raw HTML and raw LaTeX (for our injected \...)
PANDOC_FROM = "markdown+tex_math_dollars+pipe_tables+raw_html+raw_tex"
# Safe fallback: math + raw TeX OFF, so undefined commands render as literal text
# instead of aborting the whole document.
PANDOC_FROM_SAFE = (
    "markdown+pipe_tables+raw_html"
    "-tex_math_dollars-tex_math_single_backslash-raw_tex-latex_macros"
)

# Config: unicode -> LaTeX maps (reverse of pdf_md.py, so pdf->md->pdf round-trips)
SUPERSCRIPT_TO_LATEX = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
    "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-",
    "⁼": "=", "⁽": "(", "⁾": ")", "ⁿ": "n", "ⁱ": "i",
}
SUBSCRIPT_TO_LATEX = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
    "₆": "6", "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-",
    "₌": "=", "₍": "(", "₎": ")",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j", "ₖ": "k",
    "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o", "ₚ": "p", "ᵣ": "r",
    "ₛ": "s", "ₜ": "t", "ᵤ": "u", "ᵥ": "v", "ₓ": "x",
}

# Greek letters that have a real LaTeX command (used both for standalone
# conversion and as the base of a sub/superscript, e.g. θ₀ -> $\theta_{0}$).
GREEK_TO_LATEX = {
    # lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    # uppercase (only those with a dedicated command; the rest look like Latin)
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi",
    "Ψ": r"\Psi", "Ω": r"\Omega",
}

# Operators / relations / arrows / set theory that don't render reliably as raw
# unicode under xelatex, so we wrap them in a LaTeX command inside math mode.
OPERATOR_TO_LATEX = {
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∮": r"\oint",
    "∂": r"\partial", "∇": r"\nabla", "∞": r"\infty", "√": r"\surd",
    "∓": r"\mp", "×": r"\times", "÷": r"\div", "·": r"\cdot", "∗": r"\ast",
    "≠": r"\neq", "≡": r"\equiv", "∝": r"\propto", "∼": r"\sim",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "⊃": r"\supset", "⊇": r"\supseteq", "∪": r"\cup", "∩": r"\cap",
    "∅": r"\emptyset", "∀": r"\forall", "∃": r"\exists",
    "¬": r"\neg", "∧": r"\land", "∨": r"\lor",
    "→": r"\rightarrow", "←": r"\leftarrow", "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow", "↔": r"\leftrightarrow", "⇔": r"\Leftrightarrow",
    "↦": r"\mapsto", "∠": r"\angle", "⊥": r"\perp", "∥": r"\parallel",
    "⋈": r"\bowtie",
}

# Everything we turn into a $\command$: greek + operators, in one pass.
SYMBOL_TO_LATEX = {**GREEK_TO_LATEX, **OPERATOR_TO_LATEX}

# These render better as unicode kept inside math mode than as a LaTeX command.
UNICODE_MATH_KEEP = ["≤", "≥", "±", "≈"]

# Precomposed barred variables (the combining-macron form is handled by regex).
BAR_VARIABLES = {
    "x̄": r"$\\bar{x}$", "ȳ": r"$\\bar{y}$", "z̄": r"$\\bar{z}$",
    "X̄": r"$\\bar{X}$", "Ȳ": r"$\\bar{Y}$", "Z̄": r"$\\bar{Z}$",
}

# Character classes reused across the script regexes.
_GREEK_CLASS = "α-ωΑ-Ωθε"
_SCRIPT_BASE = r"A-Za-z0-9" + _GREEK_CLASS + r"\)\]"

# Config: LaTeX preamble injected into every render
LATEX_HEADER = """\\usepackage{amsmath}
\\usepackage{amssymb}
\\usepackage{fontspec}
% Ensure horizontal rules render properly
\\usepackage{booktabs}
\\usepackage{array}
% Better table column alignment
\\usepackage{tabularx}
% Prevent line breaks in table cells with math
\\usepackage{makecell}
% Auto-adjust column widths to prevent wrapping
\\usepackage{adjustbox}
% Better column alignment - left align first column, center others
\\newcolumntype{L}{>{\\raggedright\\arraybackslash}X}
\\newcolumntype{C}{>{\\centering\\arraybackslash}X}
\\usepackage{colortbl}
% Prevent page breaks within tables - keep tables together
\\usepackage{float}
% Configure table placement to avoid page breaks (H = here, don't float)
\\floatplacement{table}{H}
% Set table column width handling - reduce spacing for better alignment
\\setlength{\\tabcolsep}{4pt}
\\renewcommand{\\arraystretch}{1.2}
% Make tables fit content width better
\\setlength{\\extrarowheight}{0pt}
% Make tables auto-size to content instead of stretching to full width
\\renewcommand{\\tabularxcolumn}[1]{m{#1}}
% Prevent page breaks within tables - keep entire tables on one page
\\usepackage{etoolbox}
% Prevent page breaks within tables, but allow normal flow after table
% Only prevents splitting within the table itself, not after it
\\preto\\table{\\nopagebreak[4]}
\\appto\\endtable{\\nopagebreak[4]}
% Prevent breaks in tabular environments - strong penalties to prevent splitting within table
\\preto\\tabular{\\nopagebreak[4]\\penalty10000\\begingroup}
\\appto\\endtabular{\\endgroup\\penalty10000\\nopagebreak[4]}
% Additional protection using AtBeginEnvironment - only within table
\\AtBeginEnvironment{table}{\\nopagebreak[4]}
\\AtEndEnvironment{table}{\\nopagebreak[4]}
"""


# Preprocessing: control chars + math delimiters + list spacing
def clean_control_chars(md):
    """Turn vertical-tab/form-feed into newlines and strip other control chars."""
    md = md.replace("\x0b", "\n").replace("\x0c", "\n")
    return re.sub(r"[\x00-\x08\x0e-\x1f]", "", md)


def normalize_math_delimiters(md):
    """Normalize LaTeX math delimiters to $ / $$ and fix escaped/padded $.

    raw_tex doesn't always handle \\[..\\] correctly, so we convert to $$..$$.
    Pandoc's tex_math_dollars also requires the opening $ to be immediately
    followed by a non-space character, so leading spaces are trimmed.
    """
    # \[..\] -> $$..$$ and \(..\) -> $..$  (match pairs, allow newlines)
    md = re.sub(r"\\\[([\s\S]*?)\\\]", lambda m: f"$${m.group(1)}$$", md)
    md = re.sub(r"\\\(([\s\S]*?)\\\)", lambda m: f"${m.group(1).strip()}$", md)

    # Em/en dashes can break LaTeX rendering
    md = md.replace("—", "-").replace("–", "-")

    # \$..\$ pairs -> $..$ when the content is actually math (contains a backslash)
    def unescape_math_dollars(m):
        content = m.group(1)
        return f"${content.strip()}$" if "\\" in content else m.group(0)
    md = re.sub(r"\\\$((?:[^$])+?)\\\$", unescape_math_dollars, md)

    # Lone \$ used as an opening delimiter with no closing pair
    md = re.sub(r"\\\$(\s*\\[a-zA-Z])", r"$\1", md)         # \$ \command
    md = re.sub(r"\\\$(\s*[A-Za-z]\s*=\s*\\)", r"$\1", md)   # \$ var = \...
    md = re.sub(r"(?<=[a-zA-Z0-9}])\\\$", "$", md)           # trailing closing \$

    # Trim space right after an opening $ so math commands stay inside math mode
    md = re.sub(r"(?<!\$)\$ +(?=\\[a-zA-Z])", "$", md)                 # $ \command
    md = re.sub(r"(?<!\$)\$ +(?=[A-Za-z][^$\n]*(?:=|\\))", "$", md)     # $ var=
    return md


def ensure_list_spacing(md):
    """Add a blank line before lists so pandoc reliably recognizes them."""
    md = re.sub(r"([^\n])\n(- )", r"\1\n\n\2", md)
    md = re.sub(r"([^\n])\n(\* )", r"\1\n\n\2", md)
    md = re.sub(r"([^\n])\n(\d+\. )", r"\1\n\n\2", md)
    return md


# Preprocessing: ASCII-art / graph diagrams
def _is_ascii_diagram_line(ln):
    """Heuristic: does this line look like part of an ASCII graph/flow diagram?"""
    s = ln.rstrip()
    if not s:
        return False
    # Horizontal arrow patterns used in graph diagrams
    if re.search(r"--+>|<--+", s):
        return True
    # Lines composed entirely of structural characters (|, ^, v, digits, spaces)
    # e.g. "|        |         |"  or  "5        |         8"
    structural_only = re.sub(r"[\s|^v\d]", "", s)
    if structural_only == "" and ("|" in s or "^" in s):
        return True
    # Lines with only digits and spaces that use large gaps for positioning
    # e.g. "1        6         3" — numbers spread out as edge weights in a diagram
    if re.match(r"^[\d\s]+$", s) and re.search(r"\d\s{3,}\d", s):
        return True
    return False


# A markdown table separator row. At least one dash is required, otherwise a diagram
# column line like "|    |    |" matches this too and real diagrams stop being wrapped.
_TABLE_SEPARATOR = re.compile(r"^\s*\|[\s:|-]*-[\s:|-]*\|\s*$")


def wrap_ascii_diagrams(md):
    """Wrap contiguous ASCII-diagram blocks in code fences to preserve spacing."""
    lines = md.split("\n")
    wrapped_lines = []
    idx = 0
    in_fence = False
    in_table = False
    while idx < len(lines):
        line = lines[idx]
        # A separator row opens a table, a blank line closes it. A table row whose cells
        # are all numbers is indistinguishable from a diagram column line once the pipes,
        # spaces and digits are stripped, so the table has to be tracked across lines
        # rather than recognized from any one line on its own. Without this the data rows
        # of a numeric table get fenced off from their own header.
        if _TABLE_SEPARATOR.match(line):
            in_table = True
        elif not line.strip():
            in_table = False
        # Track existing code fences so we don't double-wrap them
        if line.strip().startswith("```"):
            in_fence = not in_fence
            wrapped_lines.append(line)
            idx += 1
            continue
        if not in_fence and not in_table and _is_ascii_diagram_line(line):
            # Collect the contiguous diagram block, allowing single blank lines
            # between diagram lines (so the whole graph stays together)
            block_start = idx
            j = idx
            while j < len(lines):
                if _is_ascii_diagram_line(lines[j]):
                    j += 1
                elif (not lines[j].strip()
                      and j + 1 < len(lines)
                      and _is_ascii_diagram_line(lines[j + 1])):
                    j += 1  # blank line bridging two diagram lines
                else:
                    break
            block = lines[block_start:j]
            if len(block) >= 2:
                wrapped_lines.append("```")
                wrapped_lines.extend(block)
                wrapped_lines.append("```")
                idx = j
                continue
        wrapped_lines.append(line)
        idx += 1
    return "\n".join(wrapped_lines)


# Preprocessing: tables
def _convert_paren_math_to_dollars(text):
    r"""Convert \(...\) to $...$ within a table cell, honoring nesting."""
    result = []
    i = 0
    while i < len(text):
        start = text.find("\\(", i)
        if start == -1:
            result.append(text[i:])
            break
        result.append(text[i:start])
        # Find matching \)
        depth = 0
        j = start + 2
        while j < len(text):
            if j < len(text) - 1 and text[j:j + 2] == "\\(":
                depth += 1
                j += 2
            elif j < len(text) - 1 and text[j:j + 2] == "\\)":
                if depth == 0:
                    math_inner = text[start + 2:j]
                    result.append(f"${math_inner}$")
                    i = j + 2
                    break
                else:
                    depth -= 1
                    j += 2
            else:
                j += 1
        else:
            result.append(text[start:])
            break
    return "".join(result)


def normalize_tables(md):
    """Normalize pipe-table spacing and guard tables against LaTeX breakage.

    Preserves the original behavior: consistent pipe spacing, page-break
    protection around tables, spanning header rows converted to centered
    captions, table-cell math combined, and negative numbers mbox-protected.
    """
    lines = md.split("\n")
    cleaned_lines = []

    prev_line_was_table = False
    in_table = False
    in_math_block = False   # inside a $$...$$ block
    in_code_block = False   # inside a ``` code fence

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Code fences: content inside ``` must pass through untouched
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            cleaned_lines.append(line)
            prev_line_was_table = False
            continue
        if in_code_block:
            cleaned_lines.append(line)
            prev_line_was_table = False
            continue

        # Math blocks: a lone $$ toggles state; skip table processing inside
        if stripped == "$$":
            in_math_block = not in_math_block
            cleaned_lines.append(line)
            prev_line_was_table = False
            continue
        if in_math_block:
            cleaned_lines.append(line)
            prev_line_was_table = False
            continue

        # Is this a table row?
        if stripped.startswith("|") and "|" in stripped[1:]:
            # Start of a new table: add page-break protection before it
            if not in_table and not prev_line_was_table:
                cleaned_lines.append("")
                cleaned_lines.append("\\nopagebreak[4]")
                cleaned_lines.append("")
                in_table = True

            is_separator = bool(re.match(r"^\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?\s*$", stripped))

            if is_separator:
                # Normalize separator row spacing
                parts = stripped.split("|")
                cells = []
                for part in parts[1:-1]:  # skip first/last empty parts
                    sep_content = re.sub(r"[^\-\:]", "", part)  # keep only - and :
                    if not sep_content:
                        sep_content = "---"
                    cells.append(sep_content)
                cleaned_lines.append("| " + " | ".join(cells) + " |")
                prev_line_was_table = True
            else:
                # Regular table row: normalize spacing, preserve cell content
                parts = stripped.split("|")
                cells = []
                for part in parts[1:-1]:  # skip first/last empty parts
                    cell_content = part.strip()
                    # Unescape dollar signs and convert \(...\) to $...$
                    cell_content = cell_content.replace("\\$", "$")
                    cell_content = _convert_paren_math_to_dollars(cell_content)
                    # Combine adjacent $...$ separated by a math operator into one block
                    # e.g. "$d_i$ = $y_i$ - $x_i$" -> "$d_i = y_i - x_i$"
                    while True:
                        combined = re.sub(
                            r"\$([^\$]+?)\$\s*([=+\-×÷≤≥≠≈±])\s*\$([^\$]+?)\$",
                            r"$\1 \2 \3$",
                            cell_content,
                        )
                        if combined == cell_content:
                            break
                        cell_content = combined
                    # Protect negative numbers from line breaks (outside math only)
                    parts_list = re.split(r"(\$[^\$]+\$)", cell_content)
                    protected_parts = []
                    for p in parts_list:
                        if p.startswith("$") and p.endswith("$"):
                            protected_parts.append(p)  # math, keep as-is
                        else:
                            protected_parts.append(re.sub(r"(-\d+)", r"\\mbox{\1}", p))
                    cell_content = "".join(protected_parts)
                    cells.append(cell_content)

                # Spanning header rows (fewer cells than the real table) break the
                # parser, so convert them to a centered caption above the table.
                if len(cells) <= 3 and i + 1 < len(lines):
                    next_stripped = lines[i + 1].strip()
                    if next_stripped.startswith("|") and "|" in next_stripped[1:]:
                        next_parts = next_stripped.split("|")
                        next_cells = [p.strip() for p in next_parts[1:-1]]
                        if len(next_cells) > len(cells) + 1:
                            header_parts = [c for c in cells if c.strip()]
                            if header_parts:
                                header_text = " ".join(header_parts)
                                escaped_header = header_text.replace("\\", "\\textbackslash{}")
                                escaped_header = escaped_header.replace("{", "\\{").replace("}", "\\}")
                                escaped_header = escaped_header.replace("&", "\\&").replace("%", "\\%")
                                escaped_header = escaped_header.replace("$", "\\$").replace("#", "\\#")
                                escaped_header = escaped_header.replace("^", "\\textasciicircum{}")
                                escaped_header = escaped_header.replace("_", "\\_").replace("~", "\\textasciitilde{}")
                                cleaned_lines.append(f"\\begin{{center}}\\textbf{{{escaped_header}}}\\end{{center}}")
                                cleaned_lines.append("")
                            prev_line_was_table = False
                            continue

                cleaned_lines.append("| " + " | ".join(cells) + " |")
                prev_line_was_table = True
        else:
            # Left a table: close the page-break protection
            if in_table and not stripped.startswith("|"):
                cleaned_lines.append("\\nopagebreak[4]")
                cleaned_lines.append("")
                in_table = False
            cleaned_lines.append(line)
            prev_line_was_table = False

    return "\n".join(cleaned_lines)


# Preprocessing: unicode math -> LaTeX (code spans/blocks protected)
def _convert_scripts(md):
    """Convert unicode super/subscript runs to LaTeX, e.g. x² -> $x^{2}$, xᵢ -> $x_{i}$."""
    sup = "".join(re.escape(c) for c in SUPERSCRIPT_TO_LATEX)
    sub = "".join(re.escape(c) for c in SUBSCRIPT_TO_LATEX)

    def sup_repl(m):
        base = GREEK_TO_LATEX.get(m.group(1), m.group(1))
        exp = "".join(SUPERSCRIPT_TO_LATEX[c] for c in m.group(2))
        return f"${base}^{{{exp}}}$"

    def sub_repl(m):
        base = GREEK_TO_LATEX.get(m.group(1), m.group(1))
        idx = "".join(SUBSCRIPT_TO_LATEX[c] for c in m.group(2))
        return f"${base}_{{{idx}}}$"

    md = re.sub(rf"(?<!\$)([{_SCRIPT_BASE}])((?:[{sup}])+)(?!\$)", sup_repl, md)
    md = re.sub(rf"(?<!\$)([{_SCRIPT_BASE}])((?:[{sub}])+)(?!\$)", sub_repl, md)
    return md


def _convert_underscores_in_math(math_content):
    """Turn variable_subscript patterns into proper LaTeX subscripts inside math."""
    # k_1x would be misparsed as k_{1x}; make the grouping explicit first
    math_content = re.sub(r"_(\d)([a-zA-Z])", r"_{\1}\2", math_content)

    def replace_subscript(m):
        base_var, subscript = m.group(1), m.group(2)
        latex_base = "".join(GREEK_TO_LATEX.get(ch, ch) for ch in base_var)
        if len(subscript) > 1:
            return f"{latex_base}_{{{subscript}}}"
        return f"{latex_base}_{subscript}"

    # variable (letters/greek) + underscore + subscript (letters/numbers),
    # skipping escaped underscores and table separators
    return re.sub(
        rf"([A-Za-z{_GREEK_CLASS}]+)(?<!\\\\)_([a-zA-Z0-9]+)(?![|])",
        replace_subscript,
        math_content,
    )


def _combine_adjacent_math(md):
    """Merge "$a$ op $b$" (op in + - =) into a single "$a op b$" block."""
    while True:
        combined = re.sub(r"\$([^$]+)\$\s*([+\-=])\s*\$([^$]+)\$", r"$\1 \2 \3$", md)
        if combined == md:
            break
        md = combined
    return md


def convert_symbols(md):
    """Convert unicode math notation to LaTeX so xelatex renders it.

    Code blocks and inline code are stashed first so identifiers/diagrams inside
    them are never rewritten, then restored at the end.
    """
    protected = []

    def stash(s):
        protected.append(s)
        return f"\x00{len(protected) - 1}\x00"

    md = re.sub(r"```.*?```", lambda m: stash(m.group(0)), md, flags=re.S)
    md = re.sub(r"`[^`\n]*`", lambda m: stash(m.group(0)), md)

    # Horizontal rules -> paragraph break (spacing)
    md = re.sub(r"^---\s*$", r"\n\n", md, flags=re.MULTILINE)

    # Barred variables: combining macron form, then precomposed characters
    md = re.sub(r"([a-zA-Z])̄", r"$\\bar{\1}$", md)
    for var, latex in BAR_VARIABLES.items():
        md = re.sub(r"(?<!\$)" + re.escape(var) + r"(?!\$)", latex, md)

    # Unicode super/subscripts -> LaTeX (θ₀ -> $\theta_{0}$, x² -> $x^{2}$)
    md = _convert_scripts(md)

    # Underscore subscripts inside existing math blocks
    md = re.sub(
        r"\$\$([^$]*(?:\\.[^$]*)*?)\$\$",
        lambda m: f"$${_convert_underscores_in_math(m.group(1))}$$",
        md,
    )
    md = re.sub(
        r"(?<!\$)\$([^$]+?)\$(?!\$)",
        lambda m: f"${_convert_underscores_in_math(m.group(1))}$",
        md,
    )

    # Greek + operators -> $\command$ (plain, and when butted against closing $)
    for sym, cmd in SYMBOL_TO_LATEX.items():
        md = re.sub(r"(?<!\$)" + re.escape(sym) + r"(?!\$)",
                    lambda m, c=cmd: f"${c}$", md)
        md = re.sub(r"(\$[^$]+\$)\s*" + re.escape(sym) + r"(?!\$)",
                    lambda m, c=cmd: f"{m.group(1)} ${c}$", md)

    # Merge adjacent math blocks created above
    md = _combine_adjacent_math(md)

    # Symbols that render best as unicode kept in math mode
    for sym in UNICODE_MATH_KEEP:
        md = re.sub(r"(?<!\$)" + re.escape(sym) + r"(?!\$)",
                    lambda m, s=sym: f"${s}$", md)

    # Trim whitespace inside $...$ (tex_math_dollars wants no padding)
    md = re.sub(r"(?<!\$)\$([^$]+?)\$(?!\$)",
                lambda m: f"${m.group(1).strip()}$", md)

    # Restore protected code (loop in case a span nested another placeholder)
    for _ in range(5):
        if "\x00" not in md:
            break
        md = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], md)
    return md


# Rendering
def _extract_bad_command(err):
    """Pull the offending \\command out of an xelatex 'Undefined control sequence'."""
    m = re.search(r"Undefined control sequence\.\s*\n\s*l\.\d+\s*(.*)", err)
    if not m:
        return None
    cmds = re.findall(r"\\([A-Za-z]+)", m.group(1))
    return f"\\{cmds[-1]}" if cmds else None


def _pandoc_once(md_text, output_path, from_fmt, header_path, mermaid_filter):
    """Run pandoc once on md_text. Returns (ok, error_message)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8") as temp_md:
        temp_md.write(md_text)
        temp_md_path = temp_md.name

    cmd = [
        "pandoc", temp_md_path,
        "-o", str(output_path),
        "--pdf-engine=xelatex",
        "--standalone",
        f"--include-in-header={header_path}",
        f"--from={from_fmt}",
        "--to=pdf",
    ]
    if mermaid_filter:
        cmd += ["--filter", mermaid_filter]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        try:
            os.unlink(temp_md_path)
        except OSError:
            pass
        # mermaid-filter writes a .err file in the cwd; clean it up
        err_file = Path("mermaid-filter.err")
        if err_file.exists():
            try:
                err_file.unlink()
            except OSError:
                pass

    if result.returncode == 0 and output_path.exists():
        return True, ""
    error_msg = result.stderr.strip() if result.stderr else "unknown error"
    if result.stdout:
        error_msg += f"\nstdout: {result.stdout.strip()}"
    return False, error_msg


def run_pandoc(rich_md, safe_md, output_path):
    """Render with full fidelity, falling back to a safe render if xelatex fails."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tex", delete=False,
                                     encoding="utf-8") as header_file:
        header_file.write(LATEX_HEADER)
        header_path = header_file.name

    mermaid_filter = which("mermaid-filter")

    try:
        ok, err = _pandoc_once(rich_md, output_path, PANDOC_FROM, header_path, mermaid_filter)
        if ok:
            print(f"Successfully converted to '{output_path}'")
            return True

        # Full render failed: report the likely culprit and try the safe render.
        bad = _extract_bad_command(err)
        if bad:
            print(f"  full render failed on undefined LaTeX command '{bad}' "
                  f"(check your markdown); retrying in safe mode")
        else:
            print("  full render failed; retrying in safe mode")

        ok, err2 = _pandoc_once(safe_md, output_path, PANDOC_FROM_SAFE, header_path, mermaid_filter)
        if ok:
            print(f"  produced a PDF in safe mode (math shown as text) -> '{output_path}'")
            return True

        print(f"pandoc failed: {err2}")
        return False
    finally:
        try:
            os.unlink(header_path)
        except OSError:
            pass


# Orchestration
def convert_md_to_pdf(md_path: str, output_path: str | None = None) -> bool:
    """Convert one markdown file to a PDF in output/.

    Args:
        md_path: path to the .md file (relative to input/ or absolute).
        output_path: desired output filename; defaults to the input stem + .pdf.

    Returns:
        True if the conversion succeeded, False otherwise.
    """
    # If the provided path already points to a PDF, bail out early
    try:
        if Path(md_path).suffix.lower() == ".pdf":
            print("That file is already in pdf format")
            return False
    except Exception:
        pass

    full_input_path = (Path(md_path) if os.path.isabs(str(md_path))
                       else Path(input_folder) / md_path)
    if not full_input_path.exists():
        print(f"Error: Markdown file '{full_input_path}' not found")
        return False

    if output_path is None:
        pdf_name = f"{full_input_path.stem}.pdf"
    else:
        pdf_name = Path(output_path).name
    os.makedirs(output_folder, exist_ok=True)
    full_output_path = Path(output_folder) / pdf_name

    if not which("pandoc"):
        print("Error: pandoc not found. Please install pandoc to convert Markdown to PDF.")
        return False

    try:
        with open(full_input_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        # Shared safe preprocessing (no injected LaTeX) -> reused by the fallback
        md_content = clean_control_chars(md_content)
        md_content = normalize_math_delimiters(md_content)
        md_content = ensure_list_spacing(md_content)
        safe_md = md_content

        # Full-fidelity preprocessing on top
        rich_md = wrap_ascii_diagrams(md_content)
        rich_md = normalize_tables(rich_md)
        rich_md = convert_symbols(rich_md)

        print(f"Converting '{full_input_path}' to '{full_output_path}' .")
        return run_pandoc(rich_md, safe_md, full_output_path)
    except Exception as e:
        print(f"Unexpected error running pandoc: {e}")
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        # No args: convert all .md files in input/
        md_files = sorted(Path(input_folder).glob("*.md")) if os.path.isdir(input_folder) else []
        if not md_files:
            print("No .md files found in input folder")
            print("Usage: python md_pdf.py <file.md> [output.pdf]")
            print("Example: python md_pdf.py notes.md")
            print("Example: python md_pdf.py notes.md my_notes.pdf")
            return
        any_failed = False
        for md in md_files:
            if not convert_md_to_pdf(md.name, None):
                any_failed = True
        if any_failed:
            sys.exit(1)
        return

    md_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    if not convert_md_to_pdf(md_file, output_file):
        sys.exit(1)


if __name__ == "__main__":
    main()
