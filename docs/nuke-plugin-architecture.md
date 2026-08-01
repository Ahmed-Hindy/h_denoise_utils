# Nuke denoiser architecture

This document describes the native Nuke subsystem that ships the
`HOptixDenoise` and `HOidnDenoise` nodes in one `HDenoiseNodes` package.

## Goals

The subsystem is designed to:

- provide ordinary Nuke image nodes rather than command-line wrappers;
- accept beauty, albedo, and normal inputs through the Nuke graph;
- preserve alpha and non-RGB channels from the beauty stream;
- keep NVIDIA OptiX state reusable between compatible renders;
- keep Intel OIDN runtime DLLs isolated from Nuke's private runtime DLLs;
- package one validated directory for each supported Nuke ABI and OptiX SDK;
- fail predictably, with optional beauty passthrough for artist workflows.

The first implementation is Windows-only and spatial-only. Both nodes require
an NVIDIA GPU.

## Package boundary

The installed directory is named:

```text
HDenoiseNodes/
```

It contains:

```text
HDenoiseNodes/
├── HOptixDenoise.dll
├── HOidnDenoise.dll
├── HOidnBridge.exe
├── OpenImageDenoise.dll
├── OpenImageDenoise_core.dll
├── OpenImageDenoise_device_cuda.dll
├── init.py
├── menu.py
├── manifest.json
├── README.md
├── LICENSE
└── OIDN license notices
```

The two node class names remain stable even though the package container is
neutral. Add the `HDenoiseNodes` directory itself to `NUKE_PATH`.

## Shared Nuke contract

Both nodes are native `DD::Image::PlanarIop` implementations with three inputs:

1. `beauty` — required RGB or RGBA image;
2. `albedo` — optional RGB guide;
3. `normal` — optional RGB guide that requires albedo.

The adapters validate guide geometry and RGB availability, request the required
planes, convert Nuke image planes to tightly packed host buffers, run the
backend, then replace only RGB in the output plane. Alpha and other beauty
channels are copied unchanged.

Both nodes support:

- zero-based GPU selection;
- signed or unsigned normal encoding;
- input blend;
- passthrough on error;
- Nuke render-abort checks during host-buffer conversion and output writes.

## OptiX path

```text
Nuke graph
  -> HOptixDenoise.dll
  -> hdu::optix::DenoiserSession
  -> CUDA Driver API
  -> NVIDIA OptiX
  -> Nuke output plane
```

`HOptixDenoise.dll` links directly to `DDImage.dll` and the CUDA Driver API. It
does not link CUDART. The host-neutral implementation lives under
`native/optix-denoiser` and accepts float4 beauty and guide buffers.

Each Nuke node owns a thread-safe `DenoiserSession`. Compatible renders reuse:

- the retained CUDA primary context;
- the OptiX device context;
- the CUDA stream;
- the OptiX denoiser object;
- state, scratch, and image buffers.

A session is rebuilt when image dimensions, guide layout, GPU selection, or
tile configuration changes. CUDA or OptiX failures reset the session before the
next evaluation.

### Tiling

The artist-facing tile choices are full frame, 512, 1024, and 2048 pixels.
Smaller tiles reduce peak VRAM use at the cost of additional invocation and
copy overhead. The default is 1024 x 1024.

## OIDN path

```text
Nuke graph
  -> HOidnDenoise.dll
  -> versioned raw float3 exchange file
  -> HOidnBridge.exe
  -> OIDN CUDA backend
  -> raw float3 result
  -> Nuke output plane
```

`HOidnDenoise.dll` is a real Nuke image node, but OIDN execution does not occur
inside Nuke's process. Nuke ships private Visual C++ and oneTBB DLLs. Intel's
OIDN binaries require newer runtime versions with the same module names. Direct
in-process OIDN initialization reproducibly crashed during CUDA device creation.

The bridge process is therefore an ABI boundary, not a command-line image
workflow. It exchanges only a 32-byte versioned header and tightly packed float3
buffers. It does not create intermediate EXRs.

The bridge executable:

