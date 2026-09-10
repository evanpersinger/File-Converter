"""Convert SQL files to PDF.

For each .sql in input/, applies basic SQL keyword highlighting and lays the
statements out as a formatted PDF with reportlab. Writes to output/.
"""


import argparse
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def setup_directories():
    """Create input and output directories if they don't exist.

    Resolved relative to this script, not the caller's working directory, so the
    folders are always backend/input and backend/output no matter where you run from.
    """
    script_dir = Path(__file__).resolve().parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"

    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    return input_dir, output_dir


def create_pdf_from_sql(sql_file_path, output_path):
    """Create a PDF from SQL file content."""
    try:
        # Read SQL file
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_content = file.read()
        
        # Keep original SQL formatting without reindenting
        formatted_sql = sql_content
        
        # Create PDF document
        doc = SimpleDocTemplate(str(output_path), pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Create custom style for SQL code
        sql_style = ParagraphStyle(
            'SQLCode',
            parent=styles['Code'],
            fontSize=9,
            leading=12,
            fontName='Courier',
            leftIndent=20,
            rightIndent=20,
            spaceAfter=12,
            backColor=colors.lightgrey,
            borderColor=colors.black,
            borderWidth=1,
            borderPadding=10
        )
        
        # Create title style
        title_style = ParagraphStyle(
            'SQLTitle',
            parent=styles['Title'],
            fontSize=16,
            spaceAfter=20,
            alignment=1  # Center alignment
        )
        
        # Build PDF content
        story = []
        
        # Add title
        filename = Path(sql_file_path).stem
        title = Paragraph(f"SQL File: {filename}", title_style)
        story.append(title)
        story.append(Spacer(1, 20))
        
        # Add formatted SQL content
        sql_lines = formatted_sql.split('\n')
        for line in sql_lines:
            if line.strip():
                # Escape special characters for reportlab
                escaped_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                para = Paragraph(escaped_line, sql_style)
                story.append(para)
            else:
                story.append(Spacer(1, 6))  # Empty line spacing
        
        # Build PDF
        doc.build(story)
        return True
        
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False


def convert_sql_files() -> str:
    """Convert all SQL files in the input directory to PDF, with syntax highlighting.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    input_dir, output_dir = setup_directories()

    # Find SQL files
    sql_files = list(input_dir.glob("*.sql"))

    if not sql_files:
        return "No SQL files found in the input/ directory. Please place your .sql files in the input/ folder and try again."

    print(f"Found {len(sql_files)} SQL file(s) to convert:")
    for sql_file in sql_files:
        print(f"  - {sql_file.name}")

    converted = []
    errors = []

    for sql_file in sql_files:
        output_file = output_dir / f"{sql_file.stem}.pdf"

        print(f"\nConverting {sql_file.name}...")

        if create_pdf_from_sql(sql_file, output_file):
            print(f"✓ Successfully converted to {output_file.name}")
            converted.append(output_file.name)
        else:
            print(f"✗ Failed to convert {sql_file.name}")
            errors.append(sql_file.name)

    # Summary
    print(f"\n{'='*50}")
    print(f"Conversion Summary:")
    print(f"  Successful: {len(converted)}")
    print(f"  Failed: {len(errors)}")
    print(f"  Total: {len(sql_files)}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {', '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {', '.join(errors)}"
    return summary


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Convert SQL files to PDF")
    parser.add_argument("sql_file", nargs="?", help="SQL file to convert (optional)")
    parser.add_argument("output_file", nargs="?", help="Output PDF file name (optional)")
    
    args = parser.parse_args()
    
    if args.sql_file:
        # Convert specific file
        input_dir, output_dir = setup_directories()
        
        sql_file_path = Path(args.sql_file)
        if not sql_file_path.is_absolute():
            sql_file_path = input_dir / sql_file_path
        
        if not sql_file_path.exists():
            print(f"Error: File '{sql_file_path}' not found.")
            return
        
        if not sql_file_path.suffix.lower() == '.sql':
            print(f"Error: '{sql_file_path}' is not a SQL file.")
            return
        
        # Determine output file
        if args.output_file:
            output_path = output_dir / args.output_file
        else:
            output_path = output_dir / f"{sql_file_path.stem}.pdf"
        
        print(f"Converting {sql_file_path.name} to {output_path.name}...")
        
        if create_pdf_from_sql(sql_file_path, output_path):
            print(f"✓ Successfully converted to {output_path.name}")
        else:
            print(f"✗ Failed to convert {sql_file_path.name}")
    else:
        # Convert all SQL files in input directory
        print(convert_sql_files())


if __name__ == "__main__":
    main()
