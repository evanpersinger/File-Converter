"""Convert PNG images to SVG by tracing them into vector paths.

For each .png in input/, vtracer traces the bitmap into filled SVG paths and writes a
.svg to output/. This is real vectorisation, not the source PNG wrapped in an <svg>
tag, so the result scales to any size without pixelating and can be edited as vector
art.

Tracing suits flat-colour art: logos, icons, line drawings, screenshots of UI. A
photograph has no flat regions to trace, so it comes back as tens of thousands of tiny
paths, slow to produce and larger than the PNG it came from.
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

    # A set, not a concatenated list: macOS filesystems are case-insensitive by
    # default, so '*.png' and '*.PNG' return the same file and a list would convert
    # it twice.
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

            # These are vtracer's own defaults, spelled out because they are the
            # knobs worth reaching for if output looks wrong: 'color' keeps flat
            # colour regions where 'binary' would throw colour away, 'spline' fits
            # curves instead of straight-edged polygons, and filter_speckle drops
            # clusters under 4x4 px so compression noise does not become paths.
            vtracer.convert_image_to_svg_py(
                png_file,
                svg_file,
                colormode='color',
                mode='spline',
                filter_speckle=4,
            )
            print(f"Converted: {os.path.basename(png_file)} -> {filename}.svg")
            converted.append(f"{filename}.svg")

        except Exception as e:
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
