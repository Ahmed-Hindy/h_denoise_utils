# HDenoiseNodes for Nuke

This `HDenoiseNodes` package provides two native Nuke denoiser nodes:

- **Filter > HOptixDenoise** — NVIDIA OptiX spatial denoising.
- **Filter > HOidnDenoise** — Intel Open Image Denoise using its CUDA backend.

## Install

Add this directory to `NUKE_PATH`, or copy the complete directory into the
user's `.nuke` directory. Keep all DLLs and `HOidnBridge.exe` together. Restart
Nuke after installation.

Packages are built for a specific Nuke major/minor ABI. Use the package matching
your installed Nuke line.

## Inputs

Both nodes expose the same three inputs:

1. `beauty` — required noisy RGB or RGBA render.
2. `albedo` — optional RGB albedo guide.
3. `normal` — optional RGB normal guide; requires albedo.

All connected inputs must have the same data window and resolution. Alpha and
non-RGB beauty channels pass through unchanged.

## HOptixDenoise controls

- **input blend** — `0` is fully denoised; `1` is the original input.
- **tile size** — smaller tiles reduce peak VRAM use.
- **GPU device** — zero-based CUDA device index.
- **normal encoding** — signed normals or unsigned `0..1` normals remapped to
  `-1..1`.
- **passthrough on error** — returns beauty unchanged when OptiX fails.

The node keeps compatible CUDA contexts, streams, OptiX denoisers, and buffers
alive between renders.

## HOidnDenoise controls

- **input blend** — mixes the original beauty into the denoised result.
- **GPU device** — zero-based CUDA device selected for the helper process.
- **quality** — Fast, Balanced, or High.
- **HDR input** — enable for scene-linear HDR renders.
- **clean auxiliary passes** — enable when albedo and normal are noise-free.
- **normal encoding** — signed or unsigned normals.
- **passthrough on error** — returns beauty unchanged when OIDN fails.

`HOidnDenoise` is a real Nuke image node. It gathers Nuke image planes and
returns the denoised pixels through the normal render graph. OIDN itself runs in
`HOidnBridge.exe`, an isolated child process, because Nuke ships private Visual
C++ and oneTBB runtime DLLs that conflict with Intel's binary OIDN runtime when
loaded into the same process. The helper uses raw float buffers, not temporary
EXR files, and is terminated when the Nuke render is aborted.

## Requirements

- Windows x64.
- A supported NVIDIA GPU and driver.
- A package built for the installed Nuke major/minor version.

Neither node requires a full CUDA Toolkit installation. `HOptixDenoise` uses the
CUDA Driver API, while `HOidnDenoise` ships the required CUDA-only OIDN runtime
DLLs inside this package.
