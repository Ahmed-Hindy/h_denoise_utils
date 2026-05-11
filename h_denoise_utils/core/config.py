"""Configuration constants and dataclasses for the denoiser."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# File extensions supported for input
DEFAULT_INPUT_EXTS = [".exr", ".hdr", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"]

# AOVs that should never be denoised (auxiliary data)
AOVS_NEVER_DENOISE: Set[str] = {"albedo", "normal", "n", "velocity", "motionvectors"}

# Common beauty/combined plane names across renderers
BEAUTY_AOV_ALIASES: Set[str] = {"c", "rgba", "rgb", "beauty", "ci"}

# Preset configurations
PRESETS: Dict[str, Dict[str, any]] = {
    "Beauty": {
        "backend": "optix",
        "temporal": True,
        "normal": "normal",
        "albedo": "albedo",
        "motion": "motionvectors",
        "aovs": "",  # empty -> auto-detect from EXR
    },
    "Misc": {
        "backend": "optix",
        "temporal": False,
        "normal": "normal",
        "albedo": "",
        "motion": "",
        "aovs": "",  # empty -> auto-detect from EXR
    },
}


@dataclass(frozen=True)
class AOVConfig:
    """Configuration for AOV (Arbitrary Output Variable) processing."""

    normal_plane: Optional[str] = None
    albedo_plane: Optional[str] = None
    motionvectors_plane: Optional[str] = None
    aovs_to_denoise: Optional[List[str]] = None
    extra_aovs: Optional[List[str]] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Convert None to empty list for list fields (immutable workaround)
        if self.aovs_to_denoise is not None and not isinstance(
            self.aovs_to_denoise, list
        ):
            raise TypeError("aovs_to_denoise must be a list or None")
        if self.extra_aovs is not None and not isinstance(self.extra_aovs, list):
            raise TypeError("extra_aovs must be a list or None")


@dataclass(frozen=True)
class DenoiseConfig:
    """Complete configuration for a denoising operation."""

    backend: str = "optix"
    temporal: bool = False
    overwrite: bool = False
    threads: Optional[int] = None
    prefix: str = "den_"
    exrmode: Optional[int] = None
    options_json: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.backend not in ("oidn", "optix"):
            raise ValueError(
                f"Invalid backend: {self.backend}. Must be 'oidn' or 'optix'"
            )
        if self.exrmode is not None and self.exrmode not in (-1, 0, 1):
            raise ValueError(f"Invalid exrmode: {self.exrmode}. Must be -1, 0, or 1")
        if self.threads is not None and self.threads < 1:
            raise ValueError(f"Invalid threads: {self.threads}. Must be >= 1")


def normalize_plane_name(plane: Optional[str]) -> str:
    """Normalize plane name to lowercase stripped string.

    Args:
        plane: Plane name to normalize

    Returns:
        Normalized plane name (lowercase, stripped)
    """
    if plane is None:
        return ""
    return str(plane).strip().lower()


def is_beauty_plane(plane: Optional[str]) -> bool:
    """Return True if the plane name matches a common beauty alias.

    Args:
        plane: Plane name to check

    Returns:
        True if the plane is a known beauty/combined plane name
    """
    if plane is None:
        return False
    name = normalize_plane_name(plane)
    if not name:
        return False
    base = name.rsplit(".", 1)[-1]
    return base in BEAUTY_AOV_ALIASES
