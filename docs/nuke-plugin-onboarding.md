# Nuke denoiser onboarding

This guide is for developers and technical artists who need to build, test,
debug, or extend the native Nuke denoiser package.

Read [Nuke denoiser architecture](nuke-plugin-architecture.md) first when
changing process boundaries, dependencies, or package contents.

## What you are working on

The subsystem ships one `HDenoiseNodes` package containing:

- `HOptixDenoise` — in-process NVIDIA OptiX denoising;
- `HOidnDenoise` — OIDN 2.5 CUDA denoising through `HOidnBridge.exe`.

Both nodes are native Nuke `PlanarIop` implementations with beauty, albedo, and
normal inputs. Do not treat `HOidnDenoise` as an EXR command-line wrapper: its
helper is a private ABI-isolation layer that exchanges raw float buffers.

## Repository map

| Path | Purpose |
| --- | --- |
| `native/nuke-optix/src/HOptixDenoise.cpp` | Nuke adapter for OptiX |
| `native/nuke-optix/src/HOidnDenoise.cpp` | Nuke adapter and bridge process management for OIDN |
| `native/nuke-optix/src/HOidnBridge.cpp` | Isolated OIDN CUDA process |
| `native/nuke-optix/src/oidn_bridge_protocol.h` | Versioned raw-buffer protocol |
| `native/optix-denoiser/` | Host-neutral reusable OptiX implementation |
| `native/nuke-optix/package/` | `init.py`, menu registration, and packaged README |
| `tools/build_nuke_optix.ps1` | Windows build, validation, manifest, and ZIP creation |
| `tools/validate_nuke_optix_plugin.py` | Nuke terminal render validation for both nodes |
| `tools/validate_nuke_release_assets.py` | Release-package and matrix validation |
| `.github/workflows/nuke-optix.yml` | Self-hosted Nuke build and optional release workflow |
| `examples/nuke-denoise-playground/` | Live OptiX/OIDN comparison graph and launcher |
| `tests/test_nuke_plugin_layout.py` | Structural and dependency-boundary assertions |
| `tests/test_nuke_release_assets.py` | Manifest and ZIP tamper tests |

## Required local tools

- Windows x64;
- one of the supported licensed Nuke installations;
- Nuke NDK headers and `DDImage.lib` from that installation;
- Visual Studio 2022 C++ x64 tools;
- CMake and Ninja;
- an NVIDIA driver and supported GPU;
- Git and PowerShell;
- the project Python environment for tests.

The build script can fetch pinned OptiX headers, a small CUDA driver-header
redistributable, and OIDN 2.5 when they are not already cached. It does not
install the full CUDA Toolkit.

## First local build

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -OptixVersion 9.1
```

A successful production build:

1. compiles all three native targets warning-clean under MSVC `/W4`;
2. installs them under `build\nuke-optix-package\...\HDenoiseNodes`;
3. copies only the OIDN CUDA runtime DLLs;
4. renders four OptiX validation cases and one OIDN case in Nuke;
5. writes `manifest.json`;
6. creates `dist\h-denoise-nuke-17.0-windows-x64-optix-9.1-vX.Y.Z.zip`.

The extracted ZIP must contain the `HDenoiseNodes` directory, not an individual
node directory.

## Compile-only stub

Use the OptiX stub only for NDK compile compatibility when a GPU or CUDA driver
is unavailable:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -Stub
```

The stub does not build `HOidnDenoise` and is not a production package.

## Launch the live playground

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\examples\nuke-denoise-playground\launch-nuke-playground.ps1
```

The launcher:

- selects an already built `HDenoiseNodes` package;
- sets `NUKE_PATH` only for the child Nuke process;
- removes a stale generated playground autosave;
- opens a graph containing live beauty-only and guided variants of both nodes;
- includes an amplified OptiX/OIDN difference branch and Write nodes.

Use another real multipart EXR with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\examples\nuke-denoise-playground\launch-nuke-playground.ps1 `
  -InputExr "H:\renders\shot.1001.exr" `
  -BeautyLayer "rgba" `
  -AlbedoLayer "albedo" `
  -NormalLayer "N"
```

Headless playground validation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\examples\nuke-denoise-playground\launch-nuke-playground.ps1 `
  -ValidateOnly
```

## Acceptance checklist

Before marking a Nuke change ready for review, verify in the newest supported
Nuke version:

- both nodes appear under **Filter**;
- input labels are `beauty`, `albedo`, and `normal`;
- knob labels, defaults, ranges, and tooltips are understandable;
- non-default values and all three connections survive save/reopen;
- animated frame changes render through both nodes;
- repeated OptiX renders reuse the session without stale output;
- changing resolution or OptiX tile size rebuilds the required state;
- invalid GPU selection produces a readable error;
- passthrough-on-error returns the beauty stream;
- cancelling an OIDN render stops the helper and removes temporary files;
- alpha and non-RGB beauty channels remain unchanged;
- the production playground renders OptiX, OIDN, and their difference.

Run the automated acceptance pass with:

```powershell
$env:NUKE_PATH = "<absolute-HDenoiseNodes-path>"
Remove-Item Env:CUDA_CACHE_MAXSIZE -ErrorAction SilentlyContinue
& "C:\Program Files\Nuke17.0v3\Nuke17.0.exe" `
  -t tools/validate_nuke_denoiser_acceptance.py
