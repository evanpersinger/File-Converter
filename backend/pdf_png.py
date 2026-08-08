"""Convert PDF pages to PNG images.

For each .pdf in input/, renders every page with PyMuPDF and writes one PNG per page
to output/. A single-page PDF produces name.png; a multi-page one produces
name_page1.png, name_page2.png, and so on.
"""

import os
import glob
import fitz  # PyMuPDF

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')

# Rendering resolution. PDF pages are vector, so this is a choice rather than a
# property of the file: 200 keeps body text sharp on screen without turning every
# page into a multi-megabyte PNG the way 300+ does.
RENDER_DPI = 200


def convert_pdf_to_png() -> str:
    """Render every page of each PDF in the input folder to a PNG in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    pdf_files = sorted({
        path
        for pattern in ('*.pdf', '*.PDF')
        for path in glob.glob(os.path.join(input_folder, pattern))
    })

    if not pdf_files:
        png_present = glob.glob(os.path.join(input_folder, '*.png'))
        if png_present:
            return "That file is already in png format"
        return "No PDF files found in input folder"

    print(f"Found {len(pdf_files)} PDF files to convert")

    converted = []
    errors = []

    for pdf_file in pdf_files:
        try:
            filename = os.path.splitext(os.path.basename(pdf_file))[0]

            with fitz.open(pdf_file) as document:
                if document.page_count == 0:
                    errors.append(f"{os.path.basename(pdf_file)}: no pages")
                    continue

                for index, page in enumerate(document, start=1):
                    # Single-page PDFs keep the plain name, so the common case does
                    # not end up with a pointless "_page1" suffix.
                    suffix = "" if document.page_count == 1 else f"_page{index}"
                    png_file = os.path.join(output_folder, f"{filename}{suffix}.png")

                    page.get_pixmap(dpi=RENDER_DPI).save(png_file)
                    print(f"Converted: {os.path.basename(pdf_file)} page {index} "
                          f"-> {filename}{suffix}.png")
                    converted.append(f"{filename}{suffix}.png")

        except Exception as e:
            print(f"Error converting {pdf_file}: {str(e)}")
            errors.append(f"{os.path.basename(pdf_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_pdf_to_png())
