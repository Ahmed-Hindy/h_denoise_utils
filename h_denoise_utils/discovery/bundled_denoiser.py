"""Bundled OptiX denoiser discovery."""

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

PINNED_DENOISER_RELEASE = "optix-denoiser-v2026.05.18"
PINNED_DENOISER_COMMIT = "fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf"
PINNED_OPTIX_SDK_COMMITS = {
    "8.1": "50021ea0af6d41609a97777ceebbdf1e1d34efe7",
    "9.0": "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd",
    "9.1": "f1f6dd803f3159992d248178f6e09421c6eb8b6d",
}

SUPPORTED_OPTIX_VERSIONS = ("8.1", "9.0", "9.1")
DEFAULT_OPTIX_VERSION = "9.0"
PREFERRED_OPTIX_VERSIONS = (
    DEFAULT_OPTIX_VERSION,
    "8.1",
    "9.1",
)


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _denoiser_base_dir() -> Path:
    return _package_root() / "vendor" / "optix-denoiser" / "windows-x64"


def _exe_name() -> str:
    return "Denoiser.exe"


def _normalize_optix_version(optix_version: str) -> str:
    value = optix_version.strip()
    if value.lower().startswith("optix-"):
        value = value[6:]
    if value not in SUPPORTED_OPTIX_VERSIONS:
        allowed = ", ".join(SUPPORTED_OPTIX_VERSIONS)
        raise ValueError(
            f"Unsupported OptiX runtime '{optix_version}'. Expected one of: {allowed}."
        )
    return value


def _requested_optix_version(optix_version: Optional[str]) -> Tuple[str, bool]:
    if optix_version is not None:
        return _normalize_optix_version(optix_version), True

    return DEFAULT_OPTIX_VERSION, False


def legacy_bundled_denoiser_path() -> Path:
    """Return the pre-multiruntime bundled denoiser path."""
    return _denoiser_base_dir() / _exe_name()


def bundled_denoiser_path(optix_version: Optional[str] = None) -> Path:
    version, _explicit = _requested_optix_version(optix_version)
    return _denoiser_base_dir() / f"optix-{version}" / _exe_name()


def available_bundled_denoisers() -> Dict[str, Path]:
    available = {}
    for version in SUPPORTED_OPTIX_VERSIONS:
        candidate = bundled_denoiser_path(version)
        if candidate.is_file():
            available[version] = candidate
    return available


def resolve_bundled_denoiser(
    required: bool = True,
    optix_version: Optional[str] = None,
) -> Optional[str]:
    version, explicit_version = _requested_optix_version(optix_version)
    candidate = bundled_denoiser_path(version)
    if candidate.is_file():
        return str(candidate)

    if not explicit_version:
        for fallback_version in PREFERRED_OPTIX_VERSIONS:
            if fallback_version == version:
                continue
            fallback = bundled_denoiser_path(fallback_version)
            if fallback.is_file():
                return str(fallback)

    legacy_candidate = legacy_bundled_denoiser_path()
    if legacy_candidate.is_file():
        return str(legacy_candidate)

    if required:
        requested = (
            f"Requested OptiX {version}. "
            if explicit_version
            else f"Default OptiX {DEFAULT_OPTIX_VERSION} was selected. "
        )
        expected = ", ".join(
            str(_denoiser_base_dir() / f"optix-{v}" / _exe_name())
            for v in SUPPORTED_OPTIX_VERSIONS
        )
        if os.name != "nt":
            raise FileNotFoundError(
                "Bundled OptiX denoising is currently available only in the "
                "Windows package."
            )
        location = getattr(sys, "_MEIPASS", None) or str(_package_root())
        raise FileNotFoundError(
            "Bundled OptiX Denoiser.exe was not found. "
            f"{requested}Expected one of: {expected}. Package root: {location}"
        )
    return None
