"""Load and render through HOptixDenoise inside Nuke.

This validation is intended for the compile-check stub build as well as the
production OptiX build. The stub copies the beauty input unchanged, while the
production build performs real GPU denoising.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nuke


def main() -> None:
    """Create the node, validate its interface, and render a small EXR."""
    node = nuke.createNode("HOptixDenoise", inpanel=False)
    expected_knobs = {
        "blend",
        "tile_size",
        "gpu_device",
        "normal_encoding",
        "passthrough_on_error",
    }
    missing_knobs = expected_knobs.difference(node.knobs())
    if missing_knobs:
        raise RuntimeError(f"HOptixDenoise is missing knobs: {sorted(missing_knobs)}")
    if node.maximumInputs() != 3:
        raise RuntimeError(
            f"HOptixDenoise exposes {node.maximumInputs()} inputs instead of 3"
        )

    source = nuke.nodes.Constant()
    source["color"].setValue([0.25, 0.5, 0.75, 1.0])
    test_format = nuke.addFormat("16 16 1.0 HOptixDenoiseTest")
    source["format"].setValue(test_format.name())
    albedo = nuke.nodes.Constant()
    albedo["color"].setValue([0.5, 0.5, 0.5, 1.0])
    albedo["format"].setValue(test_format.name())

    normal = nuke.nodes.Constant()
    normal["color"].setValue([0.5, 0.5, 1.0, 1.0])
    normal["format"].setValue(test_format.name())

    node.setInput(0, source)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["normal_encoding"].setValue(1)

    resized_format = nuke.addFormat("24 12 1.0 HOptixDenoiseResizedTest")
    output_paths = [
        Path(tempfile.gettempdir()) / f"hdu-nuke-optix-validation-{index}.exr"
        for index in range(4)
    ]
    for output_path in output_paths:
        output_path.unlink(missing_ok=True)

    writer = nuke.nodes.Write()
    writer.setInput(0, node)
    writer["file_type"].setValue("exr")
    writer["channels"].setValue("rgba")

    try:
        render_cases = (
            (output_paths[0], [0.25, 0.5, 0.75, 1.0], 2, test_format),
            (output_paths[1], [0.35, 0.45, 0.65, 1.0], 2, test_format),
            (output_paths[2], [0.45, 0.35, 0.55, 1.0], 1, test_format),
            (output_paths[3], [0.55, 0.25, 0.45, 1.0], 1, resized_format),
        )
        for output_path, color, tile_size, render_format in render_cases:
            source["color"].setValue(color)
            for constant in (source, albedo, normal):
                constant["format"].setValue(render_format.name())
            node["tile_size"].setValue(tile_size)
            writer["file"].setValue(output_path.as_posix())
            nuke.execute(writer, 1, 1)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise RuntimeError(
                    f"Nuke did not create a valid output: {output_path}"
                )
        print(
            "HOptixDenoise repeated-session validation passed: "
            f"{len(output_paths)} renders"
        )
    finally:
        for output_path in output_paths:
            output_path.unlink(missing_ok=True)
        nuke.scriptClear(ignoreUnsavedChanges=True)


if __name__ == "__main__":
    os.environ.setdefault("NUKE_INTERACTIVE", "0")
    main()
