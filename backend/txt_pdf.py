"""Convert plain-text (.txt) files to PDF.

For each .txt in input/ (or a file passed as an argument), builds a titled PDF with
reportlab, one paragraph per line. Writes to output/.
"""

import os
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# Create input and output directories if they don't exist.
# Resolved relative to this script, not the caller's working directory, so the
# folders are always backend/input and backend/output no matter where you run from.
def setup_directories():
    script_dir = Path(__file__).resolve().parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"

    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    return input_dir, output_dir



# Convert a .txt file to PDF
# returns True if successful, False otherwise
def convert_txt_to_pdf(txt_path: str, output_path: str | None = None) -> bool:
    input_dir, output_dir = setup_directories()

    # if the provided path already points to a PDF let user know and return False
    try:
        provided_suffix = Path(txt_path).suffix.lower()
        if provided_suffix == ".pdf":
            print("That file is already in pdf format")
            return False
    except Exception:
        pass

    # Build full input path
    full_input_path = Path(txt_path) if os.path.isabs(str(txt_path)) else input_dir / txt_path
    if not full_input_path.exists():
        print(f"Error: Text file '{full_input_path}' not found")
        return False

    # Compute output name
    if output_path is None:
        pdf_name = f"{full_input_path.stem}.pdf"
    else:
        pdf_name = Path(output_path).name
    full_output_path = output_dir / pdf_name

    try:
        # Read text file
        with open(full_input_path, 'r', encoding='utf-8') as file:
            text_content = file.read()

        # Create PDF document
        doc = SimpleDocTemplate(str(full_output_path), pagesize=letter)
        styles = getSampleStyleSheet()

        # Create custom styles
        title_style = ParagraphStyle(
            'TextTitle',
            parent=styles['Title'],
            fontSize=16,
            spaceAfter=20,
            alignment=1  # Center alignment
        )

        normal_style = ParagraphStyle(
            'TextStyle',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            leftIndent=0,
            rightIndent=0,
            spaceAfter=6
        )

        # Build PDF content
        story = []

        # Add title
        filename = full_input_path.stem
        title = Paragraph(f"Text File: {filename}", title_style)
        story.append(title)
        story.append(Spacer(1, 20))

        # Add text content
        lines = text_content.split('\n')
        for line in lines:
            if line.strip():
                # Escape special characters for reportlab
                escaped_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                para = Paragraph(escaped_line, normal_style)
                story.append(para)
            else:
                story.append(Spacer(1, 6))  # Empty line spacing

        # Build PDF
        print(f"Converting '{full_input_path}' to '{full_output_path}'...")
        doc.build(story)
        
        if full_output_path.exists():
            print(f"Successfully converted to '{full_output_path}'")
            return True
        else:
            print("PDF creation failed")
            return False

    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        # No args: convert all .txt files in input/
        input_dir, output_dir = setup_directories()
        txt_files = sorted(p for p in input_dir.glob("*.txt"))
        if not txt_files:
            print("No .txt files found in input folder")
            print("Usage: python txt_pdf.py <file.txt> [output.pdf]")
            print("Example: python txt_pdf.py notes.txt")
            print("Example: python txt_pdf.py notes.txt my_notes.pdf")
            return
        any_failed = False
        for txt in txt_files:
            ok = convert_txt_to_pdf(txt.name, None)
            if not ok:
                any_failed = True
        if any_failed:
            sys.exit(1)
        return

    txt_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    success = convert_txt_to_pdf(txt_file, output_file)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
