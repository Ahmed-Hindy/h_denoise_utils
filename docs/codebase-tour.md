# Codebase Tour

Use this as a quick map of where to look for common logic.

## Top-level layout

- `ui/`: Qt UI and UI-specific helpers.
- `core/`: Pure denoise logic and configs.
- `discovery/`: Houdini/EXR discovery helpers.
- `utils/`: File and process helpers.
- `tests/`: Unit and UI smoke tests.

## Key files by responsibility

### UI

- `ui/main_window.py`: Main window wiring and high-level workflow.
- `ui/sections.py`: Widget construction for each UI section.
- `ui/state.py`: Lightweight UI state containers.
- `ui/aov_scan_manager.py`: AOV scan worker and timeout control.
- `ui/worker.py`: Denoise worker thread.

### Core

- `core/denoiser.py`: Orchestrates denoise runs (prepare, denoise, cleanup).
- `core/config.py`: Config dataclasses and validation rules.
- `core/command_builder.py`: Builds `idenoise` CLI command lines.

### Discovery + Utilities

- `discovery/exr_inspector.py`: EXR plane inspection.
- `discovery/houdini.py`: Houdini install discovery.
- `utils/file_utils.py`: File scanning, output paths.
- `utils/process_utils.py`: Subprocess execution.

## Suggested reading order

1) `ui/main_window.py` (entry points + flow).
2) `ui/sections.py` (UI structure).
3) `ui/aov_scan_manager.py` and `ui/services/aov_inspector.py` (AOV scan).
4) `ui/worker.py` and `core/denoiser.py` (denoise pipeline).
