# Release Package

`h_denoise_utils` publishes one Houdini-free Windows package that bundles both
runtime families.

## Bundled Windows Package

Artifact name:

```text
h-denoise-bundled-windows-x64-vX.Y.Z.zip
```

The package includes:

- OptiX 8.1, 9.0, and 9.1 multipart EXR denoiser runtimes.
- The custom Intel OIDN 2.4.1 multipart EXR `Denoiser.exe` wrapper.
- A GUI backend selector so users can choose OptiX or OIDN per run.

Bundled OptiX runtimes come from the support release in this repository:

```text
https://github.com/Ahmed-Hindy/h_denoise_utils/releases/tag/optix-denoiser-v2026.05.21
```

The wrapper source is owned in-tree under `native/optix-denoiser`, imported from
the historical NvidiaAIDenoiser commit:

```text
fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf
```

The NVIDIA OptiX SDK headers are not committed. CI checks out `NVIDIA/optix-dev`
at the pinned SDK commits below when building support assets.

Runtime matrix:

| Runtime | Source/version | Validation |
| --- | --- | --- |
| OptiX 8.1 | SDK commit `50021ea0af6d41609a97777ceebbdf1e1d34efe7` | Canyon Run multipart denoise passed; 22 parts; raw EXR header metadata diff count `0`. |
| OptiX 9.0 | SDK commit `fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd` | Default OptiX runtime; Canyon Run multipart denoise passed; 22 parts; raw EXR header metadata diff count `0`. |
| OptiX 9.1 | SDK commit `f1f6dd803f3159992d248178f6e09421c6eb8b6d` | Included for newer-driver compatibility and validated on NVIDIA driver `596.49`. |
| OIDN | Intel Open Image Denoise `2.4.1` | Canyon Run multipart denoise passed; 22 parts; raw EXR header metadata diff count `0`. |



## Supported Workflow

V1 supports the validated multipart EXR workflow:

- multipart EXR input and output
- beauty, albedo, and normal subimage names
- selected AOV subimage names
- source OpenEXR metadata preservation

Temporal denoising, GPU selection for OIDN, blend controls, and other native
denoiser options are future work unless separately validated.
