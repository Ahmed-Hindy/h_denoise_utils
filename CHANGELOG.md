# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] — 2026-05-11

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
