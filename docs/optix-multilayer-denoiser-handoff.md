# OptiX Multilayer Denoiser Handoff

Last updated: 2026-05-16

This is a handoff note for future agents continuing the Houdini-free OptiX denoiser experiment. The short version: the Python prototype can produce correct multilayer EXR output with in-process OpenImageIO, and the forked C++ denoiser now has a validated direct multipart EXR path for the Canyon Run sample.

## Repositories And Branches

Primary repo:

- Repository: `Ahmed-Hindy/h_denoise_utils`
- Experiment worktree: `C:\Users\Ahmed Hindy\.codex\worktrees\7de0\h_denoise_utils`
- Branch: `ci/optix-multilayer-aov-experiment`
- Current workflow pin while this note is being updated: fork commit `cdd8e82fa01cb2196905392519f1b7d73c1aa217`
- Main user workspace remains separate at `G:\Projects\Dev\Github\h_denoise_utils`, usually on `feat/ui-denoising-lock`.

Forked denoiser repo:

- Repository: `Ahmed-Hindy/NvidiaAIDenoiser`
- Local clone: `G:\Projects\Dev\Github\NvidiaAIDenoiser`
- Branch: `hdu/multilayer-exr-output`
- Latest fork commit at this handoff: `cdd8e82 Advance multipart output subimages`
- Upstream base: `DeclanRussell/NvidiaAIDenoiser` tag `3.0`, original pinned commit `4910227d0a0d60dc93c6529bae7cf6e2744f97fd`
- OptiX SDK submodule pinned in CI to commit `fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd`

## Important Files

In `h_denoise_utils`:

- `.github/workflows/build-optix.yml`
  Builds the Windows `Denoiser.exe` artifact in GitHub Actions. It now points at `Ahmed-Hindy/NvidiaAIDenoiser` branch `hdu/multilayer-exr-output`, pins exact source commits, and uses `astral-sh/setup-uv` plus `uvx --from conan conan ...` instead of bare `pip install conan`.
- `tools/optix_multilayer_aov.py`
  Isolated Python prototype wrapper. It can inspect, selectively extract, denoise, and recompose multipart EXRs. It supports `--image-io-backend auto|oiio|hoiiotool`.
- `tests/test_optix_multilayer_aov.py`
  Focused tests for parsing, selective extraction, recomposition command construction, and auto-denoisable AOV filtering.

In `NvidiaAIDenoiser`:

- `src/main.cpp`
  Main C++ denoiser. The fork has fixes for multi-AOV copyback and first-pass direct multipart EXR support.
- `conanfile.txt`
  Uses `openimageio/[>=2.4 <4]`, static by default.

## Python Prototype Results

The prototype branch moved in stages:

- `216549a Add OptiX multilayer AOV prototype`
  Initial isolated wrapper using `hoiiotool` to extract each subimage, run standalone OptiX, and recompose multipart output.
- `35fcdcc Optimize OptiX multilayer prototype with OIIO`
  Added in-process Python OpenImageIO backend and kept `hoiiotool` fallback.

Measured on:

- Source: `G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr`
- Denoised planes: `C`, `directdiffuse`, `indirectdiffuse`
- Guides: `albedo`, `N`
- Source subimages: `22`

Timings seen so far:

- Original prototype with per-subimage `hoiiotool` extraction: `25.987s`
- Batched `hoiiotool` extraction: `9.740s`
- Selective extraction and source-backed recomposition: `8.351s`
- Python in-process OIIO backend: `4.760s`
- Houdini `idenoise` baseline: about `1.684s`

Validation for Python OIIO backend:

- Output preserved `22/22` subimages.
- Extracted only `5` temp planes: `C`, `albedo`, `N`, `directdiffuse`, `indirectdiffuse`.
- All-plane diff had `0` failures.
- `C`, `directdiffuse`, `indirectdiffuse` matched Houdini OptiX output.
- Untouched AOVs matched source.

Important runtime note:

- System Python did not have `OpenImageIO`.
- Successful Python OIIO runs used Houdini's Python and Houdini's bundled OIIO binding.
- The prototype falls back to `hoiiotool` when Python OIIO is unavailable.

## GitHub Actions Build Work

Workflow: `.github/workflows/build-optix.yml`

Current behavior:

- Builds on `windows-2022`.
- Uses CUDA `12.9.0`.
- Uses `actions/setup-python@v6`.
- Uses `astral-sh/setup-uv@v6`.
- Uses `uvx --from conan conan ...` for Conan operations.
- Uploads `optix-denoiser-windows-x64` and `optix-build-diagnostics`.

Successful runs:

- Run `25967909134`
  Built fork commit `9c6d5f498cceacda59467e5dd1db9b27b2d12c0f`.
  Artifact source was the multi-AOV copyback fix.
- Run `25968397283`
  Built fork commit `c4f741945cbd84e63e5f5ac3cd8fbb2d59d65cb6`.
  Artifact source included initial direct multipart EXR mode.
