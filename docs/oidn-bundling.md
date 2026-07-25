# Bundled OIDN Denoiser

The app bundles a custom Intel Open Image Denoise (OIDN) wrapper next to the
bundled OptiX runtimes.

## Runtime layout

- Official OIDN runtime package: `v2.5.0`.
- Official Windows asset: `oidn-2.5.0.x64.windows.zip`.
- Custom wrapper executable: `Denoiser.exe`.
- Packaged vendor layout:

```text
h_denoise_utils/vendor/oidn-denoiser/windows-x64/oidn-2.5.0/
├── Denoiser.exe
├── OpenImageDenoise*.dll
├── tbb*.dll
├── manifest.json
├── LICENSE.txt
└── third-party-programs*.txt
```

The official SDK/sample package is still fetched into `vendor/oidn` for
building:

```powershell
.\tools\fetch_oidn.ps1
```

Build the custom wrapper in GitHub Actions using the `OIDN Denoiser` workflow,
or locally only when intentionally validating the native toolchain:

```powershell
.\tools\build_oidn_denoiser.ps1
```

Fetch a released wrapper asset with:

```powershell
.\tools\fetch_oidn_denoiser.ps1
```

By default the fetch script searches the latest non-draft `v*` app release for
an `oidn-denoiser-windows-x64-oidn-2.5.0-*.zip` asset. To fetch from a specific
release, pass the tag explicitly:

```powershell
.\tools\fetch_oidn_denoiser.ps1 -Tag vX.Y.Z
```

Build the bundled portable app package after both OptiX and OIDN runtimes are
present:

```powershell
.\tools\build_windows_package.ps1 -Variant bundled
```

The bundled smoke check validates that both runtime families and the UI assets
are present:

```powershell
.\dist\h-denoise\h-denoise.exe --smoke-test --smoke-runtime all
```

## Wrapper contract

Production OIDN denoising uses the same multipart CLI contract as OptiX:

```powershell
Denoiser.exe -v 1 -multipart input.exr -o output.exr -beauty-name C -albedo-name albedo -normal-name N -aov-name0 directdiffuse -aov-name1 indirectdiffuse
```

The wrapper reads the source multipart EXR, extracts RGB from the selected
beauty and explicit AOV parts, calls OIDN `RT` on the CPU device, then writes
the denoised RGB channels back into the original multipart EXR structure.
Alpha, extra channels, untouched parts, and raw OpenEXR headers are preserved
through the same OpenEXR multipart writer approach used by the bundled OptiX
wrapper.

The official `oidnDenoise.exe` remains useful as an upstream reference and
simple smoke artifact, but it is not the production denoising executable for
this app.

## Useful official references

- OIDN downloads: https://www.openimagedenoise.org/downloads.html
- OIDN documentation for `oidnDenoise`: https://www.openimagedenoise.org/documentation.html#oidnDenoise
- OIDN source repository: https://github.com/RenderKit/oidn
