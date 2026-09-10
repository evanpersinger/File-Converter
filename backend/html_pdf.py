"""Convert HTML files in input/ (or one passed as an argument) to PDF in output/.

Uses wkhtmltopdf, falling back to pandoc (xelatex) if it is not installed.
"""


import os
import sys
import subprocess
from pathlib import Path
from shutil import which


def command_exists(cmd):
    return which(cmd) is not None


def convert_html_to_pdf(html_path: str, output_path: str | None = None) -> bool:
    """
    Convert an .html file to PDF.

    Prefers wkhtmltopdf. Falls back to pandoc if wkhtmltopdf is unavailable.

    Args:
        html_path (str | Path): Path to the .html file (relative to input folder or absolute)
        output_path (str | Path | None): Desired output PDF filename. If None, uses input stem + .pdf

    Returns:
        bool: True if conversion successful, False otherwise
    """
    # Resolve folders relative to this script for consistency
    script_dir = Path(__file__).resolve().parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Early guard: if the provided path already points to a PDF, bail out
    try:
        if Path(html_path).suffix.lower() == ".pdf":
            print("That file is already in pdf format")
            return False
    except Exception:
        pass

    # Build full input path
    full_input_path = Path(html_path) if os.path.isabs(str(html_path)) else input_dir / html_path
    if not full_input_path.exists():
        print(f"Error: HTML file '{full_input_path}' not found")
        return False

    # Compute output name
    if output_path is None:
        pdf_name = f"{full_input_path.stem}.pdf"
    else:
        pdf_name = Path(output_path).name
    full_output_path = output_dir / pdf_name

    # 1) Try wkhtmltopdf (best quality for HTML rendering)
    if command_exists("wkhtmltopdf"):
        try:
            cmd = [
                "wkhtmltopdf",
                str(full_input_path),
                str(full_output_path),
            ]
            print(f"Converting '{full_input_path}' to '{full_output_path}' using wkhtmltopdf...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and full_output_path.exists():
                print(f"Successfully converted to '{full_output_path}'")
                return True
            else:
                if result.stderr:
                    print(f"wkhtmltopdf stderr: {result.stderr.strip()}")
                print("wkhtmltopdf conversion failed; will try pandoc fallback if available.")
        except Exception as e:
            print(f"wkhtmltopdf failed with error: {e}")

    # 2) Fallback to pandoc
    if command_exists("pandoc"):
        try:
            cmd = [
                "pandoc",
                str(full_input_path),
                "-o",
                str(full_output_path),
                "--pdf-engine=xelatex",
            ]
            print(f"Converting '{full_input_path}' to '{full_output_path}' using pandoc...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and full_output_path.exists():
                print(f"Successfully converted to '{full_output_path}'")
                return True
            else:
                print(f"pandoc failed: {result.stderr.strip() if result.stderr else 'unknown error'}")
                return False
        except FileNotFoundError:
            print("Error: pandoc not found.")
            return False
        except Exception as e:
            print(f"Unexpected error running pandoc: {e}")
            return False

    print("Neither wkhtmltopdf nor pandoc found. Please install one of them to convert HTML to PDF.")
    print("- Install wkhtmltopdf: https://wkhtmltopdf.org/downloads.html")
    print("- Or install pandoc: https://pandoc.org/installing.html")
    return False


def main():
    if len(sys.argv) < 2:
        # No args: convert all .html/.htm files in input/ (recursively)
        script_dir = Path(__file__).resolve().parent
        input_dir = script_dir / "input"
        input_dir.mkdir(exist_ok=True)
        html_files = sorted(
            p for p in input_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".html", ".htm"}
        )
        if not html_files:
            print(f"No .html files found in input folder: {input_dir}")
            print("Drop your HTML files into the 'input' folder and re-run.")
            return
        any_failed = False
        for html in html_files:
            ok = convert_html_to_pdf(html.name, None)
            if not ok:
                any_failed = True
        if any_failed:
            sys.exit(1)
        return

    html_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    success = convert_html_to_pdf(html_file, output_file)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()




