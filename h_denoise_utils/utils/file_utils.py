"""File operation utilities."""

import os
import re


def natural_sort_key(name):
    # type: (str) -> List
    """Generate a natural sort key (so '2' < '10').

    Args:
        name: String to generate sort key for

    Returns:
        List of integers and strings for natural sorting
    """
    num_re = re.compile(r"(\d+)")
    return [int(t) if t.isdigit() else t.lower() for t in num_re.split(name)]


def is_image_file(name, extensions):
    # type: (str, List[str]) -> bool
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


def scan_images(folder, extensions):
    # type: (str, List[str]) -> List[str]
    """List image filenames in a folder.

    Args:
        folder: Directory to scan
        extensions: List of allowed extensions (empty or None = no filtering)

    Returns:
        List of image filenames (not full paths)
    """
    items = []  # type: List[str]
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and is_image_file(entry.name, extensions):
                items.append(entry.name)
    except FileNotFoundError:
        pass
    return items


def build_output_path(src_full, out_folder, prefix):
    # type: (str, str, str) -> str
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
    base = os.path.basename(src_full)
    dst_name = "{}{}".format(prefix, base)

    # Security: validate output path doesn't escape output folder
    output_path = os.path.normpath(os.path.join(out_folder, dst_name))
    out_folder_norm = os.path.normpath(out_folder)

    output_path_abs = os.path.normcase(os.path.abspath(output_path))
    out_folder_abs = os.path.normcase(os.path.abspath(out_folder_norm))

    try:
        common = os.path.commonpath([output_path_abs, out_folder_abs])
    except ValueError:
        raise ValueError(
            "Output path {} would escape output folder".format(output_path)
        )

    if common != out_folder_abs:
        raise ValueError(
            "Output path {} would escape output folder".format(output_path)
        )

    return output_path


def compute_output_folder(in_path, extensions):
    # type: (str, List[str]) -> str
    """Compute output folder as 'denoised' subfolder next to input.

    Args:
        in_path: Input file or folder path
        extensions: List of file extensions (unused, for API compatibility)

    Returns:
        Path to output folder
    """
    base_dir = (
        in_path if os.path.isdir(in_path) else (os.path.dirname(in_path) or os.getcwd())
    )
    out = os.path.join(base_dir, "denoised")
    os.makedirs(out, exist_ok=True)
    return out.replace("\\", "/")
