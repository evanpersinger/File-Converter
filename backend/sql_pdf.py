"""Convert SQL files in input/ to PDF in output/: a title, then the source as written in a monospace code box.

No syntax highlighting and no reformatting.
"""

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def setup_directories():
    """Return (input_dir, output_dir) next to this script, creating them if missing."""
    script_dir = Path(__file__).resolve().parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    return input_dir, output_dir


def create_pdf_from_sql(sql_file_path, output_path) -> bool:
    """Write one PDF: a "SQL File: <name>" title, then each line of the source in a grey Courier box."""
    try:
        sql_path = Path(sql_file_path)
        sql_content = sql_path.read_text(encoding="utf-8")

        styles = getSampleStyleSheet()
        sql_style = ParagraphStyle(
            "SQLCode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=9,
            leading=12,
            leftIndent=20,
            rightIndent=20,
            spaceAfter=12,
            backColor=colors.lightgrey,
            borderColor=colors.black,
            borderWidth=1,
            borderPadding=10,
        )
        title_style = ParagraphStyle(
            "SQLTitle", parent=styles["Title"], fontSize=16, spaceAfter=20, alignment=1
        )

        story = [Paragraph(f"SQL File: {sql_path.stem}", title_style), Spacer(1, 20)]
        for line in sql_content.split("\n"):
            if line.strip():
                # Paragraph parses XML-ish markup, so escape the characters SQL uses freely.
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(escaped, sql_style))
            else:
                story.append(Spacer(1, 6))

        SimpleDocTemplate(str(output_path), pagesize=A4).build(story)
        return True
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False


def convert_sql_files() -> str:
    """Convert every .sql in input/ to a PDF in output/. Returns a summary for the caller."""
    input_dir, output_dir = setup_directories()
    sql_files = sorted(input_dir.glob("*.sql"))
    if not sql_files:
        return "No SQL files found in the input/ directory. Please place your .sql files in the input/ folder and try again."

    converted = []
    errors = []
    for sql_file in sql_files:
        output_file = output_dir / f"{sql_file.stem}.pdf"
        print(f"Converting {sql_file.name}...")
        if create_pdf_from_sql(sql_file, output_file):
            converted.append(output_file.name)
        else:
            errors.append(sql_file.name)

    if not converted:
        return f"No files converted. {len(errors)} failed: {', '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {', '.join(errors)}"
    return summary


def main():
    parser = argparse.ArgumentParser(description="Convert SQL files to PDF")
    parser.add_argument("sql_file", nargs="?", help="SQL file to convert (default: every .sql in input/)")
    parser.add_argument("output_file", nargs="?", help="Output PDF name (default: <sql name>.pdf)")
    args = parser.parse_args()

    if not args.sql_file:
        print(convert_sql_files())
        return

    input_dir, output_dir = setup_directories()
    sql_path = Path(args.sql_file)
    if not sql_path.is_absolute():
        sql_path = input_dir / sql_path
    if sql_path.suffix.lower() != ".sql" or not sql_path.exists():
        print(f"Error: '{sql_path}' is not an existing .sql file.")
        return

    output_path = output_dir / (args.output_file or f"{sql_path.stem}.pdf")
    print(f"Converting {sql_path.name} to {output_path.name}...")
    if not create_pdf_from_sql(sql_path, output_path):
        print(f"Failed to convert {sql_path.name}")


if __name__ == "__main__":
    main()
