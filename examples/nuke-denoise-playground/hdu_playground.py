"""Build and validate the live OptiX and OIDN Nuke playground."""

import os

import nuke

GENERATED_LABEL = "h_denoise_utils live denoise playground"


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
        layers.add(channel.rsplit(".", 1)[0] if "." in channel else "rgba")
    return sorted(layers)


def _resolve_layer(requested, layers, fallback):
    if requested in layers:
        return requested
    if fallback in layers:
        return fallback
    return layers[0] if layers else requested


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


def _configure_optix(name, beauty, albedo, normal, x, y):
    node = _get_or_create("HOptixDenoise", name)
    node.setInput(0, beauty)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["blend"].setValue(0.0)
    node["tile_size"].setValue(0)
    node["gpu_device"].setValue(0)
    node["normal_encoding"].setValue(0)
    node["passthrough_on_error"].setValue(False)
    variant = name.replace("HDU_OPTIX_", "")
    node["label"].setValue(
        f"OptiX {_env('HDU_PLAYGROUND_OPTIX_VERSION', '?')}\n{variant}"
    )
    _set_xy(node, x, y)
    return node


def _configure_oidn(name, beauty, albedo, normal, x, y):
    node = _get_or_create("HOidnDenoise", name)
    node.setInput(0, beauty)
    node.setInput(1, albedo)
    node.setInput(2, normal)
    node["blend"].setValue(0.0)
    node["gpu_device"].setValue(0)
    node["quality"].setValue("High")
    node["hdr"].setValue(True)
    node["clean_aux"].setValue(True)
    node["normal_encoding"].setValue(0)
    node["passthrough_on_error"].setValue(False)
    variant = name.replace("HDU_OIDN_", "")
    node["label"].setValue(
        f"OIDN {_env('HDU_PLAYGROUND_OIDN_VERSION', '?')} CUDA\n{variant}"
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


def _enumeration_index(knob):
    try:
        return int(knob.getValue())
    except (AttributeError, TypeError, ValueError):
        values = list(knob.values()) if hasattr(knob, "values") else []
        value = knob.value()
        return values.index(value) if value in values else 0


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
                    "OptiX + albedo + normal",
                    "OIDN beauty only",
                    "OIDN + albedo + normal",
                    "OptiX vs OIDN difference x20",
                ],
            )
        )
        node["view"].setValue(4)
    if "reload_source" not in node.knobs():
        knob = nuke.PyScript_Knob("reload_source", "reload source EXR")
        knob.setCommand("import hdu_playground; hdu_playground.reload_source()")
        node.addKnob(knob)

    _add_text_knob(node, "input_path", "input", _env("HDU_PLAYGROUND_INPUT"))
    runtime_info = (
        f"Nuke {_env('HDU_PLAYGROUND_NUKE_VERSION', '?')} | "
        f"OptiX {_env('HDU_PLAYGROUND_OPTIX_VERSION', '?')} | "
        f"OIDN {_env('HDU_PLAYGROUND_OIDN_VERSION', '?')} CUDA"
    )
    _add_text_knob(node, "runtime_info", "runtime", runtime_info)
    _add_text_knob(node, "layers", "EXR layers", ", ".join(layers))
    _add_text_knob(
        node,
        "usage",
        "usage",
        "Inspect the live OptiX and OIDN nodes, switch the Viewer source here, "
        "or render the Write nodes to compare final EXRs.",
    )

    node["knobChanged"].setValue(
        "import hdu_playground; hdu_playground.on_controls_changed()"
    )
    switch_node["which"].setValue(_enumeration_index(node["view"]))
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
    output_dir = _env("HDU_PLAYGROUND_OUTPUT_DIR")
    if not input_path or not output_dir:
        nuke.message(
            "HDU_PLAYGROUND_INPUT / HDU_PLAYGROUND_OUTPUT_DIR are not set. "
            "Launch this script with launch-nuke-playground.ps1."
        )
        return

    source = _configure_read("HDU_SOURCE_MULTIPART", input_path, 0, 0)
    layers = _available_layers(source)
    beauty_layer = _resolve_layer(
        _env("HDU_PLAYGROUND_BEAUTY_LAYER", "C"), layers, "rgba"
    )
    albedo_layer = _resolve_layer(
        _env("HDU_PLAYGROUND_ALBEDO_LAYER", "albedo"), layers, beauty_layer
    )
    normal_layer = _resolve_layer(
        _env("HDU_PLAYGROUND_NORMAL_LAYER", "N"), layers, beauty_layer
    )

    beauty = _configure_shuffle("HDU_BEAUTY", source, beauty_layer, 0, 130)
    albedo = _configure_shuffle("HDU_ALBEDO", source, albedo_layer, 180, 130)
    normal = _configure_shuffle("HDU_NORMAL", source, normal_layer, 360, 130)

    optix_beauty = _configure_optix(
        "HDU_OPTIX_BEAUTY", beauty, None, None, -260, 340
    )
    optix_guided = _configure_optix(
        "HDU_OPTIX_GUIDED", beauty, albedo, normal, -20, 340
    )
    oidn_beauty = _configure_oidn(
        "HDU_OIDN_BEAUTY", beauty, None, None, 300, 340
    )
    oidn_guided = _configure_oidn(
        "HDU_OIDN_GUIDED", beauty, albedo, normal, 540, 340
    )

    difference = _get_or_create("Merge2", "HDU_OPTIX_OIDN_DIFFERENCE")
    difference.setInput(0, optix_guided)
    difference.setInput(1, oidn_guided)
    difference["operation"].setValue("difference")
    difference["label"].setValue("absolute difference")
    _set_xy(difference, 780, 340)

    difference_gain = _get_or_create("Multiply", "HDU_DIFFERENCE_X20")
    difference_gain.setInput(0, difference)
    for channel_index in range(4):
        difference_gain["value"].setValue(20.0, channel_index)
    difference_gain["label"].setValue("difference x20")
    _set_xy(difference_gain, 780, 440)

    switch_node = _get_or_create("Switch", "HDU_VIEW_SWITCH")
    candidates = [
        beauty,
        optix_beauty,
        optix_guided,
        oidn_beauty,
        oidn_guided,
        difference_gain,
    ]
    for index, candidate in enumerate(candidates):
        switch_node.setInput(index, candidate)
    switch_node["label"].setValue("Controlled by HDU_PLAYGROUND_CONTROLS")
    _set_xy(switch_node, 250, 700)

    viewer = _get_or_create("Viewer", "HDU_PLAYGROUND_VIEWER")
    viewer.setInput(0, switch_node)
    _set_xy(viewer, 250, 820)

    stem = os.path.splitext(os.path.basename(input_path))[0]
    optix_version = _env("HDU_PLAYGROUND_OPTIX_VERSION", "unknown")
    oidn_version = _env("HDU_PLAYGROUND_OIDN_VERSION", "unknown")
    writes = (
        (
            "HDU_WRITE_OPTIX_BEAUTY",
            optix_beauty,
            f"{stem}.nuke-optix-{optix_version}.beauty.exr",
            -260,
        ),
        (
            "HDU_WRITE_OPTIX_GUIDED",
            optix_guided,
            f"{stem}.nuke-optix-{optix_version}.guided.exr",
            -20,
        ),
        (
            "HDU_WRITE_OIDN_BEAUTY",
            oidn_beauty,
            f"{stem}.nuke-oidn-{oidn_version}.beauty.exr",
            300,
        ),
        (
            "HDU_WRITE_OIDN_GUIDED",
            oidn_guided,
            f"{stem}.nuke-oidn-{oidn_version}.guided.exr",
            540,
        ),
        (
            "HDU_WRITE_OPTIX_OIDN_DIFFERENCE",
            difference_gain,
            f"{stem}.optix-vs-oidn-difference-x20.exr",
            780,
        ),
    )
    for name, input_node, filename, xpos in writes:
        _configure_write(
            name,
            input_node,
            os.path.join(output_dir, filename),
            xpos,
            560,
        )

    _configure_controls(switch_node, layers, 1030, 120)
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
        "LIVE NATIVE OPTIX",
        -330,
        270,
        560,
        440,
        0x355A42FF,
    )
    _configure_backdrop(
        "HDU_BACKDROP_OIDN",
        "LIVE OIDN CUDA NODE",
        250,
        270,
        560,
        440,
        0x5A4935FF,
    )
    _configure_backdrop(
        "HDU_BACKDROP_COMPARE",
        "LIVE COMPARISON",
        730,
        270,
        300,
        440,
        0x5A354FFF,
    )

    root = nuke.root()
    if "label" in root.knobs():
        root["label"].setValue(GENERATED_LABEL)
    if hasattr(root, "setModified"):
        root.setModified(False)
    print("HDU live denoise playground configured")
    print("Input:", input_path)
    print("Layers:", ", ".join(layers))
    print("Beauty/albedo/normal:", beauty_layer, albedo_layer, normal_layer)


