"""Lightweight UI state containers."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InputState:
    path: str = ""
    selected_files: List[str] = field(default_factory=list)
    selected_root: str = ""


@dataclass
class AovState:
    planes: List[str] = field(default_factory=list)
    last_exr: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class DenoiseState:
    backend: str = ""
    idenoise_path: str = ""
    threads: int = 0
    overwrite: bool = False
    prefix: str = ""
    options_json: str = ""
    temporal: bool = False


@dataclass
class UiState:
    scan_busy: bool = False
    is_running: bool = False
    progress_current: int = 0
    progress_total: int = 0
