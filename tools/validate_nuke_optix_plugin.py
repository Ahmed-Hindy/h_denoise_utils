"""Load and render through the native h_denoise_utils Nuke nodes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nuke


def _require_node_interface(
    node: nuke.Node,
    class_name: str,
    expected_knobs: set[str],
) -> None:
    """Validate a native denoiser node's public Nuke interface."""
    missing_knobs = expected_knobs.difference(node.knobs())
    if missing_knobs:
        raise RuntimeError(f"{class_name} is missing knobs: {sorted(missing_knobs)}")
    if node.maximumInputs() != 3:
        raise RuntimeError(
            f"{class_name} exposes {node.maximumInputs()} inputs instead of 3"
        )


def _constant(color: list[float], format_name: str) -> nuke.Node:
    node = nuke.nodes.Constant()
    node["color"].setValue(color)
    node["format"].setValue(format_name)
    return node


def _render_and_require_output(writer: nuke.Node, output_path: Path) -> None:
    output_path.unlink(missing_ok=True)
    writer["file"].setValue(output_path.as_posix())
    nuke.execute(writer, 1, 1)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Nuke did not create a valid output: {output_path}")


def _validate_optix(
    source: nuke.Node,
    albedo: nuke.Node,
    normal: nuke.Node,
    test_format: nuke.Format,
) -> list[Path]:
    node = nuke.createNode("HOptixDenoise", inpanel=False)
    _require_node_interface(
        node,
        "HOptixDenoise",
        {
            "blend",
            "tile_size",
            "gpu_device",
            "normal_encoding",
            "passthrough_on_error",
        },
    )
    node.setInput(0, source)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["normal_encoding"].setValue(1)

    writer = nuke.nodes.Write()
    writer.setInput(0, node)
    writer["file_type"].setValue("exr")
    writer["channels"].setValue("rgba")

    resized_format = nuke.addFormat("520 8 1.0 HOptixDenoiseTiledTest")
    output_paths = [
        Path(tempfile.gettempdir()) / f"hdu-nuke-optix-validation-{index}.exr"
        for index in range(4)
    ]
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
        _render_and_require_output(writer, output_path)

    print(
        "HOptixDenoise repeated-session validation passed: "
        f"{len(output_paths)} renders"
    )
    return output_paths


def _validate_oidn(
    source: nuke.Node,
    albedo: nuke.Node,
    normal: nuke.Node,
    test_format: nuke.Format,
) -> list[Path]:
    node = nuke.createNode("HOidnDenoise", inpanel=False)
    _require_node_interface(
        node,
        "HOidnDenoise",
        {
            "blend",
            "gpu_device",
            "quality",
            "hdr",
            "clean_aux",
            "normal_encoding",
            "passthrough_on_error",
        },
    )
    node.setInput(0, source)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["normal_encoding"].setValue(1)
    node["gpu_device"].setValue(0)
    node["quality"].setValue("Balanced")
    node["passthrough_on_error"].setValue(False)

    for constant in (source, albedo, normal):
        constant["format"].setValue(test_format.name())
    source["color"].setValue([0.42, 0.31, 0.67, 1.0])

    writer = nuke.nodes.Write()
    writer.setInput(0, node)
    writer["file_type"].setValue("exr")
    writer["channels"].setValue("rgba")
    output_path = Path(tempfile.gettempdir()) / "hdu-nuke-oidn-validation.exr"
    _render_and_require_output(writer, output_path)
    print("HOidnDenoise validation passed: 1 render")
    return [output_path]


def main() -> None:
    """Validate the native node interfaces and render paths."""
    test_format = nuke.addFormat("16 16 1.0 HDenoiseNodeTest")
    source = _constant([0.25, 0.5, 0.75, 1.0], test_format.name())
    albedo = _constant([0.5, 0.5, 0.5, 1.0], test_format.name())
    normal = _constant([0.5, 0.5, 1.0, 1.0], test_format.name())

    output_paths: list[Path] = []
    try:
        output_paths.extend(_validate_optix(source, albedo, normal, test_format))
        if os.environ.get("HDU_NUKE_VALIDATE_OIDN") == "1":
            output_paths.extend(_validate_oidn(source, albedo, normal, test_format))
    finally:
        for output_path in output_paths:
            output_path.unlink(missing_ok=True)
        nuke.scriptClear(ignoreUnsavedChanges=True)


if __name__ == "__main__":
    os.environ.setdefault("NUKE_INTERACTIVE", "0")
    main()
