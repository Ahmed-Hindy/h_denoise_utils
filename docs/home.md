# h_denoise_utils Documentation

Welcome to the h_denoise_utils documentation.

**h_denoise_utils** is a modular Python package for denoising images using
Houdini's `idenoise` utility with Intel OIDN or NVIDIA OptiX backends.

## Features

- Multiple backends (Intel OIDN CPU / NVIDIA OptiX GPU)
- Temporal denoising for animation sequences
- AOV support with auto-detection
- Full-featured Qt GUI and headless API
- Python 3.7+ compatible
- Comprehensive test coverage

## Read This First

- [Getting Started](getting-started.md)
- [Architecture Guide](architecture.md)
- [Codebase Tour](codebase-tour.md)
- [Common Tasks](common-tasks.md)

## Quick Start

### GUI Usage

```python
import h_denoise_utils
h_denoise_utils.show_ui()
```

### Headless Usage

```python
from h_denoise_utils.core.denoiser import Denoiser
from h_denoise_utils.core.config import DenoiseConfig, AOVConfig

denoise_config = DenoiseConfig(backend="optix", temporal=True)
aov_config = AOVConfig(normal_plane="N", albedo_plane="albedo")

denoiser = Denoiser("/path/to/images", denoise_config, aov_config)
denoiser.prepare()
for i in range(len(denoiser.files)):
    result = denoiser.denoise_one(i)
denoiser.cleanup()
```

## Contents

- [Getting Started](getting-started.md)
- [Architecture Guide](architecture.md)
- [Codebase Tour](codebase-tour.md)
- [Common Tasks](common-tasks.md)
- [Troubleshooting](troubleshooting.md)
- [Glossary](glossary.md)
- [API Reference](modules.md)

