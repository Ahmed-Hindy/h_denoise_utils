# Common Tasks

## Add a UI control

1) Add the widget in `ui/sections.py` in the appropriate section builder.
2) Store it on `window` so `main_window.py` can access it.
3) Wire signals in `BaseWindow._connect_signals` in `ui/main_window.py`.
4) Update state in the relevant setter method (for example `_set_input_path_state`).
5) Add or update a small test if behavior changes.

## Add a new preset

1) Update `PRESETS` in `core/config.py`.
2) Confirm UI default logic in `ui/main_window.py` (`_apply_preset`).
3) Add or update a unit test in `tests/test_config.py` if needed.

## Add a new AOV detection rule

1) Update `ui/services/aov_inspector.py`.
2) Ensure `ui/aov_scan_manager.py` remains unchanged (thread wrapper only).
3) Add a unit test in `tests/test_aov_inspector.py`.

## Add a bundled denoiser option

1) Extend `DenoiseConfig` in `core/config.py`.
2) Update `core/command_builder.py` to pass the option.
3) Update `ui/main_window.py` to collect the UI value.
4) Add tests in `tests/test_command_builder.py`.

## Fetch bundled runtimes

Fetch OptiX:

```powershell
.\tools\fetch_optix_denoiser.ps1
```

Fetch the official OIDN SDK/runtime used to build the custom wrapper:

```powershell
.\tools\fetch_oidn.ps1
```

Fetch a released custom OIDN wrapper:

```powershell
.\tools\fetch_oidn_denoiser.ps1
```

The wrapper fetcher searches released app tags (`v*`) for the matching OIDN
wrapper asset. Use `-Tag vX.Y.Z` when you need a specific release.

## Build the bundled package

After both runtimes are present:

```powershell
.\tools\build_windows_package.ps1 -Variant bundled
```

The package smoke test validates both bundled runtime families.

## Run a headless smoke test

Use the scripting API directly:

```python
from h_denoise_utils.core.config import AOVConfig, DenoiseConfig
from h_denoise_utils.core.denoiser import Denoiser

denoiser = Denoiser(
    input_path="/path/to/images",
    denoise_config=DenoiseConfig(backend="optix"),
    aov_config=AOVConfig(),
)
prep = denoiser.prepare()
if prep["status"] == "ready":
    denoiser.denoise_one(0)
    denoiser.cleanup()
```

Use `DenoiseConfig(backend="oidn")` to run the custom OIDN wrapper once the
wrapper bundle is present. Validate both bundled runtimes with:

```powershell
uv run h-denoise --smoke-test --smoke-runtime all
```
