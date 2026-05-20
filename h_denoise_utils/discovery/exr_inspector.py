"""Pure Python EXR file inspection."""

from __future__ import annotations

import logging
import os
import struct

logger = logging.getLogger(__name__)

OPENEXR_MAGIC = bytes.fromhex("762f3101")
OPENEXR_MULTIPART_FLAG = 0x1000
OPENEXR_UINT_BYTE_COUNT = 4
OPENEXR_CHANNEL_ENTRY_METADATA_BYTES = 16


def _read_cstring(stream, first_byte=b""):
    """Read a null-terminated C-string from a binary stream.

    Args:
        stream: The file-like binary stream.
        first_byte: Optional initial byte to prepend to the result.

    Returns:
        bytes: The read bytes, excluding the null terminator.

    Raises:
        EOFError: If EOF is reached before a null terminator.
    """
    data = bytearray(first_byte)
    while True:
        b = stream.read(1)
        if not b:
            raise EOFError("unexpected EOF while reading EXR header")
        if b == b"\0":
            return bytes(data)
        data.extend(b)


def _read_header(stream, first_name_byte=b""):
    """Read a single EXR header part/attribute block from the stream.

    Args:
        stream: The file-like binary stream.
        first_name_byte: Optional initial byte of the first attribute name.

    Returns:
        Tuple[Dict[str, Tuple[str, bytes]], List[str]]: A tuple containing:
            - A dictionary mapping attribute names to their type and raw bytes.
            - A list of attribute names in their original order.

    Raises:
        EOFError: If EOF is reached while reading sizes or values.
    """
    attrs: dict[str, tuple[str, bytes]] = {}
    order: list[str] = []
    while True:
        name = _read_cstring(stream, first_name_byte)
        first_name_byte = b""
        if not name:
            break
        attr_type = _read_cstring(stream)
        size_data = stream.read(OPENEXR_UINT_BYTE_COUNT)
        if len(size_data) != OPENEXR_UINT_BYTE_COUNT:
            raise EOFError("unexpected EOF while reading EXR attribute size")
        size = struct.unpack("<I", size_data)[0]
        value = stream.read(size)
        if len(value) != size:
            raise EOFError("unexpected EOF while reading EXR attribute value")
        key = name.decode("utf-8", "replace")
        attrs[key] = (attr_type.decode("utf-8", "replace"), value)
        order.append(key)
    return attrs, order


def _read_headers(path):
    """Read all headers from an EXR file (supporting multipart files).

    Args:
        path: Path to the EXR file.

    Returns:
        List[Tuple[Dict[str, Tuple[str, bytes]], List[str]]]: A list of headers,
            where each header is a tuple of (attributes, order).
    """
    headers = []
    with open(path, "rb") as stream:
        magic = stream.read(OPENEXR_UINT_BYTE_COUNT)
        if magic != OPENEXR_MAGIC:
            return []
        version_data = stream.read(OPENEXR_UINT_BYTE_COUNT)
        if len(version_data) != OPENEXR_UINT_BYTE_COUNT:
            return []
        version_flags = struct.unpack("<I", version_data)[0]
        headers.append(_read_header(stream))
        if not (version_flags & OPENEXR_MULTIPART_FLAG):
            return headers

        while True:
            first = stream.read(1)
            if not first or first == b"\0":
                break
            headers.append(_read_header(stream, first))
    return headers


def _string_attr(attrs, key):
    """Helper to extract a string attribute value.

    Args:
        attrs: Dictionary of EXR attributes.
        key: The key of the attribute to extract.

    Returns:
        str: The string value, or empty string if not found or not a string type.
    """
    attr = attrs.get(key)
    if not attr:
        return ""
    attr_type, value = attr
    if attr_type != "string":
        return ""
    return value.decode("utf-8", "replace").strip()


def _channel_names(attrs):
    """Extract list of channel names from the 'channels' attribute.

    Args:
        attrs: Dictionary of EXR attributes.

    Returns:
        List[str]: A list of channel names.
    """
    attr = attrs.get("channels")
    if not attr:
        return []
    attr_type, value = attr
    if attr_type != "chlist":
        return []

    names = []
    offset = 0
    while offset < len(value):
        end = value.find(b"\0", offset)
        if end < 0:
            break
        raw_name = value[offset:end]
        offset = end + 1
        if not raw_name:
            break
        names.append(raw_name.decode("utf-8", "replace"))
        offset += OPENEXR_CHANNEL_ENTRY_METADATA_BYTES
    return names


def _layer_names_from_channels(channels):
    """Deduce layer/AOV names from a flat list of channel names.

    Args:
        channels: List of channel name strings.

    Returns:
        List[str]: Deduced layer/AOV names.
    """
    stems = []
    seen = set()
    for channel in channels:
        if "." not in channel:
            continue
        stem = channel.rsplit(".", 1)[0]
        if stem and stem not in seen:
            seen.add(stem)
            stems.append(stem)
    if stems:
        return stems

    upper = {c.upper() for c in channels}
    if upper.issuperset({"R", "G", "B"}):
        return ["C"]
    if upper == {"Z"}:
        return ["Z"]
    return []


def list_exr_planes(exr_path: str, oiiotool_path: str | None = None) -> list[str]:
    """List all plane/AOV names in an EXR file without Houdini or oiiotool."""
    _ = oiiotool_path
    if not os.path.isfile(exr_path):
        logger.warning("EXR file not found: %s", exr_path)
        return []

    try:
        headers = _read_headers(exr_path)
    except Exception as exc:
        logger.warning("Unable to inspect EXR %s: %s", exr_path, exc)
        return []

    planes: dict[str, None] = {}
    for attrs, _order in headers:
        part_name = _string_attr(attrs, "name")
        if part_name:
            planes[part_name] = None
            continue
        for layer in _layer_names_from_channels(_channel_names(attrs)):
            planes[layer] = None

    return list(planes.keys())
