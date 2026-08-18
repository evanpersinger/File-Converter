"""Tests for jpg_png.py, the thin Pillow-backed JPG -> PNG converter.

Pillow's encoding is not what is under test. What is: which files the globs pick up,
the message a caller gets back when there is nothing to do, and the fact that one
unreadable file does not take the rest of the batch down with it.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

import jpg_png

Sandbox = Callable[[ModuleType], tuple[Path, Path]]
WriteImage = Callable[..., Path]


def test_reports_when_input_is_empty(sandbox: Sandbox) -> None:
    sandbox(jpg_png)
    assert jpg_png.convert_jpg_to_png() == "No JPG files found in input folder"


def test_reports_when_the_file_is_already_a_png(
    sandbox: Sandbox, write_image: WriteImage
) -> None:
    """A PNG in the input folder is a user mistake worth naming, not just "nothing found"."""
    input_dir, _ = sandbox(jpg_png)
    write_image(input_dir / "photo.png", "PNG")

    assert jpg_png.convert_jpg_to_png() == "That file is already in png format"


def test_converts_a_single_jpg(sandbox: Sandbox, write_image: WriteImage) -> None:
    input_dir, output_dir = sandbox(jpg_png)
    write_image(input_dir / "photo.jpg")

    summary = jpg_png.convert_jpg_to_png()

    assert "photo.png" in summary
    with Image.open(output_dir / "photo.png") as img:
        assert img.format == "PNG"


@pytest.mark.parametrize("filename", ["photo.jpg", "photo.jpeg", "photo.JPG", "photo.JPEG"])
def test_picks_up_every_spelling_of_the_extension(
    sandbox: Sandbox, write_image: WriteImage, filename: str
) -> None:
    input_dir, output_dir = sandbox(jpg_png)
    write_image(input_dir / filename)

    jpg_png.convert_jpg_to_png()

    assert (output_dir / "photo.png").exists()


def test_a_file_is_converted_exactly_once(sandbox: Sandbox, write_image: WriteImage) -> None:
    """The four glob patterns are collapsed into a set before converting, so no file
    can be picked up twice and written over itself."""
    input_dir, output_dir = sandbox(jpg_png)
    write_image(input_dir / "photo.jpg")

    summary = jpg_png.convert_jpg_to_png()

    assert summary.count("photo.png") == 1
    assert len(list(output_dir.iterdir())) == 1


def test_converts_several_files(sandbox: Sandbox, write_image: WriteImage) -> None:
    input_dir, output_dir = sandbox(jpg_png)
    write_image(input_dir / "one.jpg")
    write_image(input_dir / "two.jpg")

    summary = jpg_png.convert_jpg_to_png()

    assert "Converted 2 file(s)" in summary
    assert sorted(p.name for p in output_dir.iterdir()) == ["one.png", "two.png"]


def test_an_unreadable_file_is_reported_rather_than_raised(sandbox: Sandbox) -> None:
    input_dir, _ = sandbox(jpg_png)
    (input_dir / "broken.jpg").write_bytes(b"this is not a jpeg")

    summary = jpg_png.convert_jpg_to_png()

    assert summary.startswith("No files converted. 1 failed:")
    assert "broken.jpg" in summary


def test_one_bad_file_does_not_stop_the_good_ones(
    sandbox: Sandbox, write_image: WriteImage
) -> None:
    input_dir, output_dir = sandbox(jpg_png)
    write_image(input_dir / "good.jpg")
    (input_dir / "broken.jpg").write_bytes(b"this is not a jpeg")

    summary = jpg_png.convert_jpg_to_png()

    assert "good.png" in summary
    assert "1 failed" in summary
    assert (output_dir / "good.png").exists()


def test_output_folder_is_created_when_missing(
    sandbox: Sandbox, write_image: WriteImage
) -> None:
    input_dir, output_dir = sandbox(jpg_png)
    assert not output_dir.exists()
    write_image(input_dir / "photo.jpg")

    jpg_png.convert_jpg_to_png()

    assert output_dir.is_dir()
