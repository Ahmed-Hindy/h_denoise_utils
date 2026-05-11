"""EXR file inspection using oiiotool."""

import logging
import os
import re
import subprocess

from .houdini import (
    detect_default_oiiotool,
    get_oiiotool_from_running_houdini,
)
from ..utils.process_utils import get_subprocess_config

logger = logging.getLogger(__name__)


def list_exr_planes(exr_path, oiiotool_path=None):
    # type: (str, Optional[str]) -> List[str]
    """List all plane/AOV names in an EXR file.

    Supports both multipart and layered EXR formats. Returns planes in the
    order they appear in the file (important for beauty pass detection).

    Args:
        exr_path: Path to EXR file
        oiiotool_path: Optional path to oiiotool executable

    Returns:
        List of plane names in order of appearance

    Examples:
        >>> planes = list_exr_planes("render.exr")
        >>> print(planes)
        ['C', 'diffuse', 'specular', 'N']
    """
    if not os.path.isfile(exr_path):
        logger.warning("EXR file not found: %s", exr_path)
        return []

    oiiotool = (
        oiiotool_path
        or get_oiiotool_from_running_houdini()
        or detect_default_oiiotool()
    )
    if not oiiotool or not os.path.isfile(oiiotool):
        logger.warning("oiiotool not found, cannot list EXR planes for %s", exr_path)
        return []

    cmd = [oiiotool, "--info", "-v", "-a", exr_path]
    startupinfo, creationflags = get_subprocess_config()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.error("oiiotool timeout reading %s", exr_path)
        return []
    except Exception as e:
        logger.error("oiiotool error reading %s: %s", exr_path, e)
        return []

    txt = (proc.stdout or "") + "\n" + (proc.stderr or "")

    # Use dict to preserve order (Python 3.7+)
    planes = {}  # type: Dict[str, None]
    current_subimage_name = None  # type: Optional[str]

    for ln in txt.splitlines():
        # Match: Subimage 0: "beauty"  1920x1080 ...
        m = re.search(r'Subimage\s+\d+\s*:\s*"([^"]*)"', ln)
        if m:
            name = (m.group(1) or "").strip()
            current_subimage_name = name if name else None
            if current_subimage_name:
                planes[current_subimage_name] = None
            continue

        low = ln.lower()
        if ("channels:" in low) or ("channel list" in low):
            parts = ln.split(":", 1)
            chan_text = parts[1] if len(parts) > 1 else ln
            chs = re.findall(r"[A-Za-z0-9_\.]+", chan_text)

            # Multipart: prefer subimage name
            if current_subimage_name:
                continue

            # Layered: extract layer stems (e.g., "diffuse" from "diffuse.R")
            stems = []
            seen = set()
            for c in chs:
                if "." not in c:
                    continue
                stem = c.split(".", 1)[0]
                if stem in seen:
                    continue
                seen.add(stem)
                stems.append(stem)
            if stems:
                for s in stems:
                    planes[s] = None
                continue

            # Fallbacks for simple channel sets
            up = {c.upper() for c in chs}
            if up.issuperset({"R", "G", "B"}):
                planes["C"] = None
            elif up == {"Z"}:
                planes["Z"] = None

    return list(planes.keys())
