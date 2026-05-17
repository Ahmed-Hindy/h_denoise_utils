"""Bundled OptiX denoiser discovery."""

import os
import sys
from pathlib import Path
from typing import Optional

PINNED_DENOISER_COMMIT = "8893b605903f273512b750d45993bbe27a003362"
ENV_DENOISER_EXE = "HDU_DENOISER_EXE"


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def bundled_denoiser_path() -> Path:
    exe_name = "Denoiser.exe" if os.name == "nt" else "Denoiser"
    return _package_root() / "vendor" / "optix-denoiser" / "windows-x64" / exe_name


def resolve_bundled_denoiser(required: bool = True) -> Optional[str]:
    override = os.environ.get(ENV_DENOISER_EXE, "").strip()
    if override:
        override_path = Path(override)
        if override_path.is_file():
            return str(override_path)
        if required:
            raise FileNotFoundError(
                f"{ENV_DENOISER_EXE} points to a missing denoiser: {override}"
            )
        return None

    candidate = bundled_denoiser_path()
    if candidate.is_file():
        return str(candidate)

    if required:
        if os.name != "nt":
            raise FileNotFoundError(
                "Bundled OptiX denoising is currently available only in the "
                "Windows package."
            )
        location = getattr(sys, "_MEIPASS", None) or str(_package_root())
        raise FileNotFoundError(
            "Bundled OptiX Denoiser.exe was not found. Expected it under "
            f"{candidate}. Package root: {location}"
        )
    return None
