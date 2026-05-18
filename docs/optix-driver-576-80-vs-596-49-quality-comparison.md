# OptiX Driver 576.80 vs 596.49 Denoise Comparison

Date: 2026-05-18

Branch: `optix-bundled-denoiser`

## Goal

Re-test the Canyon Run multipart EXR after upgrading the local NVIDIA driver from `576.80` to `596.49`, using all bundled OptiX runtimes shipped by the Houdini-free branch:

- OptiX 8.1
- OptiX 9.0
- OptiX 9.1

The test checks three things:

- Whether OptiX 8.1, 9.0, and 9.1 produce different output on the same new driver.
- Whether the new driver changes output compared with the older `576.80` baseline.
- Whether source OpenEXR header metadata is preserved in the new outputs.

This is not a ground-truth quality benchmark because no clean reference render was available. Pixel differences here prove that output changed, not that quality improved.

## Environment

```text
NVIDIA-SMI: 596.49
Driver Version: 596.49
CUDA Version reported by nvidia-smi: 13.2
GPU: NVIDIA GeForce RTX 3070
Driver model: WDDM
```

Pixel comparison used a temporary Python analysis environment with:

```text
OpenImageIO 3.1.13.1
numpy 2.4.5
```

## Input

```text
G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr
```

Command shape used for every runtime:

```powershell
Denoiser.exe `
  -v 1 `
  -multipart <input.exr> `
  -o <output.exr> `
  -beauty-name C `
  -albedo-name albedo `
  -normal-name N `
  -aov-name0 directdiffuse `
  -aov-name1 indirectdiffuse
```

New outputs were written locally under:

```text
G:\Projects\Dev\Github\h_denoise_utils\comparison_outputs\optix-8.1-vs-9.0-vs-9.1-canyon-run-driver-596.49
```

`comparison_outputs/` is ignored by Git because these EXRs are large local test artifacts.

## Bundled Runtime Matrix

Top-level bundled denoiser manifest:

```text
release repository: https://github.com/Ahmed-Hindy/NvidiaAIDenoiser
release tag: optix-denoiser-v2026.05.18
source commit: fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf
default OptiX runtime: 9.0
```

| Runtime | Denoiser path | OptiX SDK tag | OptiX SDK commit | Denoiser.exe SHA-256 |
| --- | --- | --- | --- | --- |
| OptiX 8.1 | `h_denoise_utils\vendor\optix-denoiser\windows-x64\optix-8.1\Denoiser.exe` | `v8.1.0` | `50021ea0af6d41609a97777ceebbdf1e1d34efe7` | `658f3b709248893c1d73dc5cb54212cb45c05430d3b97cc8b42c8032ca396163` |
| OptiX 9.0 | `h_denoise_utils\vendor\optix-denoiser\windows-x64\optix-9.0\Denoiser.exe` | `v9.0.0` | `fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd` | `a1db36ea26f91d81c0e3f22adbbf369bada21e52efc47f7b9f40518593b3a17a` |
| OptiX 9.1 | `h_denoise_utils\vendor\optix-denoiser\windows-x64\optix-9.1\Denoiser.exe` | `v9.1.0` | `f1f6dd803f3159992d248178f6e09421c6eb8b6d` | `45f6a926d7abe4b0be86a9d03e8f0ba5d58a13c333cd94fb1e534b2b03320f20` |

All three executable files are `78138880` bytes and were built on the Windows x64 GitHub runner with CUDA `12.9.0`.

## Output Files

| Runtime | Output file | Size | Output SHA-256 | Denoiser-reported GPU time |
| --- | --- | ---: | --- | ---: |
| OptiX 8.1 | `CanRun_sh001_renderFxMain_v001.driver-596.49.optix-8.1.exr` | `66403621` bytes | `F192344C6E763454694DEEB2CFF33042F8AC48643637DF8EE94B5EBF64CC948D` | `0.031s` |
| OptiX 9.0 | `CanRun_sh001_renderFxMain_v001.driver-596.49.optix-9.0.exr` | `66403621` bytes | `F192344C6E763454694DEEB2CFF33042F8AC48643637DF8EE94B5EBF64CC948D` | `0.014s` |
| OptiX 9.1 | `CanRun_sh001_renderFxMain_v001.driver-596.49.optix-9.1.exr` | `66403621` bytes | `F192344C6E763454694DEEB2CFF33042F8AC48643637DF8EE94B5EBF64CC948D` | `0.014s` |

The old `576.80` baseline outputs were:

