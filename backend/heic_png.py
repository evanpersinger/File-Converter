"""Convert HEIC images to PNG.

Registers the HEIF opener with Pillow, then for each .heic in input/ opens it and
saves a .png to output/. Unlike the JPG route this keeps an alpha channel if the
source has one, since PNG supports transparency.
"""

import os
import glob
from PIL import Image
import pillow_heif

# Register HEIF opener with Pillow so it can read .heic files
pillow_heif.register_heif_opener()

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_heic_to_png() -> str:
    """Convert all HEIC files in the input folder to PNG files in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Both cases are globbed because glob matches with fnmatch, which is case-sensitive
    # on macOS and Linux whatever the filesystem does, so '*.heic' alone would miss
    # IMG_1.HEIC, which is how the camera names them. A set rather than a concatenated
    # list so that a file matching two patterns is still converted once.
    heic_files = sorted({
        path
        for pattern in ('*.heic', '*.HEIC')
        for path in glob.glob(os.path.join(input_folder, pattern))
    })

    if not heic_files:
        png_present = glob.glob(os.path.join(input_folder, '*.png'))
        if png_present:
            return "That file is already in png format"
        return "No HEIC files found in input folder"

    print(f"Found {len(heic_files)} HEIC files to convert")

    converted = []
    errors = []

    for heic_file in heic_files:
        try:
            filename = os.path.splitext(os.path.basename(heic_file))[0]
            png_file = os.path.join(output_folder, f"{filename}.png")

            with Image.open(heic_file) as img:
                # PNG cannot store CMYK or the paletted-with-alpha oddities some
                # HEIC encoders produce, so anything unusual is normalised first.
                if img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                    img = img.convert('RGBA')
                img.save(png_file, 'PNG')
                print(f"Converted: {os.path.basename(heic_file)} -> {filename}.png")
                converted.append(f"{filename}.png")

        except Exception as e:
            print(f"Error converting {heic_file}: {str(e)}")
            errors.append(f"{os.path.basename(heic_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_heic_to_png())
