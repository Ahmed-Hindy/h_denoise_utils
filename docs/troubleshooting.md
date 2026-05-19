# Troubleshooting

## No bundled OptiX denoiser found

- Run `.\tools\fetch_optix_denoiser.ps1` from the repo root.
- Confirm `h_denoise_utils/vendor/optix-denoiser/windows-x64/optix-9.0/Denoiser.exe`
  exists.
- For development, set `HDU_DENOISER_EXE` to a specific OptiX `Denoiser.exe`.

## No bundled OIDN denoiser found

- Run `.\tools\fetch_oidn_denoiser.ps1` from the repo root, or use the
  `OIDN Denoiser` GitHub Actions workflow to build a fresh bundle.
- Confirm `h_denoise_utils/vendor/oidn-denoiser/windows-x64/oidn-2.4.1/Denoiser.exe`
  exists.
- For development, set `HDU_OIDN_DENOISER_EXE` to a specific custom OIDN
  `Denoiser.exe` or `HDU_OIDN_ROOT` to the wrapper bundle root.

## No EXR planes detected

- Confirm the input path points to an EXR file or folder with EXRs.
- Use a known-good EXR and verify `oiiotool` is available.

## AOV scan timeout

- Large folders can be slow. Try a single EXR file first.
- Increase the timeout in `ui/aov_scan_manager.py` if needed.

## OptiX vs OIDN mismatch

- OptiX requires NVIDIA hardware.
- If OptiX fails, switch to OIDN (CPU).

## Outputs are skipped

- If outputs already exist and "Replace Existing" is off, files are skipped.
- Enable "Replace Existing" or change the output prefix.

## UI starts but logs are empty

- The UI log handler only captures logs sent through `_log`.
- Ensure worker logs emit `log_message`.
