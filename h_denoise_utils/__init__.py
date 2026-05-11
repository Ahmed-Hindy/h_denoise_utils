"""
h_denoise_utils - Houdini Image Denoising Utilities

A modular package for denoising images using Houdini's idenoise utility.
Supports Intel OIDN and NVIDIA OptiX backends.
"""

# Core exports
from .core.config import (
    AOVConfig,
    DenoiseConfig,
    normalize_plane_name,
    is_beauty_plane,
    DEFAULT_INPUT_EXTS,
    AOVS_NEVER_DENOISE,
    BEAUTY_AOV_ALIASES,
    PRESETS,
)
from .core.command_builder import (
    build_idenoise_command,
    override_normal_plane,
)

# Discovery exports
from .discovery.houdini import (
    detect_houdini_versions,
    detect_default_denoiser,
    get_denoiser_from_running_houdini,
    detect_default_oiiotool,
    get_oiiotool_from_running_houdini,
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

__version__ = "2.0.0"
__all__ = [
    # Config
    "AOVConfig",
    "DenoiseConfig",
    "normalize_plane_name",
    "is_beauty_plane",
    "DEFAULT_INPUT_EXTS",
    "AOVS_NEVER_DENOISE",
    "BEAUTY_AOV_ALIASES",
    "PRESETS",
    # Command building
    "build_idenoise_command",
    "override_normal_plane",
    # Discovery
    "detect_houdini_versions",
    "detect_default_denoiser",
    "get_denoiser_from_running_houdini",
    "detect_default_oiiotool",
    "get_oiiotool_from_running_houdini",
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