```

Run the external Ctrl+Break cancellation test with:

```powershell
uv --system-certs run python tools/validate_nuke_oidn_cancellation.py `
  --nuke "C:\Program Files\Nuke17.0v3\Nuke17.0.exe" `
  --plugin "build\nuke-optix-package\nuke-17.0v3\optix-9.1\HDenoiseNodes"
```

Current acceptance evidence is recorded in
[Nuke denoiser handoff](nuke-plugin-handoff.md).

## Validation ladder

Run checks from cheapest to most expensive.

### 1. Focused tests

```powershell
uv --system-certs run pytest `
  tests/test_nuke_plugin_layout.py `
  tests/test_nuke_release_assets.py `
  tests/test_nuke_denoise_playground.py
```

Use the existing project-local environment when the worktree itself does not
contain a synchronized `.venv`.

### 2. Ruff and whitespace

```powershell
uv --system-certs run ruff check .
git diff --check
```

### 3. One production package

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -OptixVersion 9.1
```

### 4. Real-scene playground

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\examples\nuke-denoise-playground\launch-nuke-playground.ps1 `
  -ValidateOnly
```

### 5. Performance benchmark

Run the reproducible 1080p/UHD benchmark with:

```powershell
$env:NUKE_PATH = "<absolute-HDenoiseNodes-path>"
Remove-Item Env:CUDA_CACHE_MAXSIZE -ErrorAction SilentlyContinue
& "C:\Program Files\Nuke17.0v3\Nuke17.0.exe" `
  -t tools/benchmark_nuke_denoiser_nodes.py
```

The JSON report is written under `%TEMP%\hdu-nuke-benchmark\benchmark.json`.
Treat it as end-to-end timing evidence, not a quality ranking.

### 6. Supported local matrix

Build all 12 Nuke/OptiX pairs serially. The build script intentionally reuses
an initialized Visual Studio environment and avoids repeatedly prepending Ninja
to `PATH`.

### 7. Release validator

Collect the 12 current ZIPs into a clean directory, then run:

```powershell
uv --system-certs run python .\tools\validate_nuke_release_assets.py `
  --assets-dir <matrix-directory> `
  --build-scope supported-matrix `
  --release-tag nuke-optix-v<project-version> `
  --source-commit <full-git-sha>
```

### 8. Self-hosted workflow

Dispatch **Nuke Denoiser Nodes** with release publication disabled. Use
`supported-matrix` before a public release and `single` for targeted validation.
Do not publish from an unreviewed branch.

## Debugging rules

### Nuke crashes during OIDN initialization

`HOidnDenoise.dll` must not link `OpenImageDenoise.dll`. Check with `dumpbin
/dependents`. OIDN belongs only in `HOidnBridge.exe`.

Also confirm the bridge:

- is statically linked to the Visual C++ runtime;
- delay-loads `OpenImageDenoise.dll`;
- calls `SetDllDirectoryW(L"")` before OIDN initialization;
- packages no oneTBB or CPU device module.

### OIDN reports unsupported CUDA device

Check the GPU index and driver. The bridge maps the zero-based node value to
`CUDA_VISIBLE_DEVICES`, then creates OIDN's CUDA device.

### OptiX package imports CUDART

The OptiX Nuke DLL must use the CUDA Driver API only. A CUDART import is a
packaging regression and should fail the build.

### Nuke cannot find either node

Confirm `NUKE_PATH` contains the complete `HDenoiseNodes` directory and that the
package matches Nuke's major/minor ABI. Keep the DLLs, helper, Python hooks, and
runtime DLLs together.

### A serial matrix eventually fails to launch tools

Do not repeatedly import the Visual Studio environment or prepend duplicate
paths. `tools/build_nuke_optix.ps1` is designed to be idempotent within one
PowerShell process.

## Safe change boundaries

Changes that usually remain local:

- knob labels and tooltips: native node source and acceptance assertions;
- menu location: `native/nuke-optix/package/menu.py` and structural tests;
- OptiX session behavior: shared OptiX core plus Nuke validator;
- OIDN filter options: protocol header, adapter, bridge, and protocol tests;
- package contents: CMake install rules, build script, manifest validator, ZIP
  tests, package README, and playground resolver;
- supported versions: workflow matrix, build-script mappings, release validator,
  documentation, and all matrix tests.

Do not modify only one layer of the package contract. The build script,
manifest, release validator, fixtures, launcher, and documentation must agree.

## Current defaults

### HOptixDenoise

- input blend: 0;
- tile size: 1024 x 1024;
- GPU device: 0;
- signed normals;
- passthrough on error: enabled.

### HOidnDenoise

- input blend: 0;
- GPU device: 0;
- quality: High;
- HDR input: enabled;
- clean auxiliary passes: enabled;
- signed normals;
- passthrough on error: enabled.

High remains the OIDN default because it is the production-quality mode and the
current local benchmark did not show a stable enough performance ordering to
justify changing artist output by default.

## Before opening or updating a PR

- keep the PR summary concise and human;
- include exactly what was validated locally;
- keep release publication disabled;
- verify the PR remains mergeable;
- resolve actionable review comments;
- leave generated EXRs, Nuke autosaves, build products, and temporary benchmark
  scripts untracked.
