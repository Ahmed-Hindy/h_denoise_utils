# HOptixDenoise for Nuke

Native NVIDIA OptiX denoising inside Foundry Nuke.

## Install

Add this directory to `NUKE_PATH`, or copy its contents directly into your
`.nuke` directory. Restart Nuke after installation.

The node is available under **Filter > HOptixDenoise**.

## Inputs

1. `beauty` — required noisy RGB(A) render.
2. `albedo` — optional RGB albedo guide.
3. `normal` — optional RGB normal guide; requires albedo.

All connected inputs must have the same data window and resolution.

## Controls

- **input blend** — `0` is fully denoised; `1` is the original noisy input.
- **tile size** — smaller tiles reduce peak VRAM use.
- **GPU device** — zero-based CUDA device index.
- **normal encoding** — choose signed normals or remap unsigned normals to
  `-1..1`.
- **passthrough on error** — returns the beauty input if CUDA or OptiX fails.

## Requirements

- A supported NVIDIA GPU and driver.
- A package built specifically for your Nuke major/minor version.
- Windows. This package has not yet been built or validated for Linux.

The production package uses the CUDA Driver API. End users need a compatible
NVIDIA driver, but they do not need the CUDA Toolkit or a separate CUDA runtime
installed.
