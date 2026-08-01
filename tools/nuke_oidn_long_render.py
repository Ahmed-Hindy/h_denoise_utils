"""Long OIDN render used by the external cancellation validator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import nuke

FORMAT_NAME = nuke.addFormat("5120 2880 1.0 HOidnCancelAcceptance").name()


def _constant(color: list[float]) -> nuke.Node:
    node = nuke.nodes.Constant()
    node["format"].setValue(FORMAT_NAME)
    node["color"].setValue(color)
    return node


beauty = _constant([0.25, 0.5, 0.75, 1.0])
albedo = _constant([0.5, 0.5, 0.5, 1.0])
normal = _constant([0.0, 0.0, 1.0, 1.0])
node = nuke.createNode("HOidnDenoise", inpanel=False)
node.setInput(0, beauty)
node.setInput(1, albedo)
node.setInput(2, normal)
node["quality"].setValue("High")
node["passthrough_on_error"].setValue(False)
writer = nuke.nodes.Write()
writer.setInput(0, node)
writer["file_type"].setValue("exr")
writer["channels"].setValue("rgba")
writer["file"].setValue(
    (Path(tempfile.gettempdir()) / "hdu-oidn-cancel-acceptance.exr").as_posix()
)
nuke.execute(writer, 1, 1)
