# HDU OIDN Denoiser

This native wrapper provides a `Denoiser.exe` with the same multipart EXR
command contract as the bundled OptiX wrapper, but uses Intel Open Image
Denoise for the denoising step.

The production command shape is:

```powershell
Denoiser.exe -v 1 -multipart input.exr -o output.exr -beauty-name C -albedo-name albedo -normal-name N -aov-name0 directdiffuse -aov-name1 indirectdiffuse
```

Only the RGB channels of the beauty part and explicitly requested AOV parts are
replaced. Alpha, extra channels, untouched parts, and source OpenEXR headers are
carried forward through the OpenEXR multipart writer path adapted from the
validated OptiX wrapper.