- Run `25968596239`
  Built fork commit `b9baf17374583689f03400b510e2cdc419c0b914`.
  Artifact source opened the multipart output with all subimage specs up front.
- Run `25969000605`
  Built fork commit `861fa7a5105d3ed846c9e849274ec81d71feb29b`.
  Compile succeeded after replacing the failing `ImageInput::read_image` call with `ImageBuf::get_pixels`.
- Run `25969194038`
  Built fork commit `cdd8e82fa01cb2196905392519f1b7d73c1aa217`.
  Artifact source advances multipart output subimages with `AppendSubimage`.

Failed run:

- Run `25968791148`
  Builds fork commit `343b570e4fb41477f4b4c7376c8814efb0e18082`.
  This was the buffered unchanged-plane copy fix, but it failed during compile.
  The build error was:
  `main.cpp(381,25): error C2661: 'OpenImageIO::v3_1::ImageInput::read_image': no overloaded function takes 2 arguments`
  The CI OpenImageIO version exposes span-based `ImageInput::read_image` overloads, not the older two-argument `(TypeDesc, pointer)` overload.

Validated build target:

- Fork commit `cdd8e82fa01cb2196905392519f1b7d73c1aa217`
  Keeps the multi-subimage upfront `open(out_path, count, specs)` call, then follows OIIO's documented pattern by reopening with `AppendSubimage` before writing each subimage after the first.
  Built in run `25969194038` and passed the Canyon Run multipart validation.

## C++ Fork Changes

Commit `9c6d5f4 Fix multi-AOV output buffer copyback`:

- Replaced `std::unordered_map<int, ImageInfo>` with `std::map<int, ImageInfo>` so AOV IDs iterate deterministically.
- Fixed the copy-back loop from:
  `aov_pixels[0]`
  to:
  `aov_pixels[i - 1]`
- This fixed one-call multi-AOV behavior.

Validation for `9c6d5f4` artifact:

- Artifact run: `25967909134`
- Local artifact path: `%TEMP%\hdu-optix-fork-artifact-25967909134\Denoiser.exe`
- One-call command denoised `C`, `directdiffuse`, and `indirectdiffuse` together.
- Denoise time: `2.567s`
- Diffs against Houdini output:
  - `C`: `PASS`
  - `directdiffuse`: `PASS`
  - `indirectdiffuse`: `PASS`
- Summary file:
  `%TEMP%\hdu-onecall-aov-fork-20260516-202930\summary.json`

Commit `c4f7419 Add direct multipart EXR mode`:

- Added command-line mode:
  - `-multipart <input.exr>`
  - `-beauty-name <name>` default `C`
  - `-albedo-name <name>` default `albedo`
  - `-normal-name <name>` default `N`
  - `-aov-name0 <name>`, `-aov-name1 <name>`, etc.
- Uses OIIO to inspect subimages and load selected planes directly from one multipart EXR.
- Feeds selected planes into the existing OptiX flow.
- Attempts to write one multipart EXR with denoised replacements and unchanged source planes.

Runtime result for `c4f7419` artifact:

- Artifact run: `25968397283`
- Compile succeeded.
- Runtime failed while appending subimage 1.
- Error:
  `openexr not opened properly for subimages`
- Output only contained subimage 0 (`C`), which diffed `PASS`.
- Summary file:
  `%TEMP%\hdu-cpp-multipart-20260516-203813\summary.json`

Commit `b9baf17 Open multipart output with all subimage specs`:

- Changed writer to call OIIO multi-subimage `open(out_path, count, specs)` before writing all parts.

Runtime result for `b9baf17` artifact:

- Artifact run: `25968596239`
- Compile succeeded.
- Output listed `22` subimages, but the process exited with `-1073740791`.
- Diffs failed because extracted candidate planes were zero/corrupt.
- Key error:
  `Failed OpenEXR copy: Quick pixel copy ... failed. The files have different channel lists., falling back to the default image copy routine.`
- This points to `ImageOutput::copy_image(input.get())` being unsafe here after opening all output parts.
- Summary file:
  `%TEMP%\hdu-cpp-multipart-20260516-204735\summary.json`

Commit `343b570 Copy unchanged multipart planes through buffers`:

- Replaced `output->copy_image(input.get())` for unchanged planes with explicit:
  - `input->read_image(OIIO::TypeDesc::FLOAT, pixels.data())`
  - `output->write_image(OIIO::TypeDesc::FLOAT, pixels.data())`
- This should avoid the OpenEXR quick-copy path and channel-list mismatch issue.
- CI run `25968791148` failed to compile because the runner's OpenImageIO `ImageInput::read_image` no longer has the two-argument overload used here.

Commit `861fa7a Fix multipart unchanged-plane reads`:

- Keeps the buffered unchanged-plane copy strategy.
- Replaces the failing `ImageInput::read_image` call with:
  - `OIIO::ImageBuf source_plane(multipart.filename, subimage.index, 0)`
  - `source_plane.init_spec(...)`
  - `source_plane.get_pixels(roi, OIIO::TypeDesc::FLOAT, pixels.data())`
