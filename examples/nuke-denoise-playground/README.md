# Nuke OptiX + OIDN playground

This folder provides a ready Nuke graph for comparing the native
`HOptixDenoise` node with the bundled OIDN multipart EXR wrapper.

## Launch

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1"
```

The default setup uses:

- Nuke 17.0v3
- OptiX 9.1
- OIDN 2.5.0
- the Canyon Run production multipart EXR
- beauty `C` (exposed by Nuke as `rgba`), albedo `albedo`, and normal `N`

Select another validated runtime pair:

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
  -NormalLayer "N" `
  -RefreshOidn
```

## Graph

Open `HDU_PLAYGROUND_CONTROLS` to switch the Viewer between:

- source beauty
- OptiX beauty only
- OptiX with albedo
- OptiX with albedo and normal
- OIDN with guides
- amplified OptiX/OIDN difference

The graph also contains write nodes for the beauty-only OptiX result, the fully
guided OptiX result, and the amplified difference image.

OIDN is currently run by the bundled multipart command-line wrapper. Use the
**rerun OIDN and reload** button on the controls node after replacing the input
EXR or changing guide-layer arguments in the launcher.

## Validation

Run the same graph headlessly and render all comparison outputs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1" `
  -ValidateOnly
```

Generated files are stored under:

```text
%TEMP%\hdu-nuke-playground\<scene-name>\
```

The launcher does not download dependencies or modify the global Nuke plugin
path. It sets `NUKE_PATH` only for the child Nuke process and selects an existing
validated native package matching the requested Nuke and OptiX versions.
