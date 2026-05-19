# h_denoise_utils

A Python GUI and scripting library for denoising multipart EXR sequences using bundled OptiX or OIDN denoiser runtimes.

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
- Bundle OptiX 8.1, 9.0, and 9.1 denoiser runtimes in the Windows package
- Bundle a custom Intel OIDN 2.4.1 multipart wrapper with the same `Denoiser.exe`
  CLI contract as OptiX

---

## Setup

Requires [uv](https://docs.astral.sh/uv/) for development. The Windows bundled package includes the OptiX and OIDN denoiser executables.

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
- [OIDN bundling notes](docs/oidn-bundling.md)

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
- Bundled Windows package, or `HDU_DENOISER_EXE` / `HDU_OIDN_DENOISER_EXE` pointing at custom `Denoiser.exe` builds for development
- Optional runtime selection with `HDU_OPTIX_VERSION=8.1`, `9.0`, or `9.1`; the default is `9.0`
- One of: PySide6, PySide2, PyQt6, PyQt5 — for the GUI only

---

## License

[MIT](LICENSE)
