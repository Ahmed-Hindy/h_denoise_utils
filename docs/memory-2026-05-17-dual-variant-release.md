# Memory: Dual Variant Release And Metadata-Preserving OptiX Work

Last updated: 2026-05-17

This file records the work done across the recovered prior conversation and the current conversation, so future agents can continue without reconstructing it from chat history.

## Final Repository State

- Default branch: `main`
- Main release line: Houdini-linked app behavior
- Second long-running branch: `optix-bundled-denoiser`
- Current app release: `v1.3.0`
- App release URL: `https://github.com/Ahmed-Hindy/h_denoise_utils/releases/tag/v1.3.0`
- Bundled denoiser source release: `https://github.com/Ahmed-Hindy/NvidiaAIDenoiser/releases/tag/hdu-multilayer-exr-output-8893b60`

Release `v1.3.0` contains two Windows artifacts:

- `h-denoise-houdini-windows-x64-v1.3.0.zip`
- `h-denoise-optix-windows-x64-v1.3.0.zip`

Release SHA manifest:

- Houdini app: `4a2b7a6e3387ffc196ecf59b268bc249cec5fa97`
- OptiX app: `20f7cc975ba5b31d237b886b261489cd35046125`
- Bundled OptiX denoiser: `8893b605903f273512b750d45993bbe27a003362`

Release asset digests observed after publish:

- Houdini zip: `sha256:4a970786bf1934cc4822d762fba9ef372de6b8baa640a7fdea6ecc092c30237e`
- OptiX zip: `sha256:b9d6744456152e20d3f02de5a14804efccbf8ed019451488f47ad61a56026245`

## User Intent Captured

The user wanted:

- `main` to remain the default Houdini-linked behavior.
- A second branch for a clean Houdini-free bundled OptiX build.
- Both variants released from one GitHub release page.
- Metadata preservation to mean all OpenEXR header metadata, not just colorspace.
- The OptiX package to use the validated compiled denoiser pinned to commit `8893b605903f273512b750d45993bbe27a003362`.
- Future agents to have Markdown memory/handoff files with enough detail to continue safely.

## Prior Conversation: OptiX Denoiser Validation

The prior thread investigated whether Houdini `idenoise` output and the built OptiX denoiser output were equivalent, including colorspace and metadata.

Important result:

- Pixel output for the selected denoised planes matched Houdini OptiX output.
- The final validated built denoiser preserved source OpenEXR part headers.
- Raw source-vs-built OpenEXR header metadata diff count was `0`.
- Attribute order diff count was `0`.
- The output contained all `22` source parts.

Primary Canyon Run source:

```text
G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr
```

Validated output from the previous thread:

```text
%TEMP%\hdu-cpp-multipart-20260517-011920\cpp_multipart_optix.exr
```

Validated built denoiser artifact source:

```text
%TEMP%\hdu-optix-multipart-artifact-25974285778\Denoiser.exe
```

That artifact came from fork commit:

```text
8893b605903f273512b750d45993bbe27a003362
```

The previous handoff file with the deepest experiment detail exists on branch `ci/optix-multilayer-aov-experiment`:

```text
docs/optix-multilayer-denoiser-handoff.md
```

That document records the Python prototype, OIIO timings, failed C++ build attempts, OpenEXR include fixes, and the final metadata-preserving validation.

## Prior Conversation: Experiment Branch Timeline

Branch `ci/optix-multilayer-aov-experiment` contains the incremental denoiser investigation.

Key commits:

- `216549a Add OptiX multilayer AOV prototype`
- `35fcdcc Optimize OptiX multilayer prototype with OIIO`
- `8d81592 Build forked OptiX denoiser with uv`
- `aa797b2 Build direct multipart OptiX fork`
- `1fd6593 Build multipart writer fix`
- `0b9fe04 Build buffered multipart copy fix`
- `e9a0ab4 Document OptiX multilayer denoiser handoff`
- `f79411b Build fixed multipart denoiser commit`
- `8bb12c4 Build multipart subimage advancement fix`
- `efca3b1 Document validated multipart OptiX output`
- `f6dcc48 Build denoiser with preserved EXR colorspace`
- `2b84311 Build denoiser with preserved EXR headers`
- `6ca5ca4 Build denoiser with OpenEXR include fix`
- `164d2e4 Build denoiser with direct OpenEXR headers`
- `63cfebb Document metadata-preserving denoiser validation`

The final successful Actions build for the denoiser artifact was run `25974285778`. Earlier failed or partial runs are documented in `docs/optix-multilayer-denoiser-handoff.md` on the experiment branch.

## Denoiser Release Created

A stable GitHub release was created in `Ahmed-Hindy/NvidiaAIDenoiser` so the app release workflow could fetch the pinned executable:

```text
tag: hdu-multilayer-exr-output-8893b60
asset: optix-denoiser-windows-x64-8893b60.zip
source commit: 8893b605903f273512b750d45993bbe27a003362
```

The app-side fetch script is:

```text
tools/fetch_optix_denoiser.ps1
```

