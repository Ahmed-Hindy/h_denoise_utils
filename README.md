# h_denoise_utils

A Python GUI and scripting library for denoising multipart EXR sequences using a bundled NVIDIA OptiX denoiser.

[![CI](https://github.com/Ahmed-Hindy/h_denoise_utils/actions/workflows/ci.yml/badge.svg)](https://github.com/Ahmed-Hindy/h_denoise_utils/actions)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

![h_denoise_utils app screenshot](docs/assets/app-screenshot.png)

---

## What it does

- Batch denoise EXR image sequences (single files or whole folders)
- Auto-detect AOVs from EXR files and pick sensible defaults
- Run without Houdini — Qt binding is auto-detected
- Full GUI with dark theme, or use the scripting API headlessly
- Preserve source OpenEXR metadata while denoising selected multipart AOVs

---

## Setup

Requires [uv](https://docs.astral.sh/uv/) for development. The Windows OptiX package bundles the denoiser executable.

```bash
git clone https://github.com/Ahmed-Hindy/h_denoise_utils.git
cd h_denoise_utils
uv sync --extra pyside6   # or --extra pyside2 / --extra pyqt5
```

No Qt dependency is required if you only use the scripting API.

---

## Usage

**GUI:**
```bash
uv run h-denoise
# or
python -m h_denoise_utils
```

**Scripting:**
```python
from h_denoise_utils.core.denoiser import Denoiser
from h_denoise_utils.core.config import DenoiseConfig, AOVConfig

denoiser = Denoiser(
    input_path="/path/to/renders",
    denoise_config=DenoiseConfig(backend="optix", prefix="den_"),
    aov_config=AOVConfig(beauty_plane="C", normal_plane="N", albedo_plane="albedo"),
)

prep = denoiser.prepare()
if prep["status"] == "ready":
    for i in range(len(denoiser.files)):
        denoiser.denoise_one(i)
    denoiser.cleanup()
```

---

## Documentation

- [Getting started](docs/getting-started.md)
- [Codebase tour](docs/codebase-tour.md)
- [Architecture](docs/architecture.md)
- [Common tasks](docs/common-tasks.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## Package layout

```
h_denoise_utils/
├── core/          # DenoiseConfig, AOVConfig, command builder, batch denoiser
├── discovery/     # Bundled denoiser lookup, EXR plane inspection, AOV validation
├── utils/         # File scanning, output path helpers, subprocess wrappers
├── ui/            # Qt GUI (main window, sections, custom widgets, dark stylesheet)
└── logger.py      # Standalone logging setup (console + rotating file)
```

---

## Running tests

```bash
uv sync --extra dev --extra pyside6
uv run pytest
```

---

## Requirements

- Python 3.7+
- Bundled OptiX Windows package, or `HDU_DENOISER_EXE` pointing at `Denoiser.exe`
- One of: PySide6, PySide2, PyQt6, PyQt5 — for the GUI only

---

## License

[MIT](LICENSE)
