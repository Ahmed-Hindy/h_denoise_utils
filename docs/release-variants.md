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

This package is built from `optix-bundled-denoiser`. It does not require Houdini at runtime. It uses the bundled compiled OptiX denoiser pinned to:

```text
8893b605903f273512b750d45993bbe27a003362
```

V1 supports the validated multipart EXR workflow:

- bundled NVIDIA OptiX denoising
- multipart EXR input and output
- beauty, albedo, and normal subimage names
- selected AOV subimage names
- source OpenEXR metadata preservation

Temporal denoising, GPU selection, blend controls, and other native OptiX options are future work unless separately validated.
