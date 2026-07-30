"""Build and control the h_denoise_utils Nuke playground."""

import os
import subprocess

import nuke

GENERATED_LABEL = "h_denoise_utils playground"


def _env(name, default=""):
    return os.environ.get(name, default)


def _node(name):
    return nuke.toNode(name)


def _set_xy(node, x, y):
    node.setXpos(x)
    node.setYpos(y)


def _get_or_create(node_class, name):
    node = _node(name)
    if node is None:
        node = nuke.createNode(node_class, inpanel=False)
        node.setName(name)
    return node


def _available_layers(read_node):
    layers = set()
    for channel in read_node.channels():
        if "." in channel:
            layers.add(channel.rsplit(".", 1)[0])
        else:
            layers.add("rgba")
    return sorted(layers)


def _resolve_layer(requested, layers, fallback):
    if requested in layers:
        return requested
    if fallback in layers:
        return fallback
    if layers:
        return layers[0]
    return requested


def _configure_read(name, path, x, y):
    node = _get_or_create("Read", name)
    node["file"].setValue(path.replace("\\", "/"))
    node["label"].setValue("[file tail [value file]]")
    _set_xy(node, x, y)
    return node


def _configure_shuffle(name, source, layer, x, y):
    node = _get_or_create("Shuffle", name)
    node.setInput(0, source)
    node["in"].setValue(layer)
    node["label"].setValue(f"{layer} -> rgba")
    _set_xy(node, x, y)
    return node


def _configure_optix(name, beauty, albedo, normal, x, y, tile_index=0):
    node = _get_or_create("HOptixDenoise", name)
    node.setInput(0, beauty)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["blend"].setValue(0.0)
    node["tile_size"].setValue(tile_index)
    node["gpu_device"].setValue(0)
    node["normal_encoding"].setValue(0)
    node["passthrough_on_error"].setValue(False)
    variant = name.replace("HDU_OPTIX_", "")
    node["label"].setValue(
        f"OptiX {_env('HDU_PLAYGROUND_OPTIX_VERSION', '?')}\n{variant}"
    )
    _set_xy(node, x, y)
    return node


def _configure_write(name, source, path, x, y):
    node = _get_or_create("Write", name)
    node.setInput(0, source)
    node["file"].setValue(path.replace("\\", "/"))
    node["file_type"].setValue("exr")
    node["channels"].setValue("rgba")
    node["label"].setValue("Render this node\n[file tail [value file]]")
    _set_xy(node, x, y)
    return node


def _add_text_knob(node, name, label, value):
    if name not in node.knobs():
        node.addKnob(nuke.Text_Knob(name, label, value))
    else:
        node[name].setValue(value)


def _configure_controls(switch_node, layers, x, y):
    node = _get_or_create("NoOp", "HDU_PLAYGROUND_CONTROLS")
    node["label"].setValue("PLAYGROUND CONTROLS\nOpen properties")
    node["tile_color"].setValue(0x3F6D8CFF)
    _set_xy(node, x, y)

    if "hdu_tab" not in node.knobs():
        node.addKnob(nuke.Tab_Knob("hdu_tab", "h_denoise_utils"))
    if "view" not in node.knobs():
        node.addKnob(
            nuke.Enumeration_Knob(
                "view",
                "viewer source",
                [
                    "Source beauty",
                    "OptiX beauty only",
                    "OptiX + albedo",
                    "OptiX + albedo + normal",
                    "OIDN + guides",
                    "OptiX vs OIDN difference x20",
                ],
            )
        )
        node["view"].setValue(3)
    if "refresh_oidn" not in node.knobs():
        knob = nuke.PyScript_Knob("refresh_oidn", "rerun OIDN and reload")
        knob.setCommand("import hdu_playground; hdu_playground.run_oidn()")
        node.addKnob(knob)
    if "reload_reads" not in node.knobs():
        knob = nuke.PyScript_Knob("reload_reads", "reload EXR reads")
        knob.setCommand("import hdu_playground; hdu_playground.reload_reads()")
        node.addKnob(knob)

    _add_text_knob(node, "input_path", "input", _env("HDU_PLAYGROUND_INPUT"))
    _add_text_knob(node, "oidn_path", "OIDN output", _env("HDU_PLAYGROUND_OIDN_OUTPUT"))
    oidn_runtime = os.path.basename(
        os.path.dirname(_env("HDU_PLAYGROUND_OIDN_EXE", "unknown"))
    )
    runtime_info = (
        f"Nuke {_env('HDU_PLAYGROUND_NUKE_VERSION', '?')} | "
        f"OptiX {_env('HDU_PLAYGROUND_OPTIX_VERSION', '?')} | "
        f"OIDN {oidn_runtime}"
    )
    _add_text_knob(node, "runtime_info", "runtime", runtime_info)
    _add_text_knob(node, "layers", "EXR layers", ", ".join(layers))
    _add_text_knob(
        node,
        "usage",
        "usage",
        "View the connected nodes directly, switch the Viewer source here, "
        "render the OptiX Write nodes, or rerun OIDN after changing layer "
        "names in the launcher.",
    )

    node["knobChanged"].setValue("import hdu_playground; hdu_playground.on_controls_changed()")
    switch_node["which"].setValue(int(node["view"].value()))
    return node


