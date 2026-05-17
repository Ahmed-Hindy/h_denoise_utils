# Agent Handoff: Bundled OptiX Branch

Last updated: 2026-05-17

## Goal

This branch is the Houdini-free OptiX release line. Keep `main` as the Houdini-linked default app and keep `optix-bundled-denoiser` as the long-running bundled OptiX branch until the two-variant release strategy is intentionally retired.

## Branch Model

- `main`: Houdini-linked behavior. Keep `idenoise`, Houdini discovery, `hoiiotool` AOV scanning, backend selection, temporal UI, `--options`, `--exrmode`, and custom executable picker.
- `optix-bundled-denoiser`: standalone Windows OptiX build. Runtime denoising uses bundled `Denoiser.exe`; no Houdini discovery, no `idenoise`, and no `hoiiotool` in the app path.
- Do not merge OptiX app changes into `main` unless the release strategy changes.

## Pinned Denoiser

- Source repository: `Ahmed-Hindy/NvidiaAIDenoiser`
- Source commit: `8893b605903f273512b750d45993bbe27a003362`
- Release tag: `hdu-multilayer-exr-output-8893b60`
- Release asset: `optix-denoiser-windows-x64-8893b60.zip`
- Fetch script: `tools/fetch_optix_denoiser.ps1`
- Install path: `h_denoise_utils/vendor/optix-denoiser/windows-x64/Denoiser.exe`
- Development override: `HDU_DENOISER_EXE`

The vendor directory is ignored by Git and should be populated before package builds.

## Runtime Entry Points

- `h_denoise_utils/discovery/bundled_denoiser.py` resolves the bundled executable or `HDU_DENOISER_EXE`.
- `h_denoise_utils/core/command_builder.py` builds the bundled command:
  - `Denoiser.exe -v 1 -multipart input.exr -o output.exr -beauty-name C ...`
- `h_denoise_utils/discovery/exr_inspector.py` performs pure Python EXR header parsing for multipart names and layered channel stems.
- `h_denoise_utils/core/denoiser.py` rejects legacy Houdini-only options before running the bundled command.
- `h_denoise_utils/ui/main_window.py` and `h_denoise_utils/ui/sections.py` expose only the validated OptiX v1 controls.

## Validated OptiX V1 Surface

- Multipart EXR denoise.
- Beauty, albedo, normal plane names.
- Selected AOV names.
- Output destination.
- Overwrite mode.
- Filename prefix mode.
- Metadata preservation is expected from the pinned denoiser build.

Temporal denoising, motion vectors, advanced OptiX flags, SideFX `--options`, SideFX `--exrmode`, OIDN, and Houdini executable selection are intentionally not exposed on this branch yet.

## Packaging

- Main/Houdini package name: `h-denoise-houdini-windows-x64-vX.Y.Z.zip`
- OptiX package name: `h-denoise-optix-windows-x64-vX.Y.Z.zip`
- Package builder: `tools/build_windows_package.ps1 -Variant houdini|optix`
- PyInstaller spec includes the vendor OptiX denoiser directory when present.
- The app smoke test on this branch requires the bundled denoiser to be resolvable.

## Release Workflow

The release workflow lives on `main` and is triggered by tags like `v1.3.0`.

It checks out:

- the tagged `main` commit for the Houdini package
- `optix-bundled-denoiser` branch HEAD for the OptiX package

It then verifies both `pyproject.toml` versions match, builds both zip artifacts, fetches the pinned OptiX denoiser only for the OptiX checkout, and publishes both artifacts to one GitHub release with a generated SHA manifest.

## Validation Commands

Use native TLS with `uv` on this workstation if package resolution hits local certificate issues:

```powershell
uv run --native-tls pytest --tb=short
```

Latest full test result while implementing this branch:

```text
91 passed in 11.10s
```

Build the OptiX package after fetching the denoiser:

```powershell
.\tools\fetch_optix_denoiser.ps1
.\tools\build_windows_package.ps1 -Variant optix
```

Latest package output:

```text
dist/h-denoise-optix-windows-x64-v1.3.0.zip
```

The generated zip was checked to contain:

```text
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/Denoiser.exe
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/manifest.json
```

## Manual Canyon Run Expectations

For the validated Canyon Run EXR sample:

- Pure Python AOV scanning should find 22 parts.
- The first planes should include `C`, `albedo`, `C_emission`, `C_light_distant_1`, and `C_light_dome_1`.
- Denoising with the pinned bundled executable should produce a 22-part output EXR.
- Raw source-vs-output EXR header metadata diff count should be `0`.

## Things To Keep An Eye On

- If the external denoiser release asset is replaced, verify its `manifest.json` still reports the pinned source commit.
- If the OptiX branch version changes, update `main` to the same `pyproject.toml` version before tagging; the release workflow intentionally fails on mismatch.
- Keep Houdini-specific docs and workflows on `main`; keep this branch's README focused on the standalone OptiX package.
