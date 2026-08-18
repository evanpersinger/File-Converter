"""Convert JPG/JPEG images to PNG.

For each .jpg/.jpeg in input/, opens it with Pillow and saves it as a .png in
output/. JPEG carries no transparency, so nothing is lost on the way across.
"""

import os
import glob
from PIL import Image

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_jpg_to_png() -> str:
    """Convert all JPG/JPEG files in the input folder to PNG files in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Both cases are globbed because glob matches with fnmatch, which is case-sensitive
    # on macOS and Linux whatever the filesystem does, so '*.jpg' alone would miss
    # photo.JPG. A set rather than a concatenated list so that a file matching two
    # patterns is still converted once.
    jpg_files = sorted({
        path
        for pattern in ('*.jpg', '*.jpeg', '*.JPG', '*.JPEG')
        for path in glob.glob(os.path.join(input_folder, pattern))
    })

    if not jpg_files:
        png_present = glob.glob(os.path.join(input_folder, '*.png'))
        if png_present:
            return "That file is already in png format"
        return "No JPG files found in input folder"

    print(f"Found {len(jpg_files)} JPG files to convert")

    converted = []
    errors = []

    for jpg_file in jpg_files:
        try:
            filename = os.path.splitext(os.path.basename(jpg_file))[0]
            png_file = os.path.join(output_folder, f"{filename}.png")

            with Image.open(jpg_file) as img:
                img.save(png_file, 'PNG')
                print(f"Converted: {os.path.basename(jpg_file)} -> {filename}.png")
                converted.append(f"{filename}.png")

        except Exception as e:
            print(f"Error converting {jpg_file}: {str(e)}")
            errors.append(f"{os.path.basename(jpg_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_jpg_to_png())
