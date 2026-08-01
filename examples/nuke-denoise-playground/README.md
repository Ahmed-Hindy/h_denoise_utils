# Nuke OptiX + OIDN playground

This folder provides a ready Nuke graph for comparing the live native
`HOptixDenoise` and `HOidnDenoise` nodes from the combined `HDenoiseNodes`
package on production EXR renders.

## Launch

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1"
```

The default setup uses:

- Nuke 17.0v3
- OptiX 9.1
- OIDN 2.5.0 on CUDA
- the Canyon Run production multipart EXR
- beauty `C` (exposed by Nuke as `rgba`), albedo `albedo`, and normal `N`

Select another built runtime pair:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1" `
  -NukeVersion "15.1v4" `
  -OptixVersion "9.0"
```

Use another multipart EXR:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1" `
  -InputExr "H:\renders\shot.1001.exr" `
  -BeautyLayer "C" `
  -AlbedoLayer "albedo" `
  -NormalLayer "N"
```

## Graph

Open `HDU_PLAYGROUND_CONTROLS` to switch the Viewer between:

- source beauty
- live OptiX beauty only
- live guided OptiX
- live OIDN beauty only
- live guided OIDN
- amplified live OptiX/OIDN difference

The graph contains Write nodes for both denoisers' beauty-only and guided
results, plus the amplified difference image.

`HOidnDenoise` is a normal Nuke image node with beauty, albedo, and normal
inputs. Its OIDN execution is delegated to the packaged `HOidnBridge.exe`
process to prevent Intel runtime DLLs from colliding with Nuke's private Visual
C++ and oneTBB libraries. The exchange uses raw float buffers, not cached EXRs.

## Validation

Run the graph headlessly and render the guided OptiX result, guided OIDN result,
and their difference:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1" `
  -ValidateOnly
```

Generated files are stored under:

```text
%TEMP%\hdu-nuke-playground\<scene-name>\
```

The launcher performs no downloads and does not modify the global Nuke plugin
path. It sets `NUKE_PATH` only for the child Nuke process and requires an
existing `HDenoiseNodes` package for the selected Nuke and OptiX versions.
