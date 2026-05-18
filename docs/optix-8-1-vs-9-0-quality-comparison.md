# OptiX 8.1 vs 9.0 Denoise Comparison

Date: 2026-05-18

## Goal

Compare the bundled OptiX 8.1 and OptiX 9.0 denoiser outputs to check whether the 9.0 build improves denoising quality for the validated Canyon Run EXR test frame.

This is not a ground-truth quality benchmark because no clean reference render was available. The useful question for this test is whether OptiX 9.0 produces any pixel change relative to OptiX 8.1 under the exact same app command.

## Input

```text
G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr
```

Command shape used for both runtimes:

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

Outputs were written locally under:

```text
G:\Projects\Dev\Github\h_denoise_utils\comparison_outputs\optix-8.1-vs-9.0-canyon-run
```

`comparison_outputs/` is ignored by Git because these EXRs are large local test artifacts.

## Runtime Results

| Runtime | Output file | Size | Denoiser-reported GPU time |
| --- | --- | ---: | ---: |
| OptiX 8.1 | `CanRun_sh001_renderFxMain_v001.optix-8.1.exr` | `66147779` bytes | `0.013s` |
| OptiX 9.0 | `CanRun_sh001_renderFxMain_v001.optix-9.0.exr` | `66147779` bytes | `0.013s` |

Both output files had the same SHA-256:

```text
E714615DE1A9A8EF164B0C891F8C3AFA9938B3CB933515D2E1717E0D37E786EB
```

## Pixel Comparison

Pixel comparison used a temporary Python analysis environment with `OpenImageIO 3.1.13.1` and `numpy 2.4.5`.

Summary:

```text
subimage_count:        22
total_values_compared: 62668800
different_values:      0
max_abs_diff:          0.0
mean_abs_diff:         0.0
rmse:                  0.0
all_pixels_identical:  true
```

Every subimage was identical:

| Subimage | Name | Shape | Different values | Max abs diff | RMSE |
| ---: | --- | --- | ---: | ---: | ---: |
| 0 | `C` | `1280x720x4` | 0 | 0.0 | 0.0 |
| 1 | `albedo` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 2 | `C_emission` | `1280x720x4` | 0 | 0.0 | 0.0 |
| 3 | `C_light_distant_1` | `1280x720x4` | 0 | 0.0 | 0.0 |
| 4 | `C_light_dome_1` | `1280x720x4` | 0 | 0.0 | 0.0 |
| 5 | `depth` | `1280x720x1` | 0 | 0.0 | 0.0 |
| 6 | `directdiffuse` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 7 | `directglossyreflection` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 8 | `directglossyreflection_emission` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 9 | `directglossyreflection_light_distant_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 10 | `directglossyreflection_light_dome_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 11 | `glossytransmission` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 12 | `glossytransmission_emission` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 13 | `glossytransmission_light_distant_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 14 | `glossytransmission_light_dome_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 15 | `indirectdiffuse` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 16 | `indirectglossyreflection` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 17 | `indirectglossyreflection_emission` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 18 | `indirectglossyreflection_light_distant_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 19 | `indirectglossyreflection_light_dome_1` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 20 | `N` | `1280x720x3` | 0 | 0.0 | 0.0 |
| 21 | `P` | `1280x720x3` | 0 | 0.0 | 0.0 |

## Conclusion

For this Canyon Run test frame, OptiX 9.0 did not improve or change denoising quality compared with OptiX 8.1. The output EXRs are byte-identical and pixel-identical.

Keep OptiX 9.0 as the default because it is still the newer validated runtime, but do not claim a denoising-quality improvement over 8.1 based on this test. The practical value of keeping 8.1 and 9.0 is compatibility coverage, not visibly better output on this sample.
