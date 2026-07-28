"""Configuration constants and dataclasses for the denoiser."""

from dataclasses import dataclass
from typing import Any

# File extensions supported by the bundled multipart denoiser path.
DEFAULT_INPUT_EXTS = [".exr"]

# Backends known to the public configuration surface.
SUPPORTED_BACKENDS = ("optix", "oidn")

# AOVs that should never be denoised (auxiliary data)
AOVS_NEVER_DENOISE: set[str] = {"albedo", "normal", "n", "velocity", "motionvectors"}

# Common beauty/combined plane names across renderers
BEAUTY_AOV_ALIASES: set[str] = {"c", "rgba", "rgb", "beauty", "ci"}

# Preset configurations
PRESETS: dict[str, dict[str, Any]] = {
    "Beauty": {
        "backend": "optix",
        "temporal": False,
        "beauty": "C",
        "normal": "N",
        "albedo": "albedo",
        "aovs": "",  # empty -> auto-detect from EXR
    },
    "Misc": {
        "backend": "optix",
        "temporal": False,
        "beauty": "C",
        "normal": "N",
        "albedo": "",
        "aovs": "",  # empty -> auto-detect from EXR
    },
}


@dataclass(frozen=True)
class AOVConfig:
    """Configuration for AOV (Arbitrary Output Variable) processing."""

    beauty_plane: str | None = "C"
    normal_plane: str | None = None
    albedo_plane: str | None = None
    motionvectors_plane: str | None = None
    aovs_to_denoise: list[str] | None = None
    extra_aovs: list[str] | None = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Convert None to empty list for list fields (immutable workaround)
        if self.aovs_to_denoise is not None and not isinstance(self.aovs_to_denoise, list):
            raise TypeError("aovs_to_denoise must be a list or None")
        if self.extra_aovs is not None and not isinstance(self.extra_aovs, list):
            raise TypeError("extra_aovs must be a list or None")


@dataclass(frozen=True)
class DenoiseConfig:
    """Complete configuration for a denoising operation."""

    backend: str = "optix"
    temporal: bool = False
    overwrite: bool = False
    threads: int | None = None
    prefix: str = "den_"
    exrmode: int | None = None
    options_json: str | None = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.backend not in SUPPORTED_BACKENDS:
            raise ValueError(
                "Invalid backend: {}. Must be one of: {}".format(
                    self.backend, ", ".join(SUPPORTED_BACKENDS)
                )
            )
        if self.exrmode is not None and self.exrmode not in (-1, 0, 1):
            raise ValueError(f"Invalid exrmode: {self.exrmode}. Must be -1, 0, or 1")
        if self.threads is not None and self.threads < 1:
            raise ValueError(f"Invalid threads: {self.threads}. Must be >= 1")


def normalize_plane_name(plane: str | None) -> str:
    """Normalize plane name to lowercase stripped string.

    Args:
        plane: Plane name to normalize

    Returns:
        Normalized plane name (lowercase, stripped)
    """
    if plane is None:
        return ""
    return str(plane).strip().lower()


def is_beauty_plane(plane: str | None) -> bool:
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