def _configure_backdrop(name, label, x, y, width, height, color):
    node = _get_or_create("BackdropNode", name)
    node["label"].setValue(label)
    node["bdwidth"].setValue(width)
    node["bdheight"].setValue(height)
    node["tile_color"].setValue(color)
    node["note_font_size"].setValue(26)
    _set_xy(node, x, y)
    return node


def configure():
    input_path = _env("HDU_PLAYGROUND_INPUT")
    oidn_output = _env("HDU_PLAYGROUND_OIDN_OUTPUT")
    output_dir = _env("HDU_PLAYGROUND_OUTPUT_DIR")
    if not input_path:
        nuke.message(
            "HDU_PLAYGROUND_INPUT is not set. Launch this script with "
            "launch-nuke-playground.ps1."
        )
        return

    source = _configure_read("HDU_SOURCE_MULTIPART", input_path, 0, 0)
    layers = _available_layers(source)
    beauty_layer = _resolve_layer(_env("HDU_PLAYGROUND_BEAUTY_LAYER", "C"), layers, "rgba")
    albedo_layer = _resolve_layer(
        _env("HDU_PLAYGROUND_ALBEDO_LAYER", "albedo"), layers, beauty_layer
    )
    normal_layer = _resolve_layer(
        _env("HDU_PLAYGROUND_NORMAL_LAYER", "N"), layers, beauty_layer
    )

    beauty = _configure_shuffle("HDU_BEAUTY", source, beauty_layer, 0, 130)
    albedo = _configure_shuffle("HDU_ALBEDO", source, albedo_layer, 180, 130)
    normal = _configure_shuffle("HDU_NORMAL", source, normal_layer, 360, 130)

    optix_beauty = _configure_optix("HDU_OPTIX_BEAUTY", beauty, None, None, -180, 340)
    optix_albedo = _configure_optix("HDU_OPTIX_ALBEDO", beauty, albedo, None, 40, 340)
    optix_guided = _configure_optix("HDU_OPTIX_GUIDED", beauty, albedo, normal, 280, 340)

    oidn_read = _configure_read("HDU_OIDN_MULTIPART", oidn_output, 560, 0)
    oidn_beauty = _configure_shuffle("HDU_OIDN_BEAUTY", oidn_read, beauty_layer, 560, 130)

    difference = _get_or_create("Merge2", "HDU_OPTIX_OIDN_DIFFERENCE")
    difference.setInput(0, optix_guided)
    difference.setInput(1, oidn_beauty)
    difference["operation"].setValue("difference")
    difference["label"].setValue("absolute difference")
    _set_xy(difference, 500, 340)

    difference_gain = _get_or_create("Multiply", "HDU_DIFFERENCE_X20")
    difference_gain.setInput(0, difference)
    for channel_index in range(4):
        difference_gain["value"].setValue(20.0, channel_index)
    difference_gain["label"].setValue("difference x20")
    _set_xy(difference_gain, 500, 440)

    switch_node = _get_or_create("Switch", "HDU_VIEW_SWITCH")
    for index, candidate in enumerate(
        [beauty, optix_beauty, optix_albedo, optix_guided, oidn_beauty, difference_gain]
    ):
        switch_node.setInput(index, candidate)
    switch_node["label"].setValue("Controlled by HDU_PLAYGROUND_CONTROLS")
    _set_xy(switch_node, 220, 600)

    viewer = _get_or_create("Viewer", "HDU_PLAYGROUND_VIEWER")
    viewer.setInput(0, switch_node)
    _set_xy(viewer, 220, 730)

    stem = os.path.splitext(os.path.basename(input_path))[0]
    optix_version = _env("HDU_PLAYGROUND_OPTIX_VERSION", "unknown")
    _configure_write(
        "HDU_WRITE_OPTIX_BEAUTY",
        optix_beauty,
        os.path.join(output_dir, stem + ".nuke-optix-" + optix_version + ".beauty.exr"),
        -180,
        520,
    )
    _configure_write(
        "HDU_WRITE_OPTIX_GUIDED",
        optix_guided,
        os.path.join(output_dir, stem + ".nuke-optix-" + optix_version + ".guided.exr"),
        280,
        520,
    )

    _configure_controls(switch_node, layers, 760, 120)
    _configure_backdrop(
        "HDU_BACKDROP_INPUTS",
        "SOURCE + GUIDE EXTRACTION",
        -60,
        -70,
        540,
        310,
        0x334455FF,
    )
    _configure_backdrop(
        "HDU_BACKDROP_OPTIX",
        "LIVE NATIVE OPTIX NODES",
        -250,
        270,
        720,
        430,
        0x355A42FF,
    )
    _configure_backdrop(
        "HDU_BACKDROP_OIDN",
        "OIDN CLI OUTPUT + COMPARISON",
        470,
        -70,
        300,
        610,
        0x5A4935FF,
    )

    root = nuke.root()
    if "label" in root.knobs():
        root["label"].setValue(GENERATED_LABEL)
    if hasattr(root, "setModified"):
        root.setModified(False)
    print("HDU playground configured")
    print("Input:", input_path)
    print("Layers:", ", ".join(layers))
    print("Beauty/albedo/normal:", beauty_layer, albedo_layer, normal_layer)


