# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2.0] — 2026-05-15

### Added
- Window title shows the installed package version (and `(DEV)` when `ENV_IS_DEV=true`).
- README screenshot and documentation links.
- GitHub Releases upload for the Windows portable zip when a `v*` tag is pushed.

### Changed
- Refined denoiser UI layout: status summary strip, destination preview in the action bar, and shared configuration scroll area.
- Advanced settings collapsed into expandable sections (basic vs. advanced rows).
- UI copy renamed from "planes" to "AOVs" for consistency.
- About dialog reads version from `__version__` instead of a hardcoded string.
- CI: updated GitHub Actions runtimes and artifact upload action; pinned Windows packaging to `windows-2022`.

### Fixed
- Avoid duplicate AOV scans when the input path is re-analyzed without changes.

## [1.1.0] — 2026-05-12

### Added
- Windows portable packaging with PyInstaller and `PySide6-Essentials`.
- GitHub Actions packaging job that uploads a Windows zip artifact on every push.
- CLI `--version` and `--smoke-test` checks for release and frozen-app validation.

### Changed
- Explicitly include Qt stylesheet and icon assets in built wheels.

## [1.0.0] — 2026-05-11

### Added
- Modular package structure: `core/`, `discovery/`, `ui/`, `utils/`.
- Full Qt compatibility layer (`qt_compat.py`): PySide6, PySide2, PyQt6, PyQt5.
- Dark-themed Qt GUI with AOV chip grid, Settings tab, and Help menu.
- Background denoising via `QThread`-based worker.
- Auto-detection of installed Houdini versions and `idenoise` / `hoiiotool` paths.
- EXR plane inspection and AOV validation.
- `uv`-based project setup with optional Qt dependency extras.
- `h-denoise` CLI entry point.
- GitHub Actions CI (pytest on Python 3.9, 3.11, 3.12).
