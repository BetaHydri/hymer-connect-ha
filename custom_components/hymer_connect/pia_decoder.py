"""Lightweight Protobuf decoder for HYMER PIA (Platform Integration Adapter) messages.

The SignalR datahub exchanges PiaRequest/PiaResponse messages whose payloads are
Base64-encoded Protocol Buffer data.  This module provides a generic wire-format
decoder plus higher-level helpers that map known field/bus combinations to
human-readable sensor names.

No .proto schema file is required — we decode at the wire level.
"""

from __future__ import annotations

import base64
import logging
import struct
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Wire types
WIRETYPE_VARINT = 0
WIRETYPE_FIXED64 = 1
WIRETYPE_LENGTH_DELIMITED = 2
WIRETYPE_FIXED32 = 5


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a varint from *data* starting at *pos*. Return (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def decode_protobuf(data: bytes) -> list[tuple[int, int, Any]]:
    """Decode raw protobuf bytes into a flat list of (field_number, wire_type, value).

    For length-delimited fields the value is the raw bytes (which may itself be
    a nested protobuf message or a UTF-8 string).
    """
    fields: list[tuple[int, int, Any]] = []
    pos = 0
    while pos < len(data):
        try:
            tag, pos = decode_varint(data, pos)
        except (IndexError, ValueError):
            break
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == WIRETYPE_VARINT:
            value, pos = decode_varint(data, pos)
            fields.append((field_number, wire_type, value))
        elif wire_type == WIRETYPE_FIXED64:
            value = struct.unpack_from("<d", data, pos)[0]
            pos += 8
            fields.append((field_number, wire_type, value))
        elif wire_type == WIRETYPE_FIXED32:
            value = struct.unpack_from("<f", data, pos)[0]
            pos += 4
            fields.append((field_number, wire_type, value))
        elif wire_type == WIRETYPE_LENGTH_DELIMITED:
            length, pos = decode_varint(data, pos)
            value = data[pos : pos + length]
            pos += length
            fields.append((field_number, wire_type, value))
        else:
            # Unknown wire type — stop parsing
            break
    return fields


def try_decode_string(data: bytes) -> str | None:
    """Try to decode bytes as a UTF-8 string, return None on failure."""
    try:
        text = data.decode("utf-8")
        if all(c.isprintable() or c in "\r\n\t" for c in text):
            return text
    except (UnicodeDecodeError, ValueError):
        pass
    return None


def _extract_sensor_fields(
    fields: list[tuple[int, int, Any]],
    depth: int = 0,
    prefix: str = "",
) -> dict[str, Any]:
    """Recursively extract sensor values from decoded protobuf fields.

    Returns a flat dict with descriptive keys where possible.
    """
    result: dict[str, Any] = {}
    for field_number, wire_type, value in fields:
        key = f"{prefix}f{field_number}" if prefix else f"f{field_number}"

        if wire_type == WIRETYPE_VARINT:
            result[key] = value
        elif wire_type in (WIRETYPE_FIXED32, WIRETYPE_FIXED64):
            result[key] = round(value, 4) if isinstance(value, float) else value
        elif wire_type == WIRETYPE_LENGTH_DELIMITED and isinstance(value, bytes):
            text = try_decode_string(value)
            if text is not None:
                result[key] = text
            elif depth < 4:
                # Try recursive decode as nested protobuf
                nested = decode_protobuf(value)
                if nested:
                    nested_vals = _extract_sensor_fields(
                        nested, depth + 1, f"{key}."
                    )
                    result.update(nested_vals)
                else:
                    result[key] = value.hex()
            else:
                result[key] = value.hex()
    return result


def decode_pia_payload(b64_payload: str) -> dict[str, Any]:
    """Decode a Base64-encoded PIA protobuf payload into a flat dict of values."""
    try:
        raw = base64.b64decode(b64_payload)
    except Exception:
        _LOGGER.warning("Failed to base64-decode PIA payload")
        return {}

    fields = decode_protobuf(raw)
    return _extract_sensor_fields(fields)


def extract_sensor_data(pia_data: dict[str, Any]) -> dict[str, Any]:
    """Map raw PIA fields to human-readable sensor names.

    This is based on observed field patterns from traffic captures.
    The mapping will be refined as more data points are collected.
    """
    sensors: dict[str, Any] = {}

    for key, value in pia_data.items():
        # Collect all values — the coordinator can filter later
        sensors[key] = value

        # Known string mappings from captured traffic
        if isinstance(value, str):
            val_lower = value.lower()
            if value in ("ON", "OFF", "CLS", "SNA"):
                sensors[key] = value
            elif "unlocked" in val_lower or "locked" in val_lower:
                sensors.setdefault("lock_status", value)
            elif "ign_lock" in val_lower:
                sensors.setdefault("ignition_status", value)
            elif "agm" in val_lower or "lithium" in val_lower:
                sensors.setdefault("battery_type", value)
            elif "diesel" in val_lower or "petrol" in val_lower:
                sensors.setdefault("fuel_type", value)
            elif "eco" in val_lower or "bulk" in val_lower:
                sensors.setdefault("charge_mode", value)
            elif "excellent" in val_lower or "good" in val_lower or "poor" in val_lower:
                sensors.setdefault("signal_quality", value)

    return sensors
