# h_denoise_utils Architecture Guide

This guide maps the main modules to responsibilities and shows the core data
flows in the GUI and headless paths. It is intended as a quick orientation for
new contributors.

## Read this first

If you are new to the codebase, start here:

- `ui/main_window.py`: `BaseWindow` and `show()` are the GUI entry points.
- `ui/sections.py`: UI construction for each screen section.
- `ui/aov_scan_manager.py`: AOV scanning workflow and timeout handling.
- `ui/worker.py`: Background denoise execution and progress/log signals.
- `core/denoiser.py`: File discovery + denoise orchestration.
- `core/config.py`: Config dataclasses and validation rules.

## High-level flow (GUI)

```text
User
 |  (path edit / scan)
 v
BaseWindow
 |--> AovScanManager --> aov_inspector (EXR plane scan)
 |            |                  |
 |            +--> AovState/UI updates
 |
 |  (Denoise)
 v
DenoiseWorker --> core.Denoiser
                   |--> command_builder
                   |--> process_utils (idenoise subprocess)
                   +--> file_utils (scan/copy paths)
```

## Module map

### UI layer (`h_denoise_utils.ui`)

- `ui/main_window.py`: The main window shell. Owns UI wiring, high-level
  orchestration, and connects services + state to widgets.
- `ui/sections.py`: Builds the major UI blocks (Source, Destination, Extras,
  Action Bar, Logs). It only creates widgets and layouts.
- `ui/state.py`: Lightweight state containers (input, AOV, UI, denoise).
- `ui/aov_scan_manager.py`: Runs AOV inspection in a worker thread, with
  timeout + stale-result protection.
- `ui/worker.py`: `DenoiseWorker` thread that calls `core.Denoiser` and
  reports progress/logs to the UI.
- `ui/logging_handler.py`: Bridges Python logging into Qt signals for the
  log table.
- `ui/services/*`:
  - `aov_inspector.py`: EXR probing for planes (non-UI).
  - `recent_paths.py`: Load/save recent paths in settings.
  - `output_paths.py`: Output preview path helper.

### Core layer (`h_denoise_utils.core`)

- `core/config.py`: Dataclasses and validation for denoise + AOV configs.
- `core/denoiser.py`: Pure denoise orchestration (file discovery, temp
  workspace, AOV validation, command execution).
- `core/command_builder.py`: Builds `idenoise` command lines from config.

### Discovery layer (`h_denoise_utils.discovery`)

- `houdini.py`: Detects Houdini installs and default tools.
- `exr_inspector.py`: Reads EXR plane/channel information.
- `aov_validator.py`: Filters AOVs based on EXR contents.

### Utilities (`h_denoise_utils.utils`)

- `file_utils.py`: File scanning, sorting, and output path helpers.
- `process_utils.py`: Subprocess execution helpers.

### Scripting path

- `core/denoiser.py`: Headless API for batch denoise runs without Qt.
- `core/config.py`: `DenoiseConfig` and `AOVConfig` inputs for scripted use.

## Main data flows

### AOV scan flow (GUI)

1) User edits Source Path or clicks Scan.
2) `BaseWindow._analyze_input` resolves the effective input path and starts
   `AovScanManager`.
3) `AovScanManager` runs `ui/services/aov_inspector.analyze_aovs` in a
   worker thread and emits `completed` or `timed_out`.
4) `BaseWindow._on_aov_analysis_complete` updates `AovState` and refreshes
   the AOV widgets (chips, combos, preview).

### Denoise run flow (GUI)

1) User clicks Denoise.
2) `BaseWindow._start_denoise` collects UI selections into
   `DenoiseConfig` + `AOVConfig`.
3) `DenoiseWorker` runs in the background, calls `core.Denoiser` to
   prepare and denoise each file.
4) Progress + logs are emitted back to the UI; summary is shown on finish.

## Reading order recommendations

1) `ui/main_window.py`: Start at `BaseWindow.__init__`, then follow
   `_setup_ui` -> `ui/sections.py` and `_connect_signals`.
2) `ui/aov_scan_manager.py` and `ui/services/aov_inspector.py` for AOV
   detection behavior.
3) `ui/worker.py` then `core/denoiser.py` for the denoise pipeline.
4) `core/config.py` and `core/command_builder.py` for config validation
   and command generation.

