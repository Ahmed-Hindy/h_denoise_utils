"""AOV inspection utilities (no UI dependencies)."""

import os

from ...discovery.exr_inspector import list_exr_planes
from ...utils.file_utils import scan_images


def find_first_exr(path, selected_files=None):
    # type: (str, Optional[List[str]]) -> Optional[str]
    if selected_files:
        for fname in selected_files:
            if fname.lower().endswith(".exr"):
                return fname
        return None
    if os.path.isfile(path) and path.lower().endswith(".exr"):
        return path
    if os.path.isdir(path):
        files = scan_images(path, [".exr"])
        if files:
            return os.path.join(path, files[0])
    return None


def analyze_aovs(path, selected_files=None):
    # type: (str, Optional[List[str]]) -> Dict[str, object]
    result = {"status": "ok", "exr_file": None, "planes": [], "error": None}
    exr_file = find_first_exr(path, selected_files)
    result["exr_file"] = exr_file
    if not exr_file:
        result["status"] = "no_exr"
        return result
    try:
        planes = list_exr_planes(exr_file, oiiotool_path=None)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    if not planes:
        result["status"] = "no_planes"
        return result
    result["planes"] = planes
    return result
