"""Tooltip strings for the denoiser GUI.

Static strings are module-level constants. Dynamic tooltips use the format
templates below or the small helper functions at the bottom of this module.
"""

# Source
PATH_EDIT = "Path to an image file or a folder containing images."
BROWSE_BTN = "Browse for folder"
SCAN_BTN = "Scan input folder for AOVs and auto-configure (F5)"
FILES_LIST = "Files selected for denoising"
FILES_REMOVE_BTN = "Remove selected files from the batch list"
FILES_CLEAR_BTN = "Clear all selected files"
SUMMARY_FILES = "Number of image files in the input path"
SUMMARY_PLANES = "AOV planes detected in the last scan"
SUMMARY_MOTION = (
    "Whether motion-vector AOVs were found (needed for temporal)"
)
SCAN_SPINNER = "Scanning input for AOVs…"
PLANES_TOGGLE = "Count: {} | Last scan: {}"

# Destination
OUTPUT_TOGGLE = "Show or hide destination options"
PRESET_COMBO = "Apply a saved denoise preset (Beauty, Misc, or Custom)"
AOVS_INPUT = (
    "Select which AOV layers to denoise; use the field below for custom names"
)
AOVS_CUSTOM_INPUT = "Comma-separated AOV names not shown as chips"
OVERWRITE_CHK = "Overwrite existing outputs"
OUTPUT_DESTINATION = "Destination: {}"
OUTPUT_DESTINATION_EMPTY = "Destination: -"
ACTION_DESTINATION = "→ {}"

# Settings
ADVANCED_TOGGLE = "Show or hide denoise settings"
ADVANCED_SETTINGS_TOGGLE = "Show or hide idenoise and EXR options"
BACKEND_COMBO = "Oidn = CPU, Optix = GPU (NVIDIA)"
THREAD_SPIN = "CPU threads passed to idenoise (-t)"
PREFIX_EDIT = "Prefix added to output filenames"
ALBEDO_COMBO = (
    "Albedo AOV name; improves quality when present"
)
NORMAL_COMBO = "Normal AOV name; improves quality when present"
MOTION_COMBO = (
    "Motion vectors AOV; required for temporal denoising"
)
TEMPORAL_CHK_ENABLED = (
    "Use previous frame for temporal denoising (OptiX only)"
)
TEMPORAL_CHK_BACKEND_UNSUPPORTED = (
    "Temporal denoising not supported by {}"
)
TEMPORAL_CHK_NO_MOTION = (
    "Requires motion vectors AOV to enable temporal denoising"
)
DENOISER_COMBO = "Houdini idenoise executable to run"
CUSTOM_EXE_BTN = "Browse for a custom idenoise executable"
EXRMODE_COMBO = (
    "HOUDINI_OIIO_EXR read mode (-1, 0, or 1); default uses env var"
)
OPTIONS_EDIT = (
    "JSON options passed to idenoise (e.g. blendfactor, auxareclean)"
)
OPTIONS_INVALID_JSON = "Invalid JSON: {}"
EXTRA_AOVS_EDIT = "Reference AOVs included but not denoised"

# Action bar
CONTROL_BTN_START = "Start denoising"
CONTROL_BTN_STOP = "Stop the running denoise"
PROGRESS = "Overall progress"
PROGRESS_LABEL = "Current file index and estimated time remaining"
OPEN_OUTPUT_BTN = "Open destination folder"

# Logs
LOG_FILTER_COMBO = "Filter log messages by severity"


def planes_toggle(count, timestamp):
    # type: (int, str) -> str
    return PLANES_TOGGLE.format(count, timestamp)


def temporal_backend_unsupported(backend_display):
    # type: (str) -> str
    return TEMPORAL_CHK_BACKEND_UNSUPPORTED.format(backend_display)


def options_invalid_json(exc):
    # type: (object) -> str
    return OPTIONS_INVALID_JSON.format(exc)


def output_destination_label(preview_path):
    # type: (str) -> str
    if preview_path:
        return OUTPUT_DESTINATION.format(preview_path)
    return OUTPUT_DESTINATION_EMPTY


def action_destination_label(preview_path):
    # type: (str) -> str
    return ACTION_DESTINATION.format(preview_path if preview_path else "-")
