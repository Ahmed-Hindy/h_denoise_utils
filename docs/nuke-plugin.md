# Native Nuke denoiser nodes

The Windows Nuke package provides two native `PlanarIop` nodes with the same
three-input image contract:

- `HOptixDenoise` — NVIDIA OptiX spatial denoising in the Nuke process.
- `HOidnDenoise` — Intel Open Image Denoise using its CUDA backend through an
  isolated packaged helper process.

The Nuke adapters own NDK image requests, channels, knobs, abort handling, and
error reporting. Alpha and non-RGB beauty channels pass through unchanged.

Read the [architecture](nuke-plugin-architecture.md) for process and package
boundaries, the [onboarding guide](nuke-plugin-onboarding.md) for development
workflow, and the [handoff](nuke-plugin-handoff.md) for current branch evidence.

## Supported inputs

1. `beauty` — required RGB or RGBA noisy render.
2. `albedo` — optional RGB albedo guide.
3. `normal` — optional RGB normal guide; requires albedo.

Guide inputs must match the beauty format and data window.

## HOptixDenoise

Controls:

- **input blend** mixes the original beauty into the result.
- **tile size** trades speed for lower peak VRAM use.
- **GPU device** selects a zero-based CUDA device.
- **normal encoding** accepts signed `-1..1` normals or remaps unsigned `0..1`
  normals before denoising.
- **passthrough on error** returns beauty unchanged after a CUDA or OptiX
  failure.

Each node owns a thread-safe denoiser session. Compatible renders reuse the CUDA
primary context, OptiX device context, stream, denoiser, and GPU buffers.
Resources are rebuilt only when the GPU, guide layout, image dimensions, or
tile settings change.

The first implementation is spatial only. Temporal state is deliberately
excluded because Nuke can evaluate frames non-sequentially and would require
frame-, view-, and hash-aware state management.

## HOidnDenoise

Controls:

- **input blend** mixes the original beauty into the result.
- **GPU device** selects the CUDA GPU used by OIDN.
- **quality** selects Fast, Balanced, or High.
- **HDR input** configures the OIDN RT filter for scene-linear HDR data.
- **clean auxiliary passes** indicates that albedo and normal are noise-free.
- **normal encoding** supports signed or unsigned normals.
- **passthrough on error** returns beauty unchanged after a helper or OIDN
  failure.

`HOidnDenoise` is a real Nuke node: it receives Nuke image inputs and returns
pixels through the normal Nuke render graph. OIDN execution is isolated in
`HOidnBridge.exe`. Nuke ships private Visual C++ and oneTBB DLLs, while Intel's
binary OIDN distribution is built against newer runtime versions. Loading both
sets into the Nuke process caused deterministic access violations during OIDN
device creation. The bridge avoids that ABI collision.

The node writes raw float3 beauty and optional guide buffers to a private
binary exchange file, launches the CUDA-only helper without a console, polls it
for completion, and reads the raw float3 result. It does not create intermediate
EXRs. A Nuke render abort terminates the helper and removes temporary files.
Only the OIDN core and CUDA device DLLs are packaged; CPU, SYCL, HIP, and oneTBB
modules are intentionally excluded from Nuke packages.

## Install a packaged build

Unzip the package matching the Nuke major/minor version. Add the extracted
`HDenoiseNodes` directory to `NUKE_PATH`, or copy the complete directory into
the user's `.nuke` directory. Keep both node DLLs, `HOidnBridge.exe`, and all
packaged runtime DLLs together.

Restart Nuke. The nodes are available under:

- **Filter > HOptixDenoise**
- **Filter > HOidnDenoise**

Windows production packages are built against Nuke `14.1v8`, `15.0v1`,
`15.1v4`, and `17.0v3`. Package names continue to identify the Nuke ABI and
OptiX variant:

```text
h-denoise-nuke-17.0-windows-x64-optix-9.1-vX.Y.Z.zip
```

Each package contains both denoiser nodes. Its manifest records:

- exact Nuke revision and OptiX SDK commit
- OptiX DLL hash, size, and PE dependencies
- OIDN version
- OIDN node and bridge hashes, sizes, and PE dependencies
- exact CUDA-only OIDN runtime DLL hashes and sizes
- source commit and whether both Nuke render validations completed

Release validation rejects direct OIDN linkage from `HOidnDenoise.dll`, missing
bridge/runtime files, CUDART linkage in the OptiX DLL, incorrect hashes, and
packages built with `-SkipValidation`.

## Build on Windows

Requirements:

- A licensed Nuke installation with NDK headers and `DDImage.lib`.
- Visual Studio 2022 with the C++ x64 tools.
- CMake and Ninja.
- An NVIDIA driver for both runtime validators.

The build script obtains pinned OptiX headers, the small CUDA driver-header
redistributable, and Intel OIDN when they are not already cached. It does not
install a full CUDA Toolkit.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -OptixVersion 9.1
```

The command configures, builds, installs, renders through both nodes in Nuke
terminal mode, creates the manifest, and packages the release ZIP under
`dist/`.

Use the OptiX compile-check stub when CUDA is unavailable:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\build_nuke_optix.ps1 `
  -NukeVersion 17.0v3 `
  -Stub
```

The stub is for NDK compatibility testing only. It does not build the OIDN node
and must not be distributed as a production denoiser.

## Current limitations

- Windows is the only validated Nuke package platform.
- Both nodes currently require an NVIDIA GPU.
- OptiX temporal denoising is not implemented.
- OIDN process isolation adds helper startup and host-buffer I/O overhead.

These constraints are intentional for the first implementation. The combined
package now uses the neutral `HDenoiseNodes` directory and manifest identity;
the individual Nuke node class names remain unchanged.

## Build automation

The `Nuke Denoiser Nodes` workflow uses a Windows self-hosted runner because the
Nuke SDK and license are not available on GitHub-hosted runners. A dispatch can
build one Nuke/OptiX pair or the complete matrix of Nuke `14.1v8`, `15.0v1`,
`15.1v4`, and `17.0v3` against OptiX `8.1`, `9.0`, and `9.1`. Jobs run serially
to avoid concurrent Nuke license and GPU use.

Each production matrix package also contains OIDN 2.5.0 and must render through
both native node classes. Optional release publication validates package count,
compatibility coverage, source commit, tag identity, every binary digest, and
the isolated OIDN dependency boundary before assets are uploaded.

## Architecture

```text
HOptixDenoise
Nuke ImagePlane -> native Nuke adapter -> shared OptiX core
                                      -> CUDA Driver API + OptiX

HOidnDenoise
Nuke ImagePlane -> native Nuke adapter -> raw float buffer exchange
                                      -> HOidnBridge.exe
                                      -> OIDN CUDA backend
```

The OptiX core remains independent of Nuke, Qt, Python, OpenImageIO, and
OpenEXR. The OIDN bridge protocol is also independent of EXR metadata and
filesystem image codecs; it transports only tightly packed float3 pixel data
and a small versioned header.