- This avoids the uncertain `ImageInput` overload and uses the same `ImageBuf::get_pixels` API that already compiled elsewhere in this file.
- The `h_denoise_utils` workflow pinned and built this commit in run `25969000605`.
- Runtime still failed after denoising with exit code `-1073741819`.
- The output file advertised `22` subimages, but diff/extraction showed corrupt pixel data. OpenEXR reported invalid chunk leaders such as:
  `Invalid part number reconstructing chunk table: expect 1, found 0`
- That means all writes were still landing in part `0`; the writer had declared all subimages, but was not advancing the active output part before each `write_image`.

Commit `cdd8e82 Advance multipart output subimages`:

- Adds `AppendSubimage` advancement inside `writeMultipartOutput` for subimages after the first.
- This follows OIIO's documented multi-subimage writing pattern: declare all specs up front, write subimage 0, then call `open(out_path, spec, AppendSubimage)` before writing later subimages.
- Built successfully in h_denoise_utils Actions run `25969194038`.
- Local artifact path:
  `%TEMP%\hdu-optix-multipart-artifact-25969194038\Denoiser.exe`
- Direct multipart validation command exited `0`.
- Output path:
  `%TEMP%\hdu-cpp-multipart-20260516-211541\cpp_multipart_optix.exr`
- Output inspection reported `22` subimages.
- Validation summary:
  `%TEMP%\hdu-cpp-multipart-20260516-211541\summary.validation.json`
- Diffs that passed:
  - `C` subimage `0` against Houdini OptiX output
  - `directdiffuse` subimage `6` against Houdini OptiX output
  - `indirectdiffuse` subimage `15` against Houdini OptiX output
  - `depth` subimage `5` against the original source
  - `P` subimage `21` against the original source
- Runtime log showed:
  - `Denoising complete in 0.016 seconds`
  - `Written out: ...\cpp_multipart_optix.exr`
  - `Done!`

## Useful Test Commands

Run one-call multi-AOV against extracted planes:

```powershell
$denoiser = "$env:TEMP\hdu-optix-fork-artifact-25967909134\Denoiser.exe"
$extract = "$env:TEMP\hdu-multilayer-oiio-20260516-195051\prototype_work\extract"
& $denoiser -v 1 `
  -i "$extract\000_C.exr" `
  -o "$env:TEMP\C_onecall.exr" `
  -a "$extract\001_albedo.exr" `
  -n "$extract\020_N.exr" `
  -aov0 "$extract\006_directdiffuse.exr" `
  -oaov0 "$env:TEMP\directdiffuse_onecall.exr" `
  -aov1 "$extract\015_indirectdiffuse.exr" `
  -oaov1 "$env:TEMP\indirectdiffuse_onecall.exr"
```

Run direct C++ multipart mode:

```powershell
$denoiser = "$env:TEMP\hdu-optix-multipart-artifact-<run-id>\Denoiser.exe"
$source = "G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr"
$output = "$env:TEMP\cpp_multipart_optix.exr"
& $denoiser -v 1 `
  -multipart $source `
  -o $output `
  -aov-name0 directdiffuse `
  -aov-name1 indirectdiffuse
```

Inspect multipart output:

```powershell
$oiiotool = "C:\Program Files\Side Effects Software\Houdini 21.0.631\bin\hoiiotool.exe"
& $oiiotool --info -v -a $output
```

Diff a subimage:

```powershell
& $oiiotool $reference --subimage 6 -o "$env:TEMP\ref_directdiffuse.exr"
& $oiiotool $output --subimage 6 -o "$env:TEMP\candidate_directdiffuse.exr"
& $oiiotool "$env:TEMP\ref_directdiffuse.exr" "$env:TEMP\candidate_directdiffuse.exr" --diff
```

## Next Steps

1. Wire `tools/optix_multilayer_aov.py` or the app integration to prefer direct C++ `-multipart` mode when a compatible compiled `Denoiser.exe` is available.
2. Keep the Python OIIO/hoiiotool prototype path as a fallback until the C++ mode is exercised on more production EXRs.
3. Broaden validation beyond the Canyon Run sample:
   - different AOV name sets
   - missing guide planes
   - non-`C` beauty names
   - EXRs with unusual data windows or channel formats
4. Profile end-to-end runtime for the direct C++ path against the current Python OIIO prototype and Houdini `idenoise` baseline.
5. If future runtime failures appear, inspect multipart EXR writing first; the denoising output matched Houdini once the writer produced valid parts.

## Current Strategic Read

- The Python OIIO prototype proves the data path and metadata preservation approach.
- The C++ denoiser copyback bug was real and is fixed; one-call multi-AOV now matches Houdini.
- Direct C++ multipart output is now validated on the Canyon Run sample.
- Best production direction is still C++ OIIO inside the denoiser, because it removes Python, Houdini, `hoiiotool`, and temp EXR extraction/recomposition from the hot path.
