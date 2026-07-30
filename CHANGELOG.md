# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Native `HOptixDenoise` Nuke `PlanarIop` with beauty, albedo, and normal
  inputs, OptiX tiling, GPU selection, normal encoding, blend, and safe
  passthrough controls.
- Shared in-memory OptiX C++ core built on the CUDA Driver API.
- One-command Windows build, Nuke terminal validation, manifest generation,
  release ZIP packaging, documentation, and self-hosted CI workflow.
- A Nuke playground for comparing live native OptiX nodes with the bundled OIDN
  wrapper on production multipart EXRs, including guide extraction, differences,
  write nodes, runtime selection, and a PowerShell launcher.

### Changed
- Nuke nodes now retain a thread-safe OptiX session and reuse compatible CUDA
  contexts, streams, denoisers, and GPU buffers between renders.
- Nuke validation now covers repeated renders, real tiled invocation, and
  image-size changes across the supported Nuke and OptiX versions.
- Standalone CLI repeat runs now reuse one OptiX session for accurate profiling.
- Native OptiX source changes now compile on Windows and Linux pull requests,
  with platform-specific source keys and cache inputs.
- The Nuke workflow can build one package or the serial 12-package supported
  matrix, reuse pinned SDK caches, and optionally publish manifest-validated
  release assets.

### Fixed
- Large Nuke plane conversions and output writes now respond to render aborts.
- The Windows Nuke build script now hashes files correctly under Windows
  PowerShell 5.1.
- Nuke packaging now rejects binaries that omit required Nuke/CUDA Driver
  imports or accidentally link a CUDA Runtime DLL.
- The legacy standalone CLI now applies its alpha mode before OptiX denoiser
  creation and reports named OptiX initialization errors.
- Pull-request packaging can reuse a compatible published OptiX runtime when
  native source changes produce a source key that is not released yet.
- Partial OptiX fetches preserve installed variants, archives reject path
  traversal, and interrupted CUDA downloads recover without manual cleanup.
- RGB and other sub-four-channel standalone outputs no longer write beyond
  their pixel stride, and legacy AOV output paths no longer assume an extension.
- Static Linux OpenImageIO builds now link their PNG dependency explicitly
  instead of accidentally discovering an untracked system library.

## [2.0.1] — 2026-07-28

### Changed
- Windows release packages are now built with Nuitka instead of PyInstaller.
- The release workflow now bundles the validated Intel OIDN 2.5.0 runtime.
- The public Windows package name remains `h-denoise-bundled-windows-x64-vX.Y.Z.zip`.

### Improved
- The Windows download is about 37% smaller and CLI startup is about 56% faster
  in the same-commit GitHub Actions comparison.

## [2.0.0] — 2026-05-20

Version 2.0.0: Breaking changes to remove Houdini integration.

### Added
- Single Houdini-free bundled Windows package with OptiX 8.1, 9.0, 9.1, and
  custom Intel OIDN 2.5.0 multipart EXR runtimes.
- GUI backend selector for OptiX vs OIDN, plus an OptiX runtime selector for the
  bundled 8.1 / 9.0 / 9.1 variants.
- CLI backend selection with `--backend optix|oidn` and `--optix-version` for
  headless batch denoise runs.
- Native OIDN wrapper build/fetch workflow, release asset publishing, and a UINT
  channel preservation smoke test.
- Validation and handoff docs for bundled OptiX versions, OIDN bundling, and
  multipart EXR metadata preservation.
- Expanded Google-style docstring coverage and added Ruff linting to the
  development workflow.

### Changed
- Release workflow now publishes `h-denoise-bundled-windows-x64-vX.Y.Z.zip`
  and the matching OIDN wrapper bundle from a tag build.
- Windows package smoke checks validate the frozen app, UI assets, and both
  bundled runtime families before publishing.
- OIDN build/fetch tooling now caches reusable wrapper bundles, validates the
  source key, and reuses matching artifacts in CI and release jobs.
- File utilities now use `pathlib`, with CLI typing, UI typing, and test
  annotations modernized under Ruff.
- EXR/header magic values and other cross-module literals were centralized in
  shared constants.
- Documentation now frames the app as a standalone bundled-runtime denoiser
  instead of a Houdini helper.

### Removed
- Houdini discovery, `idenoise` / `hoiiotool` integration, SideFX-specific
  options, and the legacy Houdini-linked release package.
- Dual-package Houdini/OptiX release variant workflow from the v1.3 line.
- Development environment overrides for bundled runtime resolution:
  `HDU_DENOISER_EXE`, `HDU_OPTIX_VERSION`, `HDU_OIDN_DENOISER_EXE`, and
  `HDU_OIDN_ROOT`.
- Tracked `.kiro` spec files from the repository.

### Fixed
- OIDN EXR layer detection, XYZ normal guide channel handling, bundled runtime
  selection, and OIDN fetch/build cache reuse.
- Release artifact smoke checks now catch frozen wrapper startup issues before
  upload.

## [1.3.0] — 2026-05-17

### Added
- Dual-variant Windows release workflow that publishes Houdini-linked and bundled OptiX packages to one GitHub release.
- Variant-specific package names:
  - `h-denoise-houdini-windows-x64-vX.Y.Z.zip`
  - `h-denoise-optix-windows-x64-vX.Y.Z.zip`
- Release manifest section with Houdini branch SHA, OptiX branch SHA, and pinned OptiX denoiser SHA.
- Release variant documentation for the Houdini and OptiX package feature differences.

### Changed
- CI package artifacts now use variant-specific names.
- Release packaging now fails if `main` and `optix-bundled-denoiser` report different package versions.

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
