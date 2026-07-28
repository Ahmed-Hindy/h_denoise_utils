"""Lightweight UI state containers."""

from dataclasses import dataclass, field


@dataclass
class InputState:
    """State container for UI inputs.

    Attributes:
        path: Path to the target file or directory.
        selected_files: List of files selected in the UI list view.
        selected_root: Path override for the output destination root.
    """

    path: str = ""
    selected_files: list[str] = field(default_factory=list)
    selected_root: str = ""


@dataclass
class AovState:
    """State container for resolved AOVs.

    Attributes:
        planes: List of AOV plane names found.
        last_exr: Path to the last parsed EXR file.
        last_error: Error message from the last scan, if any.
    """

    planes: list[str] = field(default_factory=list)
    last_exr: str | None = None
    last_error: str | None = None


@dataclass
class DenoiseState:
    """State container for denoise operation settings.

    Attributes:
        backend: Denoising backend ("optix" or "oidn").
        denoiser_path: Path to the resolved denoiser executable.
        threads: Number of worker threads configured.
        overwrite: Whether to overwrite existing files.
        prefix: Prefix to apply to output filenames.
        options_json: Raw JSON string of advanced configuration options.
        temporal: Whether temporal denoising is enabled.
    """

    backend: str = ""
    denoiser_path: str = ""
    threads: int = 0
    overwrite: bool = False
    prefix: str = ""
    options_json: str = ""
    temporal: bool = False


@dataclass
class UiState:
    """State container for general UI execution properties.

    Attributes:
        scan_busy: Whether an AOV folder scan is in progress.
        is_running: Whether a denoise process is currently running.
        progress_current: Current progress counter (e.g. processed files).
        progress_total: Total files to process in the active job.
    """

    scan_busy: bool = False
    is_running: bool = False
    progress_current: int = 0
    progress_total: int = 0