def on_controls_changed():
    knob = nuke.thisKnob()
    if knob is None or knob.name() != "view":
        return
    switch_node = _node("HDU_VIEW_SWITCH")
    if switch_node is not None:
        switch_node["which"].setValue(_enumeration_index(knob))


def reload_source():
    node = _node("HDU_SOURCE_MULTIPART")
    if node is not None and "reload" in node.knobs():
        node["reload"].execute()


def _validate_write_output(node_name, expected_width, expected_height):
    node = _node(node_name)
    if node is None:
        raise RuntimeError(f"Playground write node is missing: {node_name}")

    output_path = node["file"].evaluate()
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)

    nuke.execute(node, 1, 1)
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Nuke did not create a valid output: {output_path}")

    probe = nuke.nodes.Read(file=output_path.replace("\\", "/"))
    try:
        if probe.width() != expected_width or probe.height() != expected_height:
            raise RuntimeError(
                f"Output dimensions changed for {node_name}: "
                f"{probe.width()}x{probe.height()} instead of "
                f"{expected_width}x{expected_height}"
            )
        required_channels = {"rgba.red", "rgba.green", "rgba.blue"}
        if not required_channels.issubset(set(probe.channels())):
            raise RuntimeError(f"Output is missing RGB channels: {output_path}")
    finally:
        nuke.delete(probe)
    print(f"Validated {node_name}: {output_path}")