It installs to:

```text
h_denoise_utils/vendor/optix-denoiser/windows-x64/Denoiser.exe
```

The vendor directory is ignored by Git. For development, `HDU_DENOISER_EXE` can override the bundled executable path.

## Current Conversation: Main Branch Work

Branch `main` preserves the Houdini-linked behavior and release tooling.

Main commits created:

- `7d758e4 Add dual variant release packaging`
- `4a2b7a6 Bump version to 1.3.0`

Main branch changes:

- Kept the existing Houdini-linked app behavior.
- Kept `idenoise`, Houdini discovery, `hoiiotool` AOV scanning, OIDN/OptiX backend choice, temporal UI, `--options`, `--exrmode`, and custom executable picker.
- Updated package naming to `h-denoise-houdini-windows-x64-vX.Y.Z.zip`.
- Added `.github/workflows/release.yml` for dual-variant releases.
- Updated `.github/workflows/ci.yml` to build the Houdini-named package from `main`.
- Added `docs/release-variants.md`.
- Bumped version to `1.3.0` in `pyproject.toml`, `h_denoise_utils/__init__.py`, and `uv.lock`.
- Added `.github/release-notes/v1.3.0.md`.
- Updated `CHANGELOG.md`.
- Fixed `tools/github_release_metadata.ps1` for Windows PowerShell compatibility:
  - replaced the non-ASCII dash in the generated title with ASCII `-`
  - replaced multi-argument `Join-Path` usage with `[System.IO.Path]::Combine(...)`

Local validation on `main`:

```text
uv run --native-tls pytest --tb=short
93 passed
```

Remote validation:

- `main` CI run `25990367125`: success
- tag CI run `25990378579`: success
- Release Variants run `25990378569`: success

## Current Conversation: OptiX Branch Work

Branch `optix-bundled-denoiser` is the clean Houdini-free line.

OptiX branch commit created:

- `20f7cc9 Add bundled OptiX denoiser variant`

OptiX branch runtime changes:

- Removed Houdini discovery from the branch runtime surface.
- Removed `idenoise` command builder/export from the OptiX branch.
- Added bundled denoiser resolver:
  - `h_denoise_utils/discovery/bundled_denoiser.py`
  - `PINNED_DENOISER_COMMIT = 8893b605903f273512b750d45993bbe27a003362`
  - `HDU_DENOISER_EXE` development override
- Added pure Python EXR header parser:
  - `h_denoise_utils/discovery/exr_inspector.py`
  - parses OpenEXR magic/version, multipart flag, string attributes, `chlist`, multipart part names, and layered channel stems
- Added bundled OptiX command builder:
  - `Denoiser.exe -v 1 -multipart input.exr -o output.exr -beauty-name C ...`
- Limited app config/backend to OptiX only.
- Limited input extensions to `.exr`.
- Updated `Denoiser` orchestration to reject legacy Houdini-only settings.
- Updated UI to expose only validated bundled OptiX v1 controls:
  - beauty plane
  - albedo plane
  - normal plane
  - selected AOV names
  - overwrite
  - prefix
  - output destination
  - bundled runtime status
- Removed UI controls for:
  - Houdini executable selection
  - backend selection
  - CPU threads
  - temporal/motion vectors
  - SideFX JSON options
  - SideFX EXR mode
  - extra AOVs
- Added package inclusion of `h_denoise_utils/vendor/optix-denoiser`.
- Added OptiX branch CI package fetch/build path.
- Updated README and `pyproject.toml` description for the bundled OptiX app.
- Added tests:
  - `tests/test_bundled_denoiser.py`
  - `tests/test_exr_inspector.py`
  - updated command/config/UI tests for the OptiX branch
- Added branch-specific handoff:
  - `docs/agent-handoff-optix-bundled-denoiser.md`

Local validation on `optix-bundled-denoiser`:

```text
uv run --native-tls pytest --tb=short
91 passed

.\tools\build_windows_package.ps1 -Variant optix
dist/h-denoise-optix-windows-x64-v1.3.0.zip
```

The local OptiX zip was checked to contain:

```text
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/Denoiser.exe
h-denoise/_internal/h_denoise_utils/vendor/optix-denoiser/windows-x64/manifest.json
```

Remote validation:

- OptiX branch CI run `25990371531`: success
- OptiX package job fetched the bundled denoiser, built the portable package, and uploaded the artifact.

## Release Workflow Behavior

The release workflow is triggered by tags such as `v1.3.0`.

It checks out:

- `main` at the tag commit for the Houdini package
- `optix-bundled-denoiser` at branch HEAD for the OptiX package

It then:

- verifies `pyproject.toml` versions match
- verifies the tag version matches the package version
- builds the Houdini package with `tools/build_windows_package.ps1 -Variant houdini`
- fetches the pinned OptiX denoiser in the OptiX checkout
- builds the OptiX package with `tools/build_windows_package.ps1 -Variant optix`
- publishes or updates one GitHub release
- appends the package matrix and SHA manifest to the release notes
- uploads both zip artifacts with `--clobber`

