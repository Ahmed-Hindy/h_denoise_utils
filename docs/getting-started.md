# Getting Started

This page gets a developer from zero to running the UI and tests.

## Prerequisites

- Python 3.7+.
- `uv` installed (recommended).
- Houdini `idenoise` available on the machine for real denoise runs.

## Install deps (local venv)

From the repo root:

```powershell
uv sync --extra dev --extra pyside6
```

## Run the GUI

From the repo root:

```powershell
uv run h-denoise
```

If you need to force the Qt backend:

```powershell
$env:QT_BACKEND="PySide6"
uv run h-denoise
```

## Run tests

```powershell
uv run pytest --tb=short -v
```

## First-time sanity checks

- The UI opens without exceptions.
- A test EXR folder scans AOVs without timing out.
- Clicking Denoise starts a run (use a small folder first).

