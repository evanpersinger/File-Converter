"""Convert PowerPoint (.pptx) files to PDF.

For each .pptx in input/, shells out to a headless LibreOffice (soffice) to render
the slides to PDF in output/. Requires LibreOffice to be installed.
"""

import os
import glob
import subprocess

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')

def convert_pptx_to_pdf() -> str:
    """Convert all PPTX files in the input folder to PDF files in the output folder.

    Requires LibreOffice to be installed.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Find all PPTX files
    pptx_files = glob.glob(os.path.join(input_folder, '*.pptx'))

    if not pptx_files:
        # If only PDFs are present, notify the file(s) are already PDF
        pdf_present = glob.glob(os.path.join(input_folder, '*.pdf'))
        if pdf_present:
            return "That file is already in pdf format"
        return "No PPTX files found in input folder"

    print(f"Found {len(pptx_files)} PPTX files to convert")
    
    # Resolve LibreOffice executable across platforms
    libreoffice_executables = [
        'libreoffice',  # common on Linux
        'soffice',      # common alias
        '/Applications/LibreOffice.app/Contents/MacOS/soffice'  # macOS app bundle
    ]
    resolved_executable = None
    for candidate in libreoffice_executables:
        try:
            check = subprocess.run([candidate, '--version'], capture_output=True, text=True)
            if check.returncode == 0 or 'LibreOffice' in check.stdout:
                resolved_executable = candidate
                break
        except FileNotFoundError:
            continue

    if not resolved_executable:
        return (
            "LibreOffice not found in PATH. On macOS (Homebrew cask): "
            "brew install --cask libreoffice. If already installed via .app, add a symlink: "
            "sudo ln -s /Applications/LibreOffice.app/Contents/MacOS/soffice /usr/local/bin/soffice"
        )

    print(f"Using LibreOffice executable: {resolved_executable}")

    converted = []
    errors = []

    for pptx_file in pptx_files:
        try:
            # Get filename without extension
            filename = os.path.splitext(os.path.basename(pptx_file))[0]

            # Use LibreOffice to convert PPTX to PDF
            # This requires LibreOffice to be installed
            cmd = [
                resolved_executable,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', output_folder,
                pptx_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"Converted: {os.path.basename(pptx_file)} -> {filename}.pdf")
                converted.append(f"{filename}.pdf")
            else:
                print(f"Error converting {pptx_file}: {result.stderr}")
                errors.append(f"{os.path.basename(pptx_file)}: {result.stderr.strip()}")

        except FileNotFoundError:
            errors.append("LibreOffice executable became unavailable during run")
            break
        except Exception as e:
            print(f"Error converting {pptx_file}: {str(e)}")
            errors.append(f"{os.path.basename(pptx_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary

if __name__ == "__main__":
    print(convert_pptx_to_pdf())
