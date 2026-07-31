# Nuke denoiser nodes handoff

Last updated: 2026-07-31

## Current state

Work remains on the draft pull request and must not be merged yet.

- Branch: `dev/nuke-optix`
- Head: `3b6d828d4ddfd48b5802cdc1739fa65f71c81da8`
- Pull request: [#44 — Add native OptiX and OIDN Nuke nodes](https://github.com/Ahmed-Hindy/h_denoise_utils/pull/44)
- Base: `main`
- PR state: draft, mergeable, clean

The branch provides one Windows Nuke package containing two native `PlanarIop`
nodes:

- `HOptixDenoise`
- `HOidnDenoise`

Both nodes use beauty, optional albedo, and optional normal inputs. They are
registered under Nuke's **Filter** menu.

## Completed implementation

### HOptixDenoise

- Runs NVIDIA OptiX in the Nuke process.
- Uses the CUDA Driver API and does not link CUDART.
- Reuses the CUDA primary context, OptiX context, stream, denoiser, and GPU
  buffers across compatible renders.
- Supports input blending, tiling, GPU selection, signed or unsigned normal
  encoding, and passthrough on error.
- Resets retained resources after CUDA or OptiX failures.

### HOidnDenoise

- Is a real native Nuke image node, not a precomputed OIDN `Read` branch.
- Supports input blending, GPU selection, Fast/Balanced/High quality, HDR input,
  clean auxiliary guides, normal encoding, and passthrough on error.
- Uses the OIDN 2.5.0 CUDA backend.
- Exchanges tightly packed float buffers with `HOidnBridge.exe`; it does not
  create intermediate EXR files.
- Terminates the helper and removes temporary exchange files when Nuke aborts a
  render.

OIDN must remain outside the Nuke process. Nuke loads private Visual C++ and
oneTBB runtime DLLs that are incompatible with Intel's OIDN binary package.
Direct OIDN device creation inside Nuke produced deterministic access
violations. The isolated helper clears Nuke's inherited DLL search directory
before loading the packaged OIDN runtime.

The Nuke package intentionally includes only:

- `OpenImageDenoise.dll`
- `OpenImageDenoise_core.dll`
- `OpenImageDenoise_device_cuda.dll`

CPU, oneTBB, SYCL, and HIP modules are excluded.

## Packaging and validation

The Windows build script:

1. Reuses or fetches pinned OptiX, CUDA driver-header, and OIDN dependencies.
2. Builds both Nuke DLLs and the OIDN helper.
3. Inspects PE dependencies with `dumpbin`.
4. Renders through both nodes in Nuke terminal mode.
5. Records binary hashes, sizes, dependencies, SDK versions, source commit, and
   validation state in `manifest.json`.
6. Creates a combined release ZIP under `dist/`.

The release validator rejects:

- missing node, helper, or OIDN runtime files
- altered hashes or sizes
- direct OIDN linkage from `HOidnDenoise.dll`
- missing `DDImage.dll` or CUDA Driver imports
- CUDART linkage in `HOptixDenoise.dll`
- unsupported Nuke/OptiX combinations
- incomplete 12-package matrices
- packages produced with render validation disabled

The build environment setup is idempotent. Repeated matrix builds in one
PowerShell process no longer duplicate Visual Studio and Ninja `PATH` entries.

## Validation completed

Local validation from commit `3b6d828`:

- 169 Python tests passed.
- Ruff passed across the repository.
- Workflow YAML and PowerShell parsing passed.
- Nuke node interface and render validation passed on:
  - Nuke `14.1v8`
  - Nuke `15.0v1`
  - Nuke `15.1v4`
  - Nuke `17.0v3`
- Each Nuke version was built against OptiX `8.1`, `9.0`, and `9.1`.
- All 12 final packages passed release-manifest, hash, dependency, source-commit,
  and matrix validation.
- The Canyon Run production multipart EXR rendered successfully through:
  - guided `HOptixDenoise`
  - guided `HOidnDenoise`
  - the live amplified OptiX/OIDN difference branch
- Invalid OIDN GPU selection returns a readable Nuke error without crashing.
- PR #44 hosted checks and CodeRabbit review pass.

## Playground

Launch the live comparison graph:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1"
```

Run the production-scene comparison headlessly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File ".\examples\nuke-denoise-playground\launch-nuke-playground.ps1" `
  -ValidateOnly
```

The graph contains live OptiX and OIDN beauty-only and guided branches, plus a
live difference branch. The launcher removes only the generated playground's
stale `.nk.autosave` file so Nuke cannot restore the previous cached-OIDN graph.

## Known limitations

- Nuke packages are currently built and validated only on Windows.
- Both nodes currently require an NVIDIA GPU.
- `HOptixDenoise` is spatial only; temporal denoising is not implemented.
- `HOidnDenoise` launches one helper process per evaluation and copies image
  buffers through a temporary binary file. This is robust but has measurable
  startup and host-I/O overhead.
- Package naming still centers `HOptixDenoise` even though the ZIP contains both
  nodes.
- The package has no public release yet.
- The `Nuke Denoiser Nodes` workflow requires a Windows self-hosted runner with
  the Nuke SDK, licenses, Visual Studio, and an NVIDIA GPU.

## Recommended next work

### 1. Manual Nuke acceptance pass

Do this before architecture or naming changes. In Nuke 17.0v3:

- Create both nodes from the **Filter** menu.
- Confirm input labels and optional guide behavior.
- Inspect knob names, defaults, tooltips, ranges, and layout.
- Test interactive Viewer changes, frame changes, and repeated renders.
- Abort a large OIDN render and confirm the helper process exits immediately.
- Test passthrough-on-error for invalid GPUs and missing helper/runtime files.
- Save, close, and reopen a script containing both nodes.

Record any UX or serialization issues before changing package identity.

### 2. Benchmark the OIDN bridge

Measure beauty-only and guided OIDN renders at representative 2K and 4K sizes.
Separate:

- Nuke plane packing
- exchange-file write
- helper startup
- OIDN execution
- result readback

Use the measurements to decide whether a persistent helper process is worth the
additional protocol and lifecycle complexity. Keep OIDN process isolation even
if the helper becomes persistent.

### 3. Decide package identity before the first release

The current extracted directory and manifest name are `HOptixDenoise`, while
the package contains both nodes. Before publishing, decide whether to keep that
compatibility name or rename the combined package to something neutral such as
`HDenoiseNodes` or `h-denoise-nuke`.

A rename should update the install directory, manifest name, build workflow,
release validator, documentation, package filename, and release tag together.
This is easier before the first public Nuke package has users.

### 4. Run the self-hosted Nuke workflow

After manual acceptance and the naming decision:

- register or verify the Windows `nuke-ndk` self-hosted runner
- dispatch one Nuke 17.0/OptiX 9.1 build
- inspect the uploaded package
- dispatch the supported 12-package matrix
- keep release publication disabled

### 5. Release only after the branch is accepted

Do not merge or publish from the current handoff state. After the manual pass,
benchmark decision, naming decision, and self-hosted workflow validation, make
PR #44 ready for review. Merge and release should remain separate explicit
steps.

## Deferred work

These are not required for the first release:

- temporal OptiX state in Nuke
- Linux Nuke packages
- CPU OIDN inside Nuke packages
- persistent OIDN helper service
- multi-frame helper batching
- non-NVIDIA OIDN backends

## Working-tree caution

The worktree contains old untracked local artifacts that are not part of PR #44
and must not be staged:

- `nul`
- `tools/build_optix_denoiser.ps1`
- `tools/build_optix_denoiser_windows.ps1`
- `tools/fetch_optix_denoiser.ps1`
