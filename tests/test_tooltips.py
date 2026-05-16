"""Unit tests for tooltip string helpers."""

from h_denoise_utils.ui import tooltips


def test_planes_toggle_formats_count_and_timestamp():
    text = tooltips.planes_toggle(3, "2026-05-16 12:00:00")
    assert text == "Count: 3 | Last scan: 2026-05-16 12:00:00"


def test_temporal_backend_unsupported_includes_backend_name():
    text = tooltips.temporal_backend_unsupported("Oidn (CPU)")
    assert text == "Temporal denoising not supported by Oidn (CPU)"


def test_options_invalid_json_includes_error():
    text = tooltips.options_invalid_json("Expecting value")
    assert text == "Invalid JSON: Expecting value"


def test_output_destination_label_with_path():
    text = tooltips.output_destination_label("/tmp/out")
    assert text == "Destination: /tmp/out"


def test_output_destination_label_empty():
    assert tooltips.output_destination_label("") == tooltips.OUTPUT_DESTINATION_EMPTY


def test_action_destination_label_with_path():
    assert tooltips.action_destination_label("/tmp/out") == "→ /tmp/out"


def test_action_destination_label_empty():
    assert tooltips.action_destination_label("") == "→ -"
