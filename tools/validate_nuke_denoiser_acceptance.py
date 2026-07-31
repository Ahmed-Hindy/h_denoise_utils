"""Run a reusable acceptance pass for the native Nuke denoiser nodes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nuke

EXPECTED = {
    "HOptixDenoise": {
        "blend": 0.0,
        "gpu_device": 0,
        "normal_encoding": "Signed (-1 to 1)",
        "passthrough_on_error": True,
    },
    "HOidnDenoise": {
        "blend": 0.0,
        "gpu_device": 0,
        "quality": "High",
        "hdr": True,
        "clean_aux": True,
        "normal_encoding": "Signed (-1 to 1)",
        "passthrough_on_error": True,
    },
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _knob_value(node: nuke.Node, knob_name: str):
    knob = node[knob_name]
    if knob.Class() == "Enumeration_Knob":
        return knob.value()
    return knob.value()


def _make_constant(name: str, color: list[float], format_name: str) -> nuke.Node:
    node = nuke.nodes.Constant(name=name)
    node["color"].setValue(color)
    node["format"].setValue(format_name)
    return node


def _validate_contract(class_name: str, node: nuke.Node) -> None:
    _require(node.maximumInputs() == 3, f"{class_name} must expose three inputs")
    for knob_name, expected in EXPECTED[class_name].items():
        _require(knob_name in node.knobs(), f"{class_name} is missing {knob_name}")
        actual = _knob_value(node, knob_name)
        _require(actual == expected, f"{class_name}.{knob_name}: {actual!r} != {expected!r}")
        _require(bool(node[knob_name].tooltip()), f"{class_name}.{knob_name} has no tooltip")


def _render(node: nuke.Node, path: Path) -> None:
    writer = nuke.nodes.Write(name=f"WRITE_{node.name()}")
    writer.setInput(0, node)
    writer["file_type"].setValue("exr")
    writer["channels"].setValue("rgba")
    writer["file"].setValue(path.as_posix())
    path.unlink(missing_ok=True)
    nuke.execute(writer, 1, 1)
    _require(path.is_file() and path.stat().st_size > 0, f"Missing output: {path}")


def main() -> None:
    format_name = nuke.addFormat("64 32 1.0 HDenoiseAcceptance").name()
    beauty = _make_constant("ACCEPT_BEAUTY", [0.22, 0.48, 0.73, 0.65], format_name)
    albedo = _make_constant("ACCEPT_ALBEDO", [0.45, 0.52, 0.61, 1.0], format_name)
    normal = _make_constant("ACCEPT_NORMAL", [0.5, 0.5, 1.0, 1.0], format_name)

    nodes: list[nuke.Node] = []
    for class_name in EXPECTED:
        node = nuke.createNode(class_name, inpanel=False)
        node.setName(f"ACCEPT_{class_name}")
        node.setInput(0, beauty)
        node.setInput(1, albedo)
        node.setInput(2, normal)
        _validate_contract(class_name, node)
        nodes.append(node)

    nodes[0]["blend"].setValue(0.17)
    nodes[0]["tile_size"].setValue(1)
    nodes[1]["blend"].setValue(0.23)
    nodes[1]["quality"].setValue("Balanced")
    nodes[1]["clean_aux"].setValue(False)

    temp_root = Path(tempfile.gettempdir()) / "hdu-nuke-acceptance"
    temp_root.mkdir(parents=True, exist_ok=True)
    script_path = temp_root / "acceptance-roundtrip.nk"
    outputs = [temp_root / f"{node.Class()}.exr" for node in nodes]

    nuke.scriptSaveAs(script_path.as_posix(), overwrite=1)
    nuke.scriptClear()
    nuke.scriptOpen(script_path.as_posix())

    optix = nuke.toNode("ACCEPT_HOptixDenoise")
    oidn = nuke.toNode("ACCEPT_HOidnDenoise")
    _require(optix is not None and oidn is not None, "Nodes did not survive save/reopen")
    _require(abs(optix["blend"].value() - 0.17) < 1e-6, "OptiX blend did not serialize")
    _require(
        optix["tile_size"].value() == "512 x 512",
        f"OptiX tile size did not serialize: {optix['tile_size'].value()!r}",
    )
    _require(abs(oidn["blend"].value() - 0.23) < 1e-6, "OIDN blend did not serialize")
    _require(oidn["quality"].value() == "Balanced", "OIDN quality did not serialize")
    _require(not oidn["clean_aux"].value(), "OIDN clean_aux did not serialize")
    for node in (optix, oidn):
        _require(
            all(node.input(index) is not None for index in range(3)),
            f"{node.Class()} inputs did not serialize",
        )

    _render(optix, outputs[0])
    _render(oidn, outputs[1])

    oidn["gpu_device"].setValue(999)
    oidn["passthrough_on_error"].setValue(True)
    passthrough = temp_root / "HOidnDenoise-passthrough.exr"
    _render(oidn, passthrough)

    leftovers = list(temp_root.glob("hdu-oidn-*"))
    _require(not leftovers, f"OIDN temporary files remain: {leftovers}")

    print("Nuke denoiser acceptance passed")
    print(f"Nuke: {nuke.NUKE_VERSION_STRING}")
    print(f"Package: {os.environ.get('NUKE_PATH', '')}")
    print(f"Round-trip script: {script_path}")


if __name__ == "__main__":
    main()