```text
G:\Projects\Dev\Github\h_denoise_utils\comparison_outputs\optix-8.1-vs-9.0-canyon-run\CanRun_sh001_renderFxMain_v001.optix-8.1.exr
G:\Projects\Dev\Github\h_denoise_utils\comparison_outputs\optix-8.1-vs-9.0-canyon-run\CanRun_sh001_renderFxMain_v001.optix-9.0.exr
```

Both old baseline files had SHA-256:

```text
E714615DE1A9A8EF164B0C891F8C3AFA9938B3CB933515D2E1717E0D37E786EB
```

## Same-Driver Runtime Comparison

On driver `596.49`, all three bundled runtime outputs were byte-identical and pixel-identical.

| Comparison | Subimages | Values compared | Different values | Max abs diff | Mean abs diff | RMSE | Pixel-identical |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `596.49` OptiX 8.1 vs `596.49` OptiX 9.0 | 22 | 62668800 | 0 | 0.0 | 0.0 | 0.0 | true |
| `596.49` OptiX 8.1 vs `596.49` OptiX 9.1 | 22 | 62668800 | 0 | 0.0 | 0.0 | 0.0 | true |
| `596.49` OptiX 9.0 vs `596.49` OptiX 9.1 | 22 | 62668800 | 0 | 0.0 | 0.0 | 0.0 | true |

Every subimage had `0` different values, `0.0` max abs diff, and `0.0` RMSE for all same-driver runtime comparisons.

## Old Driver vs New Driver Comparison

The new driver changed output compared with the old `576.80` baseline. The change was identical for all three new runtime outputs because the new-driver 8.1, 9.0, and 9.1 files are byte-identical.

| Comparison | Subimages | Values compared | Different values | Max abs diff | Mean abs diff | RMSE | Pixel-identical |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `576.80` OptiX 8.1 vs `596.49` OptiX 8.1 | 22 | 62668800 | 7977409 | 0.485595703125 | 0.0001886060542740488 | 0.0012947040803817909 | false |
| `576.80` OptiX 9.0 vs `596.49` OptiX 9.0 | 22 | 62668800 | 7977409 | 0.485595703125 | 0.0001886060542740488 | 0.0012947040803817909 | false |
| `576.80` identical 8.1/9.0 baseline vs `596.49` OptiX 9.1 | 22 | 62668800 | 7977409 | 0.485595703125 | 0.0001886060542740488 | 0.0012947040803817909 | false |

Only the denoised planes changed:

| Subimage | Name | Different values | Max abs diff | Mean abs diff | RMSE |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0 | `C` | 2681635 | 0.485595703125 | 0.0019987858562833735 | 0.004995693237247993 |
| 6 | `directdiffuse` | 2614807 | 0.0439453125 | 0.0013276987880709822 | 0.002123019108279876 |
| 15 | `indirectdiffuse` | 2680967 | 0.012664794921875 | 0.00028232396709629233 | 0.0004604905016710723 |

All other subimages had `0` different values, `0.0` max abs diff, and `0.0` RMSE in the old-driver vs new-driver comparisons.

There was no valid old-driver OptiX 9.1 output because OptiX 9.1 previously failed locally on driver `576.80` with `optixInit` error `7801`.

## Metadata Preservation

Raw OpenEXR header metadata was compared from the source EXR to each new output using the branch's pure Python EXR header reader.

| Output runtime | Source part count | Output part count | Raw attribute value diff count | Attribute order diff count |
| --- | ---: | ---: | ---: | ---: |
| OptiX 8.1 | 22 | 22 | 0 | 0 |
| OptiX 9.0 | 22 | 22 | 0 | 0 |
| OptiX 9.1 | 22 | 22 | 0 | 0 |

Result: all tested new-driver outputs preserved the source EXR part headers exactly, including attribute values and attribute order.

## Run Notes

The frozen app smoke test passed for the default runtime and explicit `HDU_OPTIX_VERSION` values `8.1`, `9.0`, and `9.1`.

The first attempt to launch the 9.1 executable through a `Start-Process` helper failed with `Access is denied`, but direct invocation of the same `Denoiser.exe` succeeded. The successful 9.1 denoise output matches the 8.1 and 9.0 outputs exactly.

## Conclusion

On this Canyon Run validation frame, bundled OptiX 8.1, 9.0, and 9.1 produce identical output when run on NVIDIA driver `596.49`.

Upgrading the NVIDIA driver from `576.80` to `596.49` changed the denoised pixel output for the tested frame. The measurable differences are limited to `C`, `directdiffuse`, and `indirectdiffuse`; albedo, normal, position, depth, and untouched AOVs remained identical.

This test does not prove a general denoising quality improvement because there is no clean ground-truth render. The safe conclusion is that the driver upgrade changes OptiX denoiser output on this frame and enables local validation of the OptiX 9.1 bundled runtime on this workstation.
