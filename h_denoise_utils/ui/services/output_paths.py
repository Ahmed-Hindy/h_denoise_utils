"""Output path helpers (no UI dependencies)."""

import os


def preview_output_path(input_path, selected_root):
    # type: (str, str) -> str
    path = selected_root or (input_path or "").strip()
    if not path:
        return ""
    base_dir = path if os.path.isdir(path) else (os.path.dirname(path) or "")
    if not base_dir:
        return ""
    return os.path.normpath(os.path.join(base_dir, "denoised"))
