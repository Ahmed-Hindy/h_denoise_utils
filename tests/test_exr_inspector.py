"""Tests for pure Python EXR inspection."""

import struct

from h_denoise_utils.discovery.exr_inspector import list_exr_planes


def _attr(name, attr_type, value):
    return (
        name.encode("utf-8")
        + b"\0"
        + attr_type.encode("utf-8")
        + b"\0"
        + struct.pack("<I", len(value))
        + value
    )


def _string_attr(name, value):
    return _attr(name, "string", value.encode("utf-8"))


def _channels_attr(names):
    value = bytearray()
    for name in names:
        value.extend(name.encode("utf-8") + b"\0")
        value.extend(struct.pack("<iB3xii", 1, 0, 1, 1))
    value.extend(b"\0")
    return _attr("channels", "chlist", bytes(value))


def _singlepart_exr(attrs):
    return bytes.fromhex("762f3101") + struct.pack("<I", 2) + b"".join(attrs) + b"\0"


def _multipart_exr(parts):
    payload = bytes.fromhex("762f3101") + struct.pack("<I", 2 | 0x1000)
    for attrs in parts:
        payload += b"".join(attrs) + b"\0"
    payload += b"\0"
    return payload


def test_multipart_part_names(tmp_path):
    path = tmp_path / "multipart.exr"
    path.write_bytes(
        _multipart_exr(
            [
                [_string_attr("name", "C"), _channels_attr(["R", "G", "B", "A"])],
                [
                    _string_attr("name", "directdiffuse"),
                    _channels_attr(["directdiffuse.R", "directdiffuse.G", "directdiffuse.B"]),
                ],
            ]
        )
    )

    assert list_exr_planes(str(path)) == ["C", "directdiffuse"]


def test_layered_channel_names(tmp_path):
    path = tmp_path / "layered.exr"
    path.write_bytes(
        _singlepart_exr(
            [
                _channels_attr(
                    [
                        "diffuse.R",
                        "diffuse.G",
                        "diffuse.B",
                        "specular.R",
                        "specular.G",
                        "specular.B",
                    ]
                )
            ]
        )
    )

    assert list_exr_planes(str(path)) == ["diffuse", "specular"]
