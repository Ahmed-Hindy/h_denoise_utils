# Agent Handoff: Bundled OptiX Branch

Last updated: 2026-05-18

> Historical note: this handoff describes the earlier standalone OptiX branch
> strategy. The current release plan is a combined bundled-runtime app that
> includes both OptiX and OIDN, with users choosing the backend in the UI.
> Prefer `docs/release-variants.md` for current release/package instructions.

## Goal

This branch is the Houdini-free OptiX release line. Keep `main` as the Houdini-linked default app and keep `optix-bundled-denoiser` as the long-running bundled OptiX branch until the two-variant release strategy is intentionally retired.

## Branch Model

- `main`: Houdini-linked behavior. Keep `idenoise`, Houdini discovery, `hoiiotool` AOV scanning, backend selection, temporal UI, `--options`, `--exrmode`, and custom executable picker.
- `optix-bundled-denoiser`: standalone Windows OptiX build. Runtime denoising uses bundled `Denoiser.exe` variants for OptiX 8.1, 9.0, and 9.1; no Houdini discovery, no `idenoise`, and no `hoiiotool` in the app path.
- Do not merge OptiX app changes into `main` unless the release strategy changes.

## Pinned Denoisers

- Source repository: `Ahmed-Hindy/NvidiaAIDenoiser`
- Source commit: `fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf`
- Release tag: `optix-denoiser-v2026.05.18`
- Release assets:
  - `optix-denoiser-windows-x64-optix-8.1-fc927b7.zip`
  - `optix-denoiser-windows-x64-optix-9.0-fc927b7.zip`
  - `optix-denoiser-windows-x64-optix-9.1-fc927b7.zip`
- Fetch script: `tools/fetch_optix_denoiser.ps1`
- Install paths:
  - `h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-8.1/Denoiser.exe`
  - `h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.0/Denoiser.exe`
  - `h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.1/Denoiser.exe`
- Default runtime: OptiX 9.0
- Runtime selector: Settings -> Bundled Runtime -> OptiX Runtime
- Runtime environment override: `HDU_OPTIX_VERSION=8.1`, `9.0`, or `9.1`
- Development override: `HDU_DENOISER_EXE`

The vendor directory is ignored by Git and should be populated before package builds.

Runtime matrix:

| Runtime | OptiX SDK commit | Status |
| --- | --- | --- |
| OptiX 8.1 | `50021ea0af6d41609a97777ceebbdf1e1d34efe7` | Locally validated on Canyon Run; 22 output parts; raw EXR header metadata diff count `0`. |
| OptiX 9.0 | `fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd` | Default. Locally validated on Canyon Run; 22 output parts; raw EXR header metadata diff count `0`. |
| OptiX 9.1 | `f1f6dd803f3159992d248178f6e09421c6eb8b6d` | Locally validated on Canyon Run after upgrading the maintainer workstation to NVIDIA driver `596.49`; 22 output parts; raw EXR header metadata diff count `0`. Older driver `576.80` failed locally with `optixInit` error `7801`. |

## Runtime Entry Points

- `h_denoise_utils/discovery/bundled_denoiser.py` resolves the bundled executable selected by the UI, `HDU_OPTIX_VERSION`, or `HDU_DENOISER_EXE`.
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
- PyInstaller spec includes the vendor OptiX denoiser directory recursively when present, so the three versioned runtime folders are shipped together.
- The app smoke test on this branch requires the bundled denoiser to be resolvable.

## Release Workflow

The release workflow lives on `main` and is triggered by tags like `v1.3.0`.

It checks out:

- the tagged `main` commit for the Houdini package
- `optix-bundled-denoiser` branch HEAD for the OptiX package

It then verifies both `pyproject.toml` versions match, builds both zip artifacts, fetches the pinned three-runtime OptiX denoiser release only for the OptiX checkout, and publishes both artifacts to one GitHub release with a generated SHA manifest.

## Validation Commands

Use native TLS with `uv` on this workstation if package resolution hits local certificate issues:

```powershell
uv run --native-tls pytest --tb=short
```

Latest full test result after the three-runtime update:

```text
96 passed in 14.80s
```

Build the OptiX package after fetching the denoiser:

```powershell
.\tools\fetch_optix_denoiser.ps1
.\tools\build_windows_package.ps1 -Variant optix
```

Latest package output:

```text
dist/h-denoise-optix-windows-x64-v1.3.0.zip
size: 137516504 bytes
```

The generated zip should contain:

```text
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-8.1/Denoiser.exe
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-8.1/manifest.json
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.0/Denoiser.exe
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.0/manifest.json
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.1/Denoiser.exe
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.1/manifest.json
```

Frozen app smoke checks passed for the default runtime and explicit alternate runtimes:

```powershell
.\dist\h-denoise\h-denoise.exe --smoke-test
$env:HDU_OPTIX_VERSION='8.1'; .\dist\h-denoise\h-denoise.exe --smoke-test
$env:HDU_OPTIX_VERSION='9.1'; .\dist\h-denoise\h-denoise.exe --smoke-test
```

## Manual Canyon Run Expectations

For the validated Canyon Run EXR sample:

- Pure Python AOV scanning should find 22 parts.
- The first planes should include `C`, `albedo`, `C_emission`, `C_light_distant_1`, and `C_light_dome_1`.
- Denoising with the pinned bundled executable should produce a 22-part output EXR.
- Raw source-vs-output EXR header metadata diff count should be `0`.

Driver comparison notes:

- `docs/optix-8-1-vs-9-0-quality-comparison.md` records the original driver `576.80` result where OptiX 8.1 and 9.0 were byte-identical.
- `docs/optix-driver-576-80-vs-596-49-quality-comparison.md` records the follow-up after upgrading to driver `596.49`. On that driver, OptiX 8.1, 9.0, and 9.1 are byte-identical to each other, but differ from the old `576.80` output in the denoised planes only.

## Things To Keep An Eye On

- If the external denoiser release assets are replaced, verify each `manifest.json` still reports the pinned source commit and expected OptiX SDK commit.
- If the OptiX branch version changes, update `main` to the same `pyproject.toml` version before tagging; the release workflow intentionally fails on mismatch.
- Keep Houdini-specific docs and workflows on `main`; keep this branch's README focused on the standalone OptiX package.
