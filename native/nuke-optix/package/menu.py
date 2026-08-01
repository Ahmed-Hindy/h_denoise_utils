"""Register the h_denoise_utils nodes in Nuke's Filter menu."""

import nuke

nodes_menu = nuke.menu("Nodes")
nodes_menu.addCommand(
    "Filter/HOptixDenoise",
    lambda: nuke.createNode("HOptixDenoise"),
)
nodes_menu.addCommand(
    "Filter/HOidnDenoise",
    lambda: nuke.createNode("HOidnDenoise"),
)
