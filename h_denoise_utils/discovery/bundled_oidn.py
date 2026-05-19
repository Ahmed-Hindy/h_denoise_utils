"""Bundled custom Intel Open Image Denoise wrapper discovery."""

import os
import sys
from pathlib import Path
from typing import Dict, Optional

PINNED_OIDN_VERSION = "2.4.1"
PINNED_OIDN_RELEASE = "v2.4.1"
PINNED_OIDN_WINDOWS_ASSET = "oidn-2.4.1.x64.windows.zip"
PINNED_OIDN_DENOISER_RELEASE = "v*"

DEFAULT_OIDN_PLATFORM = "windows-x64"
SUPPORTED_OIDN_PLATFORMS = (DEFAULT_OIDN_PLATFORM,)


def _package_root() -> Path:
    """Retrieve the root directory of the package.

    Returns:
        Path: The package root path.
    """
    return Path(__file__).resolve().parents[1]


def _oidn_vendor_dir() -> Path:
    """Get the base vendor directory for OIDN.

    Returns:
        Path: Path to the vendor directory.
    """
    return _package_root() / "vendor" / "oidn-denoiser"


def _normalize_platform(platform: Optional[str] = None) -> str:
    """Normalize the platform name and validate it.

    Args:
        platform: Optional platform identifier (e.g. "windows-x64").

    Returns:
        str: Normalized platform identifier.

    Raises:
        ValueError: If the platform is not supported.
    """
    value = (platform or DEFAULT_OIDN_PLATFORM).strip().lower()
    if value not in SUPPORTED_OIDN_PLATFORMS:
        allowed = ", ".join(SUPPORTED_OIDN_PLATFORMS)
        raise ValueError(
            f"Unsupported OIDN runtime platform '{platform}'. Expected one of: {allowed}."
        )
    return value


def bundled_oidn_root(platform: Optional[str] = None) -> Path:
    """Get the root directory of the bundled OIDN installation.

    Args:
        platform: Optional platform filter.

    Returns:
        Path: Path to the bundled OIDN root folder.
    """
    platform_key = _normalize_platform(platform)
    return _oidn_vendor_dir() / platform_key / f"oidn-{PINNED_OIDN_VERSION}"


def bundled_oidn_denoiser_path(platform: Optional[str] = None) -> Path:
    """Get the path to the bundled OIDN denoiser wrapper executable.

    Args:
        platform: Optional platform filter.

    Returns:
        Path: Path to the bundled denoiser executable.
    """
    return bundled_oidn_root(platform) / _exe_name(platform)


def bundled_oidn_denoise_path(platform: Optional[str] = None) -> Path:
    """Return the custom OIDN wrapper path.

    Kept as a compatibility alias for the earlier stock oidnDenoise resolver.
    """
    return bundled_oidn_denoiser_path(platform)


def _exe_name(platform: Optional[str] = None) -> str:
    """Get the OIDN wrapper executable filename.

    Args:
        platform: Optional platform filter.

    Returns:
        str: The executable name (e.g., "Denoiser.exe" on Windows).
    """
    platform_key = _normalize_platform(platform)
    if platform_key == "windows-x64":
        return "Denoiser.exe"
    return "Denoiser"


def available_bundled_oidn_runtimes() -> Dict[str, Path]:
    """List all available bundled OIDN runtimes.

    Returns:
        Dict[str, Path]: A dictionary mapping platform names to executable paths.
    """
    available = {}
    for platform in SUPPORTED_OIDN_PLATFORMS:
        candidate = bundled_oidn_denoiser_path(platform)
        if candidate.is_file():
            available[platform] = candidate
    return available


def resolve_bundled_oidn_denoiser(
    required: bool = True,
    platform: Optional[str] = None,
) -> Optional[str]:
    """Resolve the path to the bundled OIDN denoiser wrapper.

    Args:
        required: Whether to raise an error if no denoiser is found.
        platform: Optional platform to resolve.

    Returns:
        Optional[str]: The path to the OIDN denoiser, or None.

    Raises:
        FileNotFoundError: If the denoiser is required but not found.
    """
    platform_key = _normalize_platform(platform)
    candidate = bundled_oidn_denoiser_path(platform_key)
    if candidate.is_file():
        return str(candidate)

    if required:
        if os.name != "nt":
            raise FileNotFoundError(
                "Bundled OIDN discovery is currently pinned to the official Windows x64 package."
            )
        location = getattr(sys, "_MEIPASS", None) or str(_package_root())
        raise FileNotFoundError(
            f"Bundled OIDN Denoiser.exe was not found. Expected: {candidate}. "
            "Run tools/fetch_oidn_denoiser.ps1 or tools/build_oidn_denoiser.ps1 first. "
            f"Package root: {location}"
        )
    return None


def resolve_bundled_oidn_denoise(
    required: bool = True,
    platform: Optional[str] = None,
) -> Optional[str]:
    """Compatibility alias for the custom OIDN Denoiser.exe resolver."""
    return resolve_bundled_oidn_denoiser(required=required, platform=platform)
