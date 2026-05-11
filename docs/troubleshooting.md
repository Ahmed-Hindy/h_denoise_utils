# Troubleshooting

## No idenoise executable found

- Verify Houdini is installed and `idenoise` exists in the Houdini `bin`.
- In the UI, use the custom EXE picker to point at `idenoise.exe`.

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
