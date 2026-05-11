"""Houdini installation discovery utilities."""

import glob
import os
from typing import Dict, Optional


def detect_houdini_versions() -> Dict[str, str]:
    """Detect installed Houdini versions and return idenoise paths.

    Scans common installation directories for Houdini and returns a mapping
    of version names to idenoise executable paths.

    Returns:
        Dict[str, str]: Mapping of Houdini folder names to idenoise paths.
            Example: {'Houdini 20.5.332': 'C:/Program Files/.../idenoise.exe'}
    """
    installs = {}  # type: Dict[str, str]

    # Windows
    win_base = r"C:\Program Files\Side Effects Software"
    if os.path.exists(win_base):
        for path in glob.glob(os.path.join(win_base, "Houdini*")):
            exe = os.path.join(path, "bin", "idenoise.exe")
            if os.path.isfile(exe):
                installs[os.path.basename(path)] = exe

    # Linux
    for path in glob.glob("/opt/hfs*"):
        exe = os.path.join(path, "bin", "idenoise")
        if os.path.isfile(exe):
            installs[os.path.basename(path)] = exe

    # macOS
    for path in glob.glob("/Applications/Houdini/Houdini*"):
        exe = os.path.join(path, "Contents", "MacOS", "idenoise")
        if os.path.isfile(exe):
            installs[os.path.basename(path)] = exe

    # Sort by version (newest first)
    return dict(sorted(installs.items(), reverse=True))


def get_denoiser_from_running_houdini() -> Optional[str]:
    """Get idenoise path from currently running Houdini session.

    Returns:
        Optional[str]: Path to idenoise if Houdini is running, None otherwise
    """
    try:
        hfs = os.environ.get("HFS")
        if not hfs:
            return None
        exe = "idenoise.exe" if os.name == "nt" else "idenoise"
        path = os.path.join(hfs, "bin", exe)
        return path if os.path.isfile(path) else None
    except Exception:
        return None


def detect_default_denoiser() -> Optional[str]:
    """Detect the default (newest) idenoise executable.

    Returns:
        Optional[str]: Path to newest idenoise, or None if not found
    """
    installs = detect_houdini_versions()
    if installs:
        return next(iter(installs.values()))
    return None


def get_oiiotool_from_running_houdini() -> Optional[str]:
    """Get oiiotool path from currently running Houdini session.

    Returns:
        Optional[str]: Path to oiiotool if Houdini is running, None otherwise
    """
    try:
        hfs = os.environ.get("HFS")
        if not hfs:
            return None
        # Houdini's OIIO tool is named hoiiotool
        exe = "hoiiotool.exe" if os.name == "nt" else "hoiiotool"
        path = os.path.join(hfs, "bin", exe)
        return path if os.path.isfile(path) else None
    except Exception:
        return None


def detect_default_oiiotool() -> Optional[str]:
    """Detect the default (newest) oiiotool executable.

    Scans common Houdini installation directories for hoiiotool
    (Houdini's bundled OpenImageIO tools).

    Returns:
        Optional[str]: Path to newest hoiiotool, or None if not found
    """
    candidates = []

    # Windows
    win_base = r"C:\Program Files\Side Effects Software"
    if os.path.exists(win_base):
        for path in glob.glob(os.path.join(win_base, "Houdini*")):
            exe = os.path.join(path, "bin", "hoiiotool.exe")
            if os.path.isfile(exe):
                candidates.append((os.path.basename(path), exe))

    # Linux
    for path in glob.glob("/opt/hfs*"):
        exe = os.path.join(path, "bin", "hoiiotool")
        if os.path.isfile(exe):
            candidates.append((os.path.basename(path), exe))

    # macOS
    for path in glob.glob("/Applications/Houdini/Houdini*"):
        exe = os.path.join(path, "Contents", "MacOS", "hoiiotool")
        if os.path.isfile(exe):
            candidates.append((os.path.basename(path), exe))

    if not candidates:
        return None

    # Sort by version name (newest first)
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]