def validate_playground():
    script_path = _env("HDU_PLAYGROUND_NK")
    nuke.scriptOpen(script_path)
    required = [
        "HDU_SOURCE_MULTIPART",
        "HDU_BEAUTY",
        "HDU_ALBEDO",
        "HDU_NORMAL",
        "HDU_OPTIX_BEAUTY",
        "HDU_OPTIX_GUIDED",
        "HDU_OIDN_BEAUTY",
        "HDU_OIDN_GUIDED",
        "HDU_OPTIX_OIDN_DIFFERENCE",
        "HDU_WRITE_OPTIX_BEAUTY",
        "HDU_WRITE_OPTIX_GUIDED",
        "HDU_WRITE_OIDN_BEAUTY",
        "HDU_WRITE_OIDN_GUIDED",
        "HDU_WRITE_OPTIX_OIDN_DIFFERENCE",
        "HDU_PLAYGROUND_CONTROLS",
        "HDU_PLAYGROUND_VIEWER",
    ]
    if any(_node(name) is None for name in required):
        configure()
    missing = [name for name in required if _node(name) is None]
    if missing:
        raise RuntimeError(f"Playground nodes are missing: {', '.join(missing)}")

    source = _node("HDU_SOURCE_MULTIPART")
    for node_name in (
        "HDU_WRITE_OPTIX_GUIDED",
        "HDU_WRITE_OIDN_GUIDED",
        "HDU_WRITE_OPTIX_OIDN_DIFFERENCE",
    ):
        _validate_write_output(node_name, source.width(), source.height())
    print(f"HDU Nuke playground validation passed: {len(nuke.allNodes())} nodes")


if __name__ == "__main__":
    validate_playground()