Important rule:

- Before tagging a future release, update `pyproject.toml`, `h_denoise_utils/__init__.py`, and `uv.lock` to the same version on both `main` and `optix-bundled-denoiser`.

## Commit Message Audit

I checked commit messages across local and remote branches with:

```powershell
git for-each-ref --format='%(refname:short)' refs/heads refs/remotes/origin
git log --all --format='%H`t%D`t%s`t%b' --max-count=80
git show --stat --oneline 4a2b7a6 20f7cc9 7d758e4 63cfebb d13dd4b
```

Branch refs checked:

- `main`
- `optix-bundled-denoiser`
- `feat/ui-denoising-lock`
- `fix/tooltip-text-consolidation`
- `ui/full-tooltip-coverage`
- `ci/optix-build-experiment`
- `ci/optix-multilayer-aov-experiment`
- previous `codex/*` branches still present locally
- matching `origin/*` refs

Findings:

- The most detailed commit body is `62db0f6 feat: lock UI controls during denoising run`, which explicitly lists UI lock implementation details and test coverage.
- The experiment branch commit subjects are descriptive and chronological, but most do not have long bodies. Detail is instead preserved in `docs/optix-multilayer-denoiser-handoff.md` on `ci/optix-multilayer-aov-experiment`.
- The released main/OptiX commits have concise subjects and no long bodies:
  - `7d758e4 Add dual variant release packaging`
  - `4a2b7a6 Bump version to 1.3.0`
  - `20f7cc9 Add bundled OptiX denoiser variant`
- I did not rewrite these messages after release because `v1.3.0` release notes record their exact SHAs. Rewriting would invalidate the published SHA manifest and tag history.
- This memory file is the supplemental detailed record for future agents.

Suggested commit message pattern for future work:

```text
Short imperative subject

- Why the change exists
- Runtime behavior changed
- Files or subsystems touched
- Validation commands and results
- Any intentional limitations or future work
```

## Released History To Preserve

Do not rewrite these without intentionally reissuing a release:

```text
v1.3.0 -> 4a2b7a6e3387ffc196ecf59b268bc249cec5fa97
main release workflow commit -> 7d758e4c19c29f869a13e3df06ee18b8b8838aab
optix branch release commit -> 20f7cc975ba5b31d237b886b261489cd35046125
bundled denoiser source -> 8893b605903f273512b750d45993bbe27a003362
```

## Current Feature Matrix

Houdini package:

- Full existing SideFX/Houdini feature set.
- Uses `idenoise`.
- Keeps OIDN and OptiX backend selection.
- Keeps temporal controls.
- Keeps SideFX options and EXR mode.
- Keeps Houdini discovery, `hoiiotool` AOV scanning, and custom executable picker.

OptiX package:

- Houdini-free Windows package.
- Uses bundled `Denoiser.exe`.
- Uses pure Python EXR header parsing for AOV discovery.
- Supports multipart EXR denoise with beauty/albedo/normal names and selected AOV names.
- Supports overwrite, prefix, and output destination.
- Preserves source OpenEXR metadata through the pinned denoiser.
- Does not expose temporal denoising, motion vectors, advanced OptiX flags, OIDN, SideFX JSON options, SideFX EXR mode, or custom executable selection in v1.

## Known Operational Notes

- `uv run` on this workstation may require `--native-tls` because plain TLS previously hit a local certificate issuer problem.
- The OptiX app smoke test requires the bundled denoiser to be present or `HDU_DENOISER_EXE` to be set.
- The release workflow fetches the denoiser asset using `gh release download`.
- If the denoiser release asset is replaced, verify `manifest.json` still reports `source_commit = 8893b605903f273512b750d45993bbe27a003362`.
- The app release `v1.3.0` was created after `v1.2.0` already existed; do not reuse existing tags.

## Useful Commands

Run tests:

```powershell
uv run --native-tls pytest --tb=short
```

Fetch the OptiX denoiser on the OptiX branch:

```powershell
.\tools\fetch_optix_denoiser.ps1
```

Build Houdini package:

```powershell
.\tools\build_windows_package.ps1 -Variant houdini
```

Build OptiX package:

```powershell
.\tools\build_windows_package.ps1 -Variant optix
```

Inspect release:

```powershell
gh release view v1.3.0 --repo Ahmed-Hindy/h_denoise_utils --json tagName,name,assets,url,body
```

Watch release workflow:

```powershell
gh run watch <run-id> --repo Ahmed-Hindy/h_denoise_utils --exit-status
```

## Next Safe Steps

- Manually download both `v1.3.0` zip assets and smoke test launches on a clean Windows machine.
- Run a real Canyon Run denoise through the released OptiX zip and confirm:
  - AOV scan finds 22 parts.
  - Output contains 22 parts.
  - Raw source-vs-output OpenEXR header metadata diff count remains `0`.
- Keep `main` and `optix-bundled-denoiser` version numbers aligned before any future app release tag.
