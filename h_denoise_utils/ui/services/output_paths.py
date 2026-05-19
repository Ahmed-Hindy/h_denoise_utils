"""Output path helpers (no UI dependencies)."""

import os


def preview_output_path(input_path: str, selected_root: str) -> str:
    """Compute the preview directory where denoised images will be saved.

    Args:
        input_path: Path of the input directory or file.
        selected_root: Optional user-override output directory root.

    Returns:
        str: Normalized path to the output directory, or empty string if input
            is invalid.
    """
    path = selected_root or (input_path or "").strip()
    if not path:
        return ""
    base_dir = path if os.path.isdir(path) else (os.path.dirname(path) or "")
    if not base_dir:
        return ""
    return os.path.normpath(os.path.join(base_dir, "denoised"))
