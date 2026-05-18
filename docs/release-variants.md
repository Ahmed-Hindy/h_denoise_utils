# Release Variants

`h_denoise_utils` publishes two Windows package variants from the same release.

## Houdini-Linked Package

Artifact name:

```text
h-denoise-houdini-windows-x64-vX.Y.Z.zip
```

This is the default app line from `main`. It keeps Houdini `idenoise` behavior:

- Houdini executable discovery
- custom `idenoise` executable selection
- OIDN and OptiX backend selection
- temporal controls
- SideFX `--options`
- SideFX `--exrmode`
- Houdini `hoiiotool` AOV scanning

## Bundled OptiX Package

Artifact name:

```text
h-denoise-optix-windows-x64-vX.Y.Z.zip
```

This package is built from `optix-bundled-denoiser`. It does not require Houdini at runtime. It bundles three compiled OptiX denoiser variants from:

```text
https://github.com/Ahmed-Hindy/NvidiaAIDenoiser/releases/tag/optix-denoiser-v2026.05.18
```

All variants come from NvidiaAIDenoiser source commit:

```text
fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf
```

Bundled runtime matrix:

| Runtime | OptiX SDK commit | Local validation |
| --- | --- | --- |
| OptiX 8.1 | `50021ea0af6d41609a97777ceebbdf1e1d34efe7` | Canyon Run multipart denoise passed; 22 parts; raw EXR header metadata diff count `0`. |
| OptiX 9.0 | `fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd` | Canyon Run multipart denoise passed; 22 parts; raw EXR header metadata diff count `0`. |
| OptiX 9.1 | `f1f6dd803f3159992d248178f6e09421c6eb8b6d` | Included for newer-driver compatibility. Local `optixInit` error `7801` is expected on the validation workstation because its NVIDIA driver is below the OptiX 9.1 runtime requirement. |

The app defaults to OptiX 9.0. Users can select OptiX 8.1, 9.0, or 9.1 in the Settings section. For command-line/development runs, set `HDU_OPTIX_VERSION=8.1`, `HDU_OPTIX_VERSION=9.0`, or `HDU_OPTIX_VERSION=9.1`. `HDU_DENOISER_EXE` still overrides the bundled executable entirely for development.

V1 supports the validated multipart EXR workflow:

- bundled NVIDIA OptiX denoising
- multipart EXR input and output
- beauty, albedo, and normal subimage names
- selected AOV subimage names
- source OpenEXR metadata preservation

Temporal denoising, GPU selection, blend controls, and other native OptiX options are future work unless separately validated.
