"""Fixtures shared by the converter tests.

Every folder-based converter reads module-level `input_folder` / `output_folder`
globals at call time rather than taking paths as arguments, and server.py drives them
by swapping those globals for the duration of a request (`via_globals` in server.py).
The `sandbox` fixture does the same swap onto a tmp_path, so a test never touches the
real backend/input and backend/output.
"""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image


@pytest.fixture
def sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[ModuleType], tuple[Path, Path]]:
    """Point a converter module's folder globals at a throwaway pair of directories.

    Returns a callable so each test names the module it is exercising:

        input_dir, output_dir = sandbox(jpg_png)

    Only the input directory is created. The converters are responsible for making
    their own output directory, which leaves that behaviour testable.
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    def redirect(module: ModuleType) -> tuple[Path, Path]:
        monkeypatch.setattr(module, "input_folder", str(input_dir))
        monkeypatch.setattr(module, "output_folder", str(output_dir))
        return input_dir, output_dir

    return redirect


@pytest.fixture
def write_image() -> Callable[..., Path]:
    """Write a small genuine image, so Pillow has something real to open.

    The format is passed explicitly rather than inferred, so a test can deliberately
    mismatch the contents and the extension.
    """

    def write(path: Path, fmt: str = "JPEG", color: str = "red") -> Path:
        Image.new("RGB", (8, 8), color).save(path, fmt)
        return path

    return write
