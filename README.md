# h_denoise_utils

Standalone EXR denoising for artists and pipeline users.

[![CI](https://github.com/Ahmed-Hindy/h_denoise_utils/actions/workflows/ci.yml/badge.svg)](https://github.com/Ahmed-Hindy/h_denoise_utils/actions)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)
![OptiX](https://img.shields.io/badge/OptiX-8.1%20%7C%209.0%20%7C%209.1-76B900?logo=nvidia)
![C++](https://img.shields.io/badge/C%2B%2B-20-blue)
[![Python 3.11 | 3.13](https://img.shields.io/badge/Python-3.11%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

https://github.com/user-attachments/assets/477eec96-684d-40f9-ad18-7ba86055a467

## What It Does

- Denoises OpenEXR image sequences.
- Denoises most AOVs.
- Supports bundled OptiX and Intel OIDN denoiser.
- Does not require Houdini.

## Download

For most users, download the latest Windows package from
[Releases](https://github.com/Ahmed-Hindy/h_denoise_utils/releases).

Look for:

```text
h-denoise-bundled-windows-x64-vX.Y.Z.zip
```

Unzip it, then run the included app.

## Run From Source

```bash
git clone https://github.com/Ahmed-Hindy/h_denoise_utils.git
cd h_denoise_utils
uv sync --extra pyside6
uv run h-denoise
```

Python 3.11 is the default. Python 3.13 is also supported; Python 3.12 is intentionally excluded.
To use PyQt6 instead of PySide6, run `uv sync --extra pyqt6`.

## Command Line

```bash
uv run h-denoise /path/to/renders --backend optix --optix-version 9.0
uv run h-denoise /path/to/input.exr --backend oidn
```

## More Help

- [Getting started](docs/getting-started.md)
- [Common tasks](docs/common-tasks.md)
- [Release package details](docs/release-variants.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

[MIT](LICENSE)
