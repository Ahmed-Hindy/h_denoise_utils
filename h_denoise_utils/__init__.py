"""
h_denoise_utils - Bundled Image Denoising Utilities

A modular package for denoising multipart EXRs with bundled OptiX and OIDN
Denoiser.exe runtimes.
"""

from ._version import __version__

# Core exports
from .core.config import (
    AOVConfig,
    DenoiseConfig,
    SUPPORTED_BACKENDS,
    normalize_plane_name,
    is_beauty_plane,
    DEFAULT_INPUT_EXTS,
    AOVS_NEVER_DENOISE,
    BEAUTY_AOV_ALIASES,
    PRESETS,
)
from .core.command_builder import (
    build_bundled_multipart_command,
    build_bundled_optix_command,
    build_oidn_denoise_command,
)

# Discovery exports
from .discovery.bundled_denoiser import (
    DEFAULT_OPTIX_VERSION,
    ENV_OPTIX_VERSION,
    PINNED_DENOISER_COMMIT,
    PINNED_DENOISER_RELEASE,
    PINNED_OPTIX_SDK_COMMITS,
    SUPPORTED_OPTIX_VERSIONS,
    available_bundled_denoisers,
    resolve_bundled_denoiser,
)
from .discovery.bundled_oidn import (
    DEFAULT_OIDN_PLATFORM,
    ENV_OIDN_DENOISER_EXE,
    ENV_OIDN_ROOT,
    PINNED_OIDN_RELEASE,
    PINNED_OIDN_DENOISER_RELEASE,
    PINNED_OIDN_VERSION,
    PINNED_OIDN_WINDOWS_ASSET,
    SUPPORTED_OIDN_PLATFORMS,
    available_bundled_oidn_runtimes,
    bundled_oidn_denoise_path,
    bundled_oidn_denoiser_path,
    bundled_oidn_root,
    resolve_bundled_oidn_denoise,
    resolve_bundled_oidn_denoiser,
)
from .discovery.exr_inspector import list_exr_planes
from .discovery.aov_validator import validate_aov_exists, filter_existing_aovs

# Utils exports
from .utils.process_utils import get_subprocess_config, run_subprocess
from .utils.file_utils import (
    natural_sort_key,
    is_image_file,
    scan_images,
    build_output_path,
    compute_output_folder,
)

__all__ = [
    # Config
    "AOVConfig",
    "DenoiseConfig",
    "SUPPORTED_BACKENDS",
    "normalize_plane_name",
    "is_beauty_plane",
    "DEFAULT_INPUT_EXTS",
    "AOVS_NEVER_DENOISE",
    "BEAUTY_AOV_ALIASES",
    "PRESETS",
    # Command building
    "build_bundled_multipart_command",
    "build_bundled_optix_command",
    "build_oidn_denoise_command",
    # Discovery
    "DEFAULT_OPTIX_VERSION",
    "ENV_OPTIX_VERSION",
    "PINNED_DENOISER_COMMIT",
    "PINNED_DENOISER_RELEASE",
    "PINNED_OPTIX_SDK_COMMITS",
    "SUPPORTED_OPTIX_VERSIONS",
    "available_bundled_denoisers",
    "resolve_bundled_denoiser",
    "DEFAULT_OIDN_PLATFORM",
    "ENV_OIDN_DENOISER_EXE",
    "ENV_OIDN_ROOT",
    "PINNED_OIDN_RELEASE",
    "PINNED_OIDN_DENOISER_RELEASE",
    "PINNED_OIDN_VERSION",
    "PINNED_OIDN_WINDOWS_ASSET",
    "SUPPORTED_OIDN_PLATFORMS",
    "available_bundled_oidn_runtimes",
    "bundled_oidn_denoise_path",
    "bundled_oidn_denoiser_path",
    "bundled_oidn_root",
    "resolve_bundled_oidn_denoise",
    "resolve_bundled_oidn_denoiser",
    "list_exr_planes",
    "validate_aov_exists",
    "filter_existing_aovs",
    # Utils
    "get_subprocess_config",
    "run_subprocess",
    "natural_sort_key",
    "is_image_file",
    "scan_images",
    "build_output_path",
    "compute_output_folder",
    # UI
    "show_ui",
]


def show_ui():
    """Show the denoiser GUI window.

    Returns:
        DenoiserWindow instance
    """
    from .ui.main_window import show

    return show()
