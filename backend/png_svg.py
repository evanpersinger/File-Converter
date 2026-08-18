"""Convert PNG images to SVG by tracing them into vector paths.

For each .png in input/, vtracer traces the bitmap into filled SVG paths and writes a
.svg to output/. This is real vectorization, not the source PNG wrapped in an <svg>
tag, so the result scales without pixelating. Tracing suits flat-color art. A
photograph has no flat regions and comes back as tens of thousands of paths, slower to
produce and larger than the PNG it came from. See the README for the tuning knobs.
"""

import os
import glob
import vtracer

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_png_to_svg() -> str:
    """Convert all PNG files in the input folder to SVG files in the output folder.

    Returns:
        A summary of what was converted, suitable for showing to a caller.
    """

    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Both cases are globbed because glob matches with fnmatch, which is case-sensitive
    # on macOS and Linux whatever the filesystem does, so '*.png' alone would miss
    # logo.PNG. A set rather than a concatenated list so that a file matching two
    # patterns is still converted once.
    png_files = sorted({
        path
        for pattern in ('*.png', '*.PNG')
        for path in glob.glob(os.path.join(input_folder, pattern))
    })

    if not png_files:
        svg_present = glob.glob(os.path.join(input_folder, '*.svg'))
        if svg_present:
            return "That file is already in svg format"
        return "No PNG files found in input folder"

    print(f"Found {len(png_files)} PNG files to convert")

    converted = []
    errors = []

    for png_file in png_files:
        try:
            filename = os.path.splitext(os.path.basename(png_file))[0]
            svg_file = os.path.join(output_folder, f"{filename}.svg")

            # vtracer's defaults suit flat-color art. colormode, mode and
            # filter_speckle are the knobs to reach for otherwise, see the README.
            vtracer.convert_image_to_svg_py(png_file, svg_file)
            print(f"Converted: {os.path.basename(png_file)} -> {filename}.svg")
            converted.append(f"{filename}.svg")

        # vtracer is a Rust extension: on an unreadable file it panics, and pyo3's
        # PanicException derives from BaseException, so `except Exception` never sees it
        # and one bad file takes down the whole batch. The class is not importable to
        # name directly, hence the wide catch with the interrupts re-raised first.
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            print(f"Error converting {png_file}: {str(e)}")
            errors.append(f"{os.path.basename(png_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_png_to_svg())
