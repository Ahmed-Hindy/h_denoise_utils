"""File operation utilities."""

from __future__ import annotations

import os
import re
from pathlib import Path


def natural_sort_key(name: str) -> list:
    """Generate a natural sort key (so '2' < '10').

    Args:
        name: String to generate sort key for

    Returns:
        List of integers and strings for natural sorting
    """
    num_re = re.compile(r"(\d+)")
    return [int(t) if t.isdigit() else t.lower() for t in num_re.split(name)]


def is_image_file(name: str, extensions: list[str]) -> bool:
    """Check if filename has one of the allowed extensions.

    Args:
        name: Filename to check
        extensions: List of allowed extensions (e.g., ['.exr', '.png'])
            If empty or None, all files are accepted.

    Returns:
        True if file has allowed extension
    """
    if not extensions:
        return True
    name_lower = name.lower()
    return any(name_lower.endswith(ext) for ext in extensions)


def scan_images(folder: str, extensions: list[str]) -> list[str]:
    """List image filenames in a folder.

    Args:
        folder: Directory to scan
        extensions: List of allowed extensions (empty or None = no filtering)

    Returns:
        List of image filenames (not full paths)
    """
    items: list[str] = []
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and is_image_file(entry.name, extensions):
                items.append(entry.name)
    except FileNotFoundError:
        pass
    return items


def build_output_path(src_full: str, out_folder: str, prefix: str) -> str:
    """Build output path by prepending prefix to filename.

    Args:
        src_full: Source file path
        out_folder: Output directory
        prefix: Prefix to add to filename

    Returns:
        Full output path

    Raises:
        ValueError: If output path would escape output folder
    """
    base = Path(src_full).name
    dst_name = f"{prefix}{base}"

    # Security: validate output path doesn't escape output folder
    out_folder_path = Path(out_folder)
    output_path = out_folder_path / dst_name

    resolved_output = output_path.resolve(strict=False)
    resolved_out_folder = out_folder_path.resolve(strict=False)

    try:
        resolved_output.relative_to(resolved_out_folder)
    except ValueError:
        raise ValueError(f"Output path {output_path} would escape output folder")

    return str(output_path)


def compute_output_folder(in_path: str, extensions: list[str]) -> str:
    """Compute output folder as 'denoised' subfolder next to input.

    Args:
        in_path: Input file or folder path
        extensions: List of file extensions (unused, for API compatibility)

    Returns:
        Path to output folder
    """
    input_path = Path(in_path)
    if input_path.is_dir():
        base_dir = input_path
    elif input_path.parent != Path("."):
        base_dir = input_path.parent
    else:
        base_dir = Path.cwd()

    out = base_dir / "denoised"
    out.mkdir(parents=True, exist_ok=True)
    return out.as_posix()
