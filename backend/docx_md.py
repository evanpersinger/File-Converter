"""Convert Word (.docx) documents in input/ to Markdown in output/ via pandoc.

Images are saved to output/<name>_images/ and linked from the Markdown with relative paths.
"""

import glob
import os
import subprocess
from shutil import which

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_docx_to_markdown() -> str:
    """Convert all DOCX files in the input folder to Markdown files in the output folder.

    Uses pandoc, so headings, lists, tables, links, and images carry over. Requires
    pandoc to be installed.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """
    if not which("pandoc"):
        return "Error: pandoc not found. Install it with: brew install pandoc"

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    docx_files = sorted(glob.glob(os.path.join(input_folder, '*.docx')))

    if not docx_files:
        # If there are only markdown files present, notify the user
        md_present = glob.glob(os.path.join(input_folder, '*.md'))
        if md_present:
            return "That file is already in markdown format"
        return "No DOCX files found in input folder"

    print(f"Found {len(docx_files)} DOCX files to convert")

    converted = []
    errors = []

    for docx_file in docx_files:
        filename = os.path.splitext(os.path.basename(docx_file))[0]

        try:
            # Runs from inside output_folder with a relative --extract-media path, because
            # pandoc writes image links exactly as given. An absolute path would break the
            # links as soon as the output is moved or zipped.
            result = subprocess.run(
                [
                    "pandoc", docx_file,
                    "--to=gfm",                             # GitHub Markdown, pipe tables
                    "--wrap=none",                          # no hard line breaks at 72 columns
                    f"--extract-media={filename}_images",
                    "-o", f"{filename}.md",
                ],
                cwd=output_folder,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                message = result.stderr.strip() or "unknown pandoc error"
                print(f"Error converting {docx_file}: {message}")
                errors.append(f"{os.path.basename(docx_file)}: {message}")
                continue

            print(f"Converted: {os.path.basename(docx_file)} -> {filename}.md")
            converted.append(f"{filename}.md")

        except Exception as e:
            print(f"Error converting {docx_file}: {str(e)}")
            errors.append(f"{os.path.basename(docx_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_docx_to_markdown())