def on_controls_changed():
    knob = nuke.thisKnob()
    if knob is None or knob.name() != "view":
        return
    switch_node = _node("HDU_VIEW_SWITCH")
    if switch_node is not None:
        switch_node["which"].setValue(int(knob.value()))


def reload_reads():
    for name in ("HDU_SOURCE_MULTIPART", "HDU_OIDN_MULTIPART"):
        node = _node(name)
        if node is not None and "reload" in node.knobs():
            node["reload"].execute()


def run_oidn():
    executable = _env("HDU_PLAYGROUND_OIDN_EXE")
    input_path = _env("HDU_PLAYGROUND_INPUT")
    output_path = _env("HDU_PLAYGROUND_OIDN_OUTPUT")
    beauty = _env("HDU_PLAYGROUND_BEAUTY_LAYER", "C")
    albedo = _env("HDU_PLAYGROUND_ALBEDO_LAYER", "albedo")
    normal = _env("HDU_PLAYGROUND_NORMAL_LAYER", "N")
    if not executable or not os.path.isfile(executable):
        nuke.message("OIDN executable is missing. Relaunch with launch-nuke-playground.ps1.")
        return

    command = [
        executable,
        "-v",
        "1",
        "-multipart",
        input_path,
        "-o",
        output_path,
        "-beauty-name",
        beauty,
        "-albedo-name",
        albedo,
        "-normal-name",
        normal,
    ]
    result = subprocess.run(
        command,
        cwd=os.path.dirname(executable),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        nuke.message(
            f"OIDN failed with exit code {result.returncode}. See the Nuke console."
        )
        return
    reload_reads()
    nuke.message(f"OIDN output refreshed:\n{output_path}")


def validate_playground():
    script_path = _env("HDU_PLAYGROUND_NK")
    nuke.scriptOpen(script_path)
    configure()
    required = [
        "HDU_SOURCE_MULTIPART",
        "HDU_BEAUTY",
        "HDU_ALBEDO",
        "HDU_NORMAL",
        "HDU_OPTIX_BEAUTY",
        "HDU_OPTIX_ALBEDO",
        "HDU_OPTIX_GUIDED",
        "HDU_OIDN_MULTIPART",
        "HDU_OIDN_BEAUTY",
        "HDU_OPTIX_OIDN_DIFFERENCE",
        "HDU_PLAYGROUND_CONTROLS",
        "HDU_PLAYGROUND_VIEWER",
    ]
    missing = [name for name in required if _node(name) is None]
    if missing:
        raise RuntimeError(f"Playground nodes are missing: {', '.join(missing)}")
    print(f"HDU Nuke playground validation passed: {len(nuke.allNodes())} nodes")


if __name__ == "__main__":
    validate_playground()
