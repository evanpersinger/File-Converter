"""Convert R Markdown (.Rmd) files to PDF.

For each .Rmd in input/ (or a file passed as an argument), substitutes Sys.Date()
with today's date, then renders it to a PDF in output/.
"""


import os
import sys
import subprocess
import argparse
from pathlib import Path
from shutil import which
from datetime import date
import re

# Default folders live next to this script, so `python backend/Rmd_pdf.py` finds
# backend/input regardless of the shell's working directory.
SCRIPT_DIR = Path(__file__).resolve().parent


def command_exists(cmd):
    return which(cmd) is not None

def replace_sys_date(content):
    """Replace Sys.Date() with the actual current date in YYYY-MM-DD format."""
    current_date = date.today().strftime('%Y-%m-%d')
    # Replace inline R code chunks like `r Sys.Date()` with just the date
    # Pattern matches: `r Sys.Date()` or `r Sys.Date() ` with optional spaces
    inline_pattern = r'`r\s+Sys\.Date\s*\(\s*\)\s*`'
    content = re.sub(inline_pattern, current_date, content)
    # Also replace standalone Sys.Date() (handles various spacing)
    # Pattern matches Sys.Date() with optional spaces inside parentheses
    standalone_pattern = r'Sys\.Date\s*\(\s*\)'
    content = re.sub(standalone_pattern, current_date, content)
    return content