- uses a static Visual C++ runtime;
- delay-loads `OpenImageDenoise.dll`;
- clears Nuke's inherited DLL search directory before loading OIDN;
- restricts DLL lookup to the application directory and System32;
- sets `CUDA_VISIBLE_DEVICES` from the node's GPU knob;
- creates the OIDN CUDA device and RT filter;
- writes diagnostics to a private log captured by the Nuke adapter;
- runs without a console window.

The Nuke adapter polls the child process every 50 ms. When Nuke reports an
abort, it terminates the helper and removes the private input, output, and log
files.

Only these OIDN runtime DLLs are packaged:

- `OpenImageDenoise.dll`;
- `OpenImageDenoise_core.dll`;
- `OpenImageDenoise_device_cuda.dll`.

CPU, oneTBB, SYCL, and HIP modules are excluded to keep the runtime boundary
small and avoid module collisions.

## Build and package flow

```text
tools/build_nuke_optix.ps1
  1. resolve Nuke, MSVC, CMake, Ninja, OptiX, CUDA headers, and OIDN;
  2. configure native/nuke-optix/CMakeLists.txt;
  3. build HOptixDenoise, HOidnDenoise, and HOidnBridge;
  4. install into HDenoiseNodes/;
  5. copy the CUDA-only OIDN runtime and license notices;
  6. inspect PE dependencies with dumpbin;
  7. render through both nodes in Nuke terminal mode;
  8. write manifest hashes, sizes, dependencies, versions, and source commit;
  9. create the neutral h-denoise-nuke-... ZIP.
```

The build script reuses an already initialized Visual Studio environment and
adds Ninja to `PATH` only once. This is required for serial matrix builds in one
PowerShell process.

## Manifest and release invariants

`manifest.json` identifies the package as `HDenoiseNodes` and records:

- project and source-commit identity;
- exact Nuke revision and binary-compatible Nuke line;
- exact OptiX version and pinned source commit;
- hashes, sizes, and PE dependencies for both Nuke DLLs;
- the OIDN version;
- hash, size, and dependencies for `HOidnBridge.exe`;
- the exact OIDN CUDA runtime DLL set and hashes;
- whether Nuke render validation ran.

Release validation rejects packages that:

- contain the wrong package identity or unsupported matrix pair;
- were built from another commit;
- omit either Nuke node or the bridge;
- link OIDN directly into `HOidnDenoise.dll`;
- link CUDART into `HOptixDenoise.dll`;
- contain an unexpected OIDN runtime set;
- have mismatched sizes or SHA-256 digests;
- skipped Nuke render validation.

## Supported matrix

Validated Windows packages currently cover:

- Nuke 14.1v8;
- Nuke 15.0v1;
- Nuke 15.1v4;
- Nuke 17.0v3;

against:

- OptiX 8.1;
- OptiX 9.0;
- OptiX 9.1.

Every one of the 12 packages contains the same OIDN 2.5.0 CUDA node and must
render through both node classes.

## Performance characteristics

A local Nuke 17.0v3 benchmark on CUDA device 0 used guided synthetic frames,
one warm-up render, and the median of three animated-frame EXR renders.
Approximate denoiser overhead after subtracting the source-write baseline was:

| Resolution | OptiX guided | OIDN Fast | OIDN Balanced | OIDN High |
| --- | ---: | ---: | ---: | ---: |
| 1920 x 1080 | 0.35 s | 0.82 s | 0.79 s | 0.84 s |
| 3840 x 2160 | 1.44 s | 2.81 s | 2.95 s | 3.22 s |

Run the checked-in benchmark with `tools/benchmark_nuke_denoiser_nodes.py`.
The UHD samples contained occasional multi-second outliers, so these numbers
characterize end-to-end cost rather than provide a precise quality-mode ranking.
High remains the production default. The helper boundary is acceptable for the
first release, but a persistent helper or shared-memory transport may be
considered if real production profiling shows it is a bottleneck.

## Deliberate non-goals

The current subsystem does not provide:

- OptiX temporal denoising;
- CPU OIDN inside Nuke;
- Linux Nuke packages;
- cross-process persistent OIDN device/filter reuse;
- AOV batch denoising inside one Nuke node;
- automatic guide-layer discovery inside the native nodes.

Those features should be added only with production evidence and explicit
state-management or packaging designs.
