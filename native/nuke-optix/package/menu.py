"""Register the HOptixDenoise node in Nuke's Nodes menu."""

import nuke


nuke.menu("Nodes").addCommand(
    "Filter/HOptixDenoise",
    lambda: nuke.createNode("HOptixDenoise"),
)
