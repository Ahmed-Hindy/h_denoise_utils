"""Validate packaged OIDN denoising with a generated multipart EXR."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import OpenEXR


def _part_name(part: object) -> str:
    """Return an OpenEXR part name across binding variants.

    Args:
        part: OpenEXR part object.

    Returns:
        The part name.
    """
    name = getattr(part, "name")
    return name() if callable(name) else str(name)


def _find_part(exr_file: OpenEXR.File, name: str) -> object:
    """Find a named part in an OpenEXR file.

    Args:
        exr_file: Open multipart EXR file.
        name: Part name to locate.

    Returns:
        The matching OpenEXR part.

    Raises:
        AssertionError: If the requested part is missing.
    """
    for part in exr_file.parts:
        if _part_name(part) == name:
            return part
    raise AssertionError(f"EXR part {name!r} was not found")


def _rgb_channels(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
) -> dict[str, np.ndarray]:
    """Build an RGB channel mapping.

    Args:
        red: Red channel pixels.
        green: Green channel pixels.
        blue: Blue channel pixels.

    Returns:
        Mapping suitable for ``OpenEXR.Part``.
    """
    return {"R": red, "G": green, "B": blue}


def _create_source(path: Path) -> np.ndarray:
    """Create a deterministic multipart EXR with guides and an untouched part.

    Args:
        path: Destination EXR path.

    Returns:
        Expected UINT pixels from the untouched part.
    """
    height = 32
    width = 32
    y, x = np.mgrid[0:height, 0:width]

    red = (0.1 + x / width + ((x + y) % 5) * 0.02).astype(np.float32)
    green = (0.2 + y / height + ((x * 3 + y) % 7) * 0.015).astype(np.float32)
    blue = (0.3 + (x + y) / (width + height)).astype(np.float32)

    albedo_red = np.full((height, width), 0.6, dtype=np.float32)
    albedo_green = np.full((height, width), 0.5, dtype=np.float32)
    albedo_blue = np.full((height, width), 0.4, dtype=np.float32)

    normal_x = np.zeros((height, width), dtype=np.float32)
    normal_y = np.zeros((height, width), dtype=np.float32)
    normal_z = np.ones((height, width), dtype=np.float32)

    aov_red = (red * 0.4).astype(np.float32)
    aov_green = (green * 0.4).astype(np.float32)
    aov_blue = (blue * 0.4).astype(np.float32)

    untouched_ids = (
        np.uint32(16_777_219) + (x + y * width).astype(np.uint32)
    ).astype(np.uint32)

    parts = [
        OpenEXR.Part(
            {"name": "C", "comments": "packaged OIDN validation"},
            _rgb_channels(red, green, blue),
        ),
        OpenEXR.Part(
            {"name": "albedo"},
            _rgb_channels(albedo_red, albedo_green, albedo_blue),
        ),
        OpenEXR.Part(
            {"name": "N"},
            {"X": normal_x, "Y": normal_y, "Z": normal_z},
        ),
        OpenEXR.Part(
            {"name": "directdiffuse"},
            _rgb_channels(aov_red, aov_green, aov_blue),
        ),
        OpenEXR.Part({"name": "ids"}, {"id": untouched_ids}),
    ]
    OpenEXR.File(parts).write(str(path))
    return untouched_ids


def _assert_finite_float_channels(exr_file: OpenEXR.File) -> None:
    """Assert that every floating-point output channel is finite.

    Args:
        exr_file: Open output EXR file.

    Raises:
        AssertionError: If a floating-point channel contains NaN or infinity.
    """
    for part in exr_file.parts:
        part_name = _part_name(part)
        for channel_name, channel in part.channels.items():
            pixels = np.asarray(channel.pixels)
            if np.issubdtype(pixels.dtype, np.floating) and not np.isfinite(pixels).all():
                raise AssertionError(
                    f"Non-finite pixels found in {part_name}.{channel_name}"
                )


def _validate_output(output: Path, expected_ids: np.ndarray) -> None:
    """Validate the generated denoised EXR.

    Args:
        output: Denoised EXR path.
        expected_ids: Expected untouched UINT pixels.

    Raises:
        AssertionError: If EXR structure or pixel preservation is invalid.
    """
    output_file = OpenEXR.File(str(output))
    names = [_part_name(part) for part in output_file.parts]
    expected_names = ["C", "albedo", "N", "directdiffuse", "ids"]
    if names != expected_names:
        raise AssertionError(f"Expected parts {expected_names}, found {names}")

    beauty = _find_part(output_file, "C")
    if beauty.header.get("comments") != "packaged OIDN validation":
        raise AssertionError("Beauty-part metadata was not preserved")

    ids_part = _find_part(output_file, "ids")
    actual_ids = np.asarray(ids_part.channels["id"].pixels)
    if not np.array_equal(expected_ids, actual_ids):
        raise AssertionError("Untouched UINT part changed during packaged denoise")

    _assert_finite_float_channels(output_file)


def _run_validation(app: Path, work_dir: Path) -> None:
    """Run packaged OIDN denoising and validate its output.

    Args:
        app: Packaged h-denoise executable.
        work_dir: Directory for generated inputs and outputs.

    Raises:
        RuntimeError: If the packaged app exits unsuccessfully.
        AssertionError: If the expected output is missing or invalid.
    """
    source = work_dir / "packaged_oidn_source.exr"
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_ids = _create_source(source)

    command = [
        str(app),
        str(source),
        "--backend",
        "oidn",
        "--output-folder",
        str(output_dir),
        "--prefix",
        "validated_",
        "--overwrite",
        "--beauty",
        "C",
        "--albedo",
        "albedo",
        "--normal",
        "N",
        "--aov",
        "directdiffuse",
    ]
    result = subprocess.run(
        command,
        cwd=app.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Packaged app exited with status {result.returncode}")

    outputs = list(output_dir.glob("*.exr"))
    if len(outputs) != 1:
        raise AssertionError(f"Expected one denoised EXR, found {len(outputs)}")

    _validate_output(outputs[0], expected_ids)
    print(f"Packaged OIDN multipart EXR validation passed: {outputs[0]}")


def main() -> int:
    """Run the packaged OIDN validation command.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app",
        required=True,
        type=Path,
        help="Path to the packaged h-denoise executable",
    )
    parser.add_argument("--work-dir", type=Path, help="Directory for validation files")
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep generated EXR files for inspection",
    )
    args = parser.parse_args()

    app = args.app.resolve()
    if not app.is_file():
        raise FileNotFoundError(app)

    if args.work_dir:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        _run_validation(app, work_dir)
        return 0

    temp_dir = Path(tempfile.mkdtemp(prefix="hdu-packaged-oidn-"))
    try:
        _run_validation(app, temp_dir)
        if args.keep_files:
            print(f"Kept validation files in: {temp_dir}")
            return 0
    finally:
        if not args.keep_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
