# Nuke OptiX plugin

`HOptixDenoise` is a native Nuke `PlanarIop` that runs the NVIDIA OptiX
spatial denoiser in-process. It uses a host-neutral in-memory C++ core alongside
the existing standalone native tooling, while the Nuke adapter owns
NDK-specific image requests, channels, knobs, and error reporting.

## Supported inputs

The node exposes three inputs:

1. `beauty` — required RGB or RGBA noisy render.
2. `albedo` — optional RGB albedo guide.
3. `normal` — optional RGB normal guide; requires albedo.

Guide inputs must match the beauty input's format and data window. The output
preserves alpha and non-RGB channels from the beauty input.

## Controls

- **input blend** mixes the original input into the result. `0` is fully
  denoised and `1` is unchanged.
- **tile size** trades speed for lower peak VRAM use.
- **GPU device** selects a zero-based CUDA device.
- **normal encoding** accepts signed `-1..1` normals or remaps unsigned `0..1`
  normals before denoising.
- **passthrough on error** returns the beauty input if CUDA or OptiX fails.

The first release intentionally provides spatial denoising only. Temporal
state is not implemented because Nuke can evaluate frames non-sequentially and
would require frame-, view-, and hash-aware state management.

## Install a packaged build

Unzip the matching package for the Nuke major/minor version. Add the extracted
`HOptixDenoise` directory to `NUKE_PATH`, or copy it into the user's `.nuke`
directory. Restart Nuke and create the node from **Filter > HOptixDenoise**.

Windows production builds have been compiled and GPU-validated locally against
Nuke `14.1v8`, `15.0v1`, `15.1v4`, and `17.0v3`. A package built for Nuke
`17.0v3` is named by its binary-compatible major/minor line:

```text
h-denoise-nuke-17.0-windows-x64-optix-9.1-vX.Y.Z.zip
```

The manifest inside the package records the exact Nuke revision used to build
it.

## Build on Windows

Requirements:

- A licensed Nuke installation with NDK headers and `DDImage.lib`.
- Visual Studio 2022 with the C++ x64 tools.
- CMake and Ninja.
- An NVIDIA driver for runtime validation.

The build script downloads only the pinned OptiX headers and NVIDIA's small
CUDA driver-header redistributable. It does not install the full CUDA Toolkit.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -OptixVersion 9.1
```

The command configures, builds, installs, validates in Nuke terminal mode, and
creates the release ZIP under `dist/`.

Use the compile-check stub when CUDA or an NVIDIA GPU is unavailable:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -Stub
```

The stub is for NDK compatibility testing only and must not be distributed as
a denoiser.

## Build automation

The `Nuke OptiX Plugin` workflow targets a Windows self-hosted runner because
Foundry's Nuke SDK and license are not available on GitHub-hosted runners. The
runner must have Nuke and the Visual Studio toolchain installed. The workflow
uses the same build script as local development and uploads the validated ZIP.

## Architecture

```text
Nuke ImagePlane buffers
        |
        v
native/nuke-optix/src/HOptixDenoise.cpp
        |
        v
native/optix-denoiser/include/hdu/optix_denoiser.h
        |
        v
native/optix-denoiser/src/optix_denoiser.cpp
        |
        v
CUDA Driver API + NVIDIA OptiX
```

The new core accepts in-memory float4 buffers. It does not depend on Nuke, Qt,
Python, OpenImageIO, or OpenEXR. This keeps the Nuke integration separate from
GPU denoising and provides a stable seam for future native adapters. The
existing standalone CLI remains on its established implementation in this
change to avoid regressing multipart, AOV, and temporal behavior.
