"""Smoke-test the OIDN wrapper's native EXR channel preservation.

The test image includes UINT values above the exact integer range of float32.
Those channels must survive both untouched parts and non-RGB channels inside a
denoised part without float round-tripping.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import OpenEXR


def _part_name(part: object) -> str:
    name = getattr(part, "name")
    return name() if callable(name) else str(name)


def _find_part(exr_file: OpenEXR.File, name: str) -> object:
    for part in exr_file.parts:
        if _part_name(part) == name:
            return part
    raise AssertionError(f"EXR part {name!r} was not found")


def _read_channel(path: Path, part_name: str, channel_name: str) -> np.ndarray:
    exr_file = OpenEXR.File(str(path))
    part = _find_part(exr_file, part_name)
    channels = part.channels
    if channel_name not in channels:
        raise AssertionError(f"Channel {channel_name!r} was not found in part {part_name!r}")
    return np.asarray(channels[channel_name].pixels)


def _create_source(path: Path) -> tuple[np.ndarray, np.ndarray]:
    height = 32
    width = 32
    y, x = np.mgrid[0:height, 0:width]

    r = (0.1 + x / width).astype(np.float32)
    g = (0.2 + y / height).astype(np.float32)
    b = (0.3 + ((x + y) % 7) / 7.0).astype(np.float32)

    beauty_ids = (np.uint32(16_777_217) + ((x + y) % 5).astype(np.uint32)).astype(np.uint32)
    untouched_ids = (np.uint32(16_777_219) + (x + y * width).astype(np.uint32)).astype(np.uint32)

    parts = [
        OpenEXR.Part(
            {"name": "C"},
            {
                "R": r,
                "G": g,
                "B": b,
                "object_id": beauty_ids,
            },
        ),
        OpenEXR.Part({"name": "ids"}, {"id": untouched_ids}),
    ]
    OpenEXR.File(parts).write(str(path))
    return beauty_ids, untouched_ids


def _assert_equal(label: str, expected: np.ndarray, actual: np.ndarray) -> None:
    if np.array_equal(expected, actual):
        return

    mismatch = np.argwhere(expected != actual)[0]
    index = tuple(int(value) for value in mismatch)
    raise AssertionError(
        f"{label} changed at {index}: source={int(expected[index])} output={int(actual[index])}"
    )


def _run_validation(denoiser: Path, work_dir: Path) -> None:
    source = work_dir / "oidn_uint_preservation_source.exr"
    output = work_dir / "oidn_uint_preservation_output.exr"
    if output.exists():
        output.unlink()

    expected_beauty_ids, expected_untouched_ids = _create_source(source)

    command = [
        str(denoiser),
        "-v",
        "1",
        "-multipart",
        str(source),
        "-o",
        str(output),
        "-beauty-name",
        "C",
    ]
    result = subprocess.run(
        command,
        cwd=denoiser.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(f"OIDN wrapper exited with status {result.returncode}")
    if not output.exists():
        raise AssertionError(f"OIDN wrapper did not create output: {output}")

    output_file = OpenEXR.File(str(output))
    if len(output_file.parts) != 2:
        raise AssertionError(f"Expected 2 EXR parts, found {len(output_file.parts)}")

    _assert_equal("denoised part UINT side channel", expected_beauty_ids, _read_channel(output, "C", "object_id"))
    _assert_equal("untouched UINT part", expected_untouched_ids, _read_channel(output, "ids", "id"))

    print("OIDN UINT preservation smoke test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denoiser", required=True, type=Path, help="Path to the custom OIDN Denoiser.exe")
    parser.add_argument("--work-dir", type=Path, help="Directory for temporary EXR files")
    parser.add_argument("--keep-files", action="store_true", help="Keep generated EXR files for inspection")
    args = parser.parse_args()

    denoiser = args.denoiser.resolve()
    if not denoiser.exists():
        raise FileNotFoundError(denoiser)

    if args.work_dir:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        _run_validation(denoiser, work_dir)
        return 0

    temp_dir = Path(tempfile.mkdtemp(prefix="hdu-oidn-uint-"))
    try:
        _run_validation(denoiser, temp_dir)
        if args.keep_files:
            print(f"Kept validation files in: {temp_dir}")
            return 0
    finally:
        if not args.keep_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