# convert an R markdown file to a pdf file
def convert_rmd_to_pdf(rmd_path: str, output_path: str | None = None,
                       input_dir: str | None = None, output_dir: str | None = None) -> bool:
    """Convert an R Markdown file to PDF.

    Prefers R's rmarkdown (which executes R code chunks) and falls back to pandoc.

    Args:
        rmd_path: Path to the .Rmd file (relative to input folder or absolute)
        output_path: Desired output PDF filename. If None, uses input stem + .pdf
        input_dir: Input directory (default: the script's input/ folder)
        output_dir: Output directory (default: the script's output/ folder)

    Returns:
        bool: True if conversion successful, False otherwise
    """
    # Set default directories if not provided. Default relative to this script, not
    # the caller's working directory, so it works no matter where it's invoked from.
    script_dir = Path(__file__).resolve().parent

    if input_dir is None:
        input_dir = script_dir / "input"
    else:
        input_dir = Path(input_dir)

    if output_dir is None:
        output_dir = script_dir / "output"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(exist_ok=True)

    # if the provided path already points to a PDF, stop
    try:
        if Path(rmd_path).suffix.lower() == ".pdf":
            print("That file is already in pdf format")
            return False
    except Exception:
        pass

    # Build full input path
    full_input_path = Path(rmd_path) if os.path.isabs(str(rmd_path)) else input_dir / rmd_path
    if not full_input_path.exists():
        print(f"Error: Rmd file '{full_input_path}' not found")
        return False

    # Compute output name
    if output_path is None:
        pdf_name = f"{full_input_path.stem}.pdf"
    else:
        pdf_name = Path(output_path).name
    full_output_path = output_dir / pdf_name

    # Try via R + rmarkdown (best for .Rmd with code chunks)
    if command_exists("Rscript"):
        import tempfile
        temp_path = None
        try:
            # Create a modified version with better formatting to prevent text overflow
            with open(full_input_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace Sys.Date() with actual date
            content = replace_sys_date(content)
            
            # Check if YAML header exists and add geometry settings for proper margins
            if content.startswith('---'):
                # Find the end of YAML header
                yaml_end = content.find('---', 3)
                if yaml_end != -1:
                    yaml_header = content[:yaml_end + 3]
                    # Add geometry settings if not already present
                    if 'geometry:' not in yaml_header and 'margin' not in yaml_header.lower():
                        yaml_header = yaml_header.replace('\n---', '\ngeometry: margin=1in\n---')
                        content = yaml_header + content[yaml_end + 3:]
            else:
                # No YAML header, prepend one
                content = '---\ngeometry: margin=1in\n---\n\n' + content
            
            # Create temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.Rmd', delete=False, encoding='utf-8') as tmp:
                tmp.write(content)
                temp_path = tmp.name
            
            r_expr = (
                "rmarkdown::render("
                f"\"{temp_path}\", "
                "output_format=\"pdf_document\", "
                f"output_file=\"{pdf_name}\", "
                f"output_dir=\"{str(output_dir)}\")"
            )
            cmd = [
                "Rscript",
                "-e",
                r_expr,
            ]
            print(f"Converting '{full_input_path}' to '{full_output_path}' using rmarkdown...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and full_output_path.exists():
                print(f"Successfully converted to '{full_output_path}'")
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                return True
            else:
                # Surface stderr for easier debugging
                if result.stderr:
                    print(f"rmarkdown stderr: {result.stderr.strip()}")
                print("rmarkdown conversion did not produce output; will try pandoc fallback if available.")
        except Exception as e:
            print(f"rmarkdown failed with error: {e}")
        finally:
            # Clean up temp file on error
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    # Fallback to pandoc (works for plain Markdown; R chunks won't execute)
    if command_exists("pandoc"):
        import tempfile
        header_path = None
        modified_input_path = None
        try:
            # Pre-process the Rmd file to break long lines
            with open(full_input_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace Sys.Date() with actual date
            content = replace_sys_date(content)
            
            # Break long lines by inserting spaces every 80 characters for regular text
            # (but not inside code blocks or YAML headers)
            # Also escape # characters in code blocks to prevent LaTeX errors
            lines = content.split('\n')
            processed_lines = []
            in_code_block = False
            in_yaml = False
            
            for line in lines:
                # Check if we're entering/exiting code blocks
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    processed_lines.append(line)
                    continue
                
                # Check if we're in YAML header
                if line.strip() == '---':
                    in_yaml = not in_yaml
                    processed_lines.append(line)
                    continue
                
                if in_code_block:
                    # Escape special LaTeX characters in code blocks
                    # Double backslashes first (so \n becomes \\n)
                    line = line.replace('\\', '\\\\')
                    # Escape $ to prevent math mode interpretation
                    line = line.replace('$', '\\$')
                    # Escape # to prevent macro parameter errors
                    line = line.replace('#', '\\#')
                    processed_lines.append(line)
                elif not in_yaml:
                    # Break very long lines (over 70 chars) at word boundaries
                    if len(line) > 70 and not line.strip().startswith('#'):
                        # Insert a line break after appropriate length
                        words = line.split()
                        if len(words) > 1:
                            current_line = ""
                            for word in words:
                                if len(current_line) + len(word) + 1 > 70 and current_line:
                                    processed_lines.append(current_line)
                                    current_line = word
                                else:
                                    current_line = current_line + " " + word if current_line else word
                            if current_line:
                                processed_lines.append(current_line)
                        else:
                            processed_lines.append(line)
                    else:
                        processed_lines.append(line)
                else:
                    processed_lines.append(line)
            
            modified_content = '\n'.join(processed_lines)
            
            # Create a temporary LaTeX header for better text wrapping
            header_content = r"""\usepackage{microtype}
\usepackage{xurl}
\usepackage{fvextra}
\usepackage{seqsplit}
\usepackage{url}
\PassOptionsToPackage{hyphens}{url}
\sloppy
\emergencystretch=3em
\setlength{\emergencystretch}{3em}
\hyphenpenalty=50
\hbadness=10000
\tolerance=9999
\overfullrule=0pt
\interlinepenalty=10000
\pretolerance=1000
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False, encoding='utf-8') as tmp:
                tmp.write(header_content)
                header_path = tmp.name
            
            # Create temp modified Rmd file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.Rmd', delete=False, encoding='utf-8') as tmp:
                tmp.write(modified_content)
                modified_input_path = tmp.name
            
            cmd = [
                "pandoc",
                modified_input_path,
                "-f", "markdown",  # Use standard markdown (math will work in text, code blocks are protected)
                "-o",
                str(full_output_path),
                "--pdf-engine=xelatex",
                "--standalone",
                "--syntax-highlighting=none",  # Disable highlighting to use plain verbatim
                "-V", "geometry:margin=1in",  # Set 1 inch margins
                "-V", "fontsize=11pt",  # Set readable font size
                "-H", header_path,  # Include LaTeX header for text wrapping
            ]
            print(f"Converting '{full_input_path}' to '{full_output_path}' using pandoc...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up temp files
            if os.path.exists(header_path):
                os.unlink(header_path)
            if os.path.exists(modified_input_path):
                os.unlink(modified_input_path)
            
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
        finally:
            # Clean up temp files on error
            if header_path and os.path.exists(header_path):
                os.unlink(header_path)
            if modified_input_path and os.path.exists(modified_input_path):
                os.unlink(modified_input_path)

    print("Neither Rscript (rmarkdown) nor pandoc found. Please install one of them to convert .Rmd to PDF.")
    print("- Install R + rmarkdown: Rscript -e 'install.packages(\"rmarkdown\")'")
    print("- Or install pandoc: see https://pandoc.org/installing.html")
    return False


def main():
    parser = argparse.ArgumentParser(description="Convert R Markdown files to PDF")
    parser.add_argument("rmd_file", nargs="?", help="R Markdown file to convert (optional)")
    parser.add_argument("output_file", nargs="?", help="Output PDF filename (optional)")
    parser.add_argument("--input-dir", default=SCRIPT_DIR / "input", help="Input directory (default: backend/input)")
    parser.add_argument("--output-dir", default=SCRIPT_DIR / "output", help="Output directory (default: backend/output)")
    
    args = parser.parse_args()
    
    # Set up directories
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    if args.rmd_file:
        # Convert specific file
        success = convert_rmd_to_pdf(args.rmd_file, args.output_file, input_dir, output_dir)
        if not success:
            sys.exit(1)
    else:
        # convert all .Rmd files in input/
        rmd_files = sorted(p for p in input_dir.glob("*.Rmd"))
        if not rmd_files:
            print(f"No .Rmd files found in {input_dir} folder")
            print("Usage: python Rmd_pdf.py <file.Rmd> [output.pdf] [--input-dir DIR] [--output-dir DIR]")
            print("Example: python Rmd_pdf.py report.Rmd")
            print("Example: python Rmd_pdf.py report.Rmd my_report.pdf")
            print("Example: python Rmd_pdf.py --input-dir myinput --output-dir myoutput")
            return
        any_failed = False
        for rmd in rmd_files:
            ok = convert_rmd_to_pdf(rmd.name, None, input_dir, output_dir)
            if not ok:
                any_failed = True
        if any_failed:
            sys.exit(1)


if __name__ == "__main__":
    main()


