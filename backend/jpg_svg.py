"""Convert JPG/JPEG images to SVG by tracing them into vector paths.

For each .jpg/.jpeg in input/, vtracer traces the bitmap into filled SVG paths and
writes a .svg to output/. JPEG makes a poor tracing source twice over: it is lossy, so
edge ringing artifacts trace as real color regions, and it is the format photographs
arrive in. Trace a PNG instead where there is one, and see the README for the numbers
and the tuning knobs.
"""

import os
import glob
import vtracer

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Folders
input_folder = os.path.join(script_dir, 'input')
output_folder = os.path.join(script_dir, 'output')


def convert_jpg_to_svg() -> str:
    """Convert all JPG/JPEG files in the input folder to SVG files in the output folder.

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
        svg_present = glob.glob(os.path.join(input_folder, '*.svg'))
        if svg_present:
            return "That file is already in svg format"
        return "No JPG files found in input folder"

    print(f"Found {len(jpg_files)} JPG files to convert")

    converted = []
    errors = []

    for jpg_file in jpg_files:
        try:
            filename = os.path.splitext(os.path.basename(jpg_file))[0]
            svg_file = os.path.join(output_folder, f"{filename}.svg")

            # vtracer's defaults. Raise filter_speckle here if JPEG edge artifacts
            # are showing up as stray micro-paths, see the README.
            vtracer.convert_image_to_svg_py(jpg_file, svg_file)
            print(f"Converted: {os.path.basename(jpg_file)} -> {filename}.svg")
            converted.append(f"{filename}.svg")

        # vtracer is a Rust extension: on an unreadable file it panics, and pyo3's
        # PanicException derives from BaseException, so `except Exception` never sees it
        # and one bad file takes down the whole batch. The class is not importable to
        # name directly, hence the wide catch with the interrupts re-raised first.
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            print(f"Error converting {jpg_file}: {str(e)}")
            errors.append(f"{os.path.basename(jpg_file)}: {e}")

    if not converted:
        return f"No files converted. {len(errors)} failed: {'; '.join(errors)}"

    summary = f"Converted {len(converted)} file(s) to output/: {', '.join(converted)}"
    if errors:
        summary += f". {len(errors)} failed: {'; '.join(errors)}"
    return summary


if __name__ == "__main__":
    print(convert_jpg_to_svg())
