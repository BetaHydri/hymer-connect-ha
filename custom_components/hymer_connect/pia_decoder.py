"""PIA Protobuf decoder/encoder for HYMER Connect sensor data.

Decodes Base64-encoded Protobuf payloads from SignalR PiaResponse messages.
Encodes PiaRequest subscription messages for sensor data streaming.

Sensor mappings and entity definitions are loaded at runtime from JSON files
in the ``sensor_maps/`` directory.  Call :func:`load_sensor_map` at startup
to populate :data:`SENSOR_MAP` and :data:`ENTITY_DEFS` from ``base.json``
and an optional brand-specific overlay (e.g. ``eriba.json``).
"""

from __future__ import annotations

import base64
import json
import logging
import struct
import time
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Directory containing JSON overlay files
_SENSOR_MAPS_DIR = Path(__file__).parent / "sensor_maps"

# Discovery mode: tracks all sensor value changes (mapped and unmapped)
# and logs them at INFO level. Helps identify what unknown bus/sensor
# slots actually report. Enabled via HA logger config:
#   logger:
#     logs:
#       custom_components.hymer_connect.pia_decoder: info
_discovery_previous: dict[str, Any] = {}

# Sensor key map: (bus_id, sensor_id) → (name, unit, value_transform)
# value_transform: None=raw, "div10"=divide by 10, "div100"=divide by 100, "div1000"=divide by 1000, "div3600"=seconds to hours
# v2.43.0+: Populated at runtime from sensor_maps/base.json + brand overlay.
SENSOR_MAP: dict[tuple[int, int], tuple[str, str | None, str | None]] = {}

# Entity metadata loaded from JSON overlays.  Populated by load_sensor_map().
# Key: sensor name (str).  Value: dict with platform, device_class, etc.
# Only entries with a ``"platform"`` field in the JSON appear here.
ENTITY_DEFS: dict[str, dict[str, Any]] = {}

# Light definitions loaded from JSON ``"lights"`` section.
# Key: bus_id (int).  Value: dict with name, icon, brightness, color_temp.
LIGHT_DEFS: dict[int, dict[str, Any]] = {}

# Switch definitions loaded from JSON ``"switches"`` section.
# Key: ``"bus_id,sensor_id"`` string.  Value: dict with name, icon, write_type, etc.
SWITCH_DEFS: dict[str, dict[str, Any]] = {}

# Climate/control definitions loaded from JSON ``"climate"`` section.
# Contains bus/slot IDs for heater, fridge, and boiler — used by
# climate.py and select.py to parameterize write commands per brand.
CLIMATE_DEFS: dict[str, dict[str, Any]] = {}

# Track whether overlays have already been loaded (prevents re-loading on
# integration reload, since SENSOR_MAP is module-level and persists).
_overlays_loaded: set[str] = set()


def _load_json_overlay(filename: str) -> int:
    """Load a single JSON overlay file and merge into SENSOR_MAP / ENTITY_DEFS.

    Supports two value formats per sensor entry:

    * **Array** (v2.42 compat): ``["name", "unit", "transform"]``
    * **Object** (v2.43+): ``{"name": "…", "unit": "…", "platform": "sensor", …}``

    Object entries with a ``"platform"`` key are also stored in
    :data:`ENTITY_DEFS` so that ``sensor.py`` / ``binary_sensor.py`` can
    build HA entity descriptions at runtime.

    Additionally loads ``"lights"`` and ``"switches"`` sections (v2.44.0+)
    into :data:`LIGHT_DEFS` and :data:`SWITCH_DEFS`.

    Overlay entries **override** existing entries for the same key.

    Returns:
        Number of sensor entries merged (lights/switches not counted).
    """
    path = _SENSOR_MAPS_DIR / filename
    if not path.is_file():
        return 0

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _LOGGER.error("Failed to load sensor map %s: %s", filename, exc)
        return 0

    _ENTITY_FIELDS = (
        "platform", "device_class", "state_class", "icon",
        "on_value", "enabled", "entity_category",
    )

    sensors = data.get("sensors", {})
    count = 0
    for key_str, value in sensors.items():
        parts = key_str.split(",")
        if len(parts) != 2:
            continue
        bus_id, sensor_id = int(parts[0].strip()), int(parts[1].strip())

        if isinstance(value, list):
            # v2.42 backward compat: [name, unit, transform]
            name = value[0]
            unit = value[1] if len(value) > 1 else None
            transform = value[2] if len(value) > 2 else None
        elif isinstance(value, dict):
            name = value.get("name", f"bus{bus_id}_s{sensor_id}")
            unit = value.get("unit")
            transform = value.get("transform")
            # Store entity metadata when a platform is declared
            if "platform" in value:
                meta = {k: value[k] for k in _ENTITY_FIELDS if k in value}
                if unit is not None:
                    meta["unit"] = unit
                ENTITY_DEFS[name] = meta
        else:
            continue

        SENSOR_MAP[(bus_id, sensor_id)] = (name, unit, transform)
        count += 1

    # --- Lights section (v2.44.0+) ---
    # Keyed by bus_id string. Convention: sid 1=on/off, sid 2=brightness,
    # sid 3=color_temp. The JSON declares which capabilities the light has.
    lights = data.get("lights", {})
    for bus_str, light_def in lights.items():
        if not isinstance(light_def, dict):
            continue
        bus_id = int(bus_str.strip())
        LIGHT_DEFS[bus_id] = light_def
    if lights:
        _LOGGER.debug("Loaded %d light definitions from %s", len(lights), filename)

    # --- Switches section (v2.44.0+) ---
    # Keyed by "bus_id,sensor_id" string. Defines write-command metadata.
    switches = data.get("switches", {})
    for key_str, switch_def in switches.items():
        if not isinstance(switch_def, dict):
            continue
        SWITCH_DEFS[key_str] = switch_def
    if switches:
        _LOGGER.debug("Loaded %d switch definitions from %s", len(switches), filename)

    # --- Climate section (v2.45.0+) ---
    # Defines bus/slot IDs for heater, fridge, and boiler per brand.
    # Later entries override earlier ones (brand overrides base).
    climate = data.get("climate", {})
    for key, climate_def in climate.items():
        if key.startswith("_"):
            continue
        if isinstance(climate_def, dict):
            CLIMATE_DEFS[key] = climate_def
    if climate:
        _LOGGER.debug("Loaded %d climate definitions from %s",
                       sum(1 for k in climate if not k.startswith("_")), filename)

    return count


def load_sensor_map(brand: str) -> None:
    """Load sensor map overlays for the given brand.

    Loads ``base.json`` (shared across all EHG brands) first, then the
    brand-specific overlay (e.g. ``eriba.json``).  Populates both
    :data:`SENSOR_MAP` (decode layer) and :data:`ENTITY_DEFS` (entity
    metadata for ``sensor.py`` / ``binary_sensor.py``).

    ``base.json`` is required — if missing, an error is logged and no
    sensor mappings will be available.  The brand overlay is optional.

    This function is idempotent: calling it multiple times with the same brand
    is safe and will not re-load files.

    Args:
        brand: The EHG brand key (e.g. ``"hymer"``, ``"eriba"``, ``"buerstner"``).
    """
    cache_key = f"brand:{brand}"
    if cache_key in _overlays_loaded:
        return

    base_count = 0
    brand_count = 0

    if "base" not in _overlays_loaded:
        base_count = _load_json_overlay("base.json")
        _overlays_loaded.add("base")
        if base_count:
            _LOGGER.info("Sensor map: loaded base.json (%d entries)", base_count)
        else:
            _LOGGER.error(
                "Sensor map: base.json missing or empty — no sensor mappings loaded! "
                "Ensure sensor_maps/base.json is present in custom_components/hymer_connect/."
            )

    brand_file = f"{brand}.json"
    brand_count = _load_json_overlay(brand_file)
    if brand_count:
        _LOGGER.info(
            "Sensor map: loaded %s (%d entries)",
            brand_file, brand_count,
        )
    else:
        _LOGGER.debug("Sensor map: no brand overlay for '%s' (using base only)", brand)

    _overlays_loaded.add(cache_key)
    _LOGGER.info(
        "Sensor map ready: %d total entries (base=%d, %s=%d, hardcoded=%d), "
        "%d lights, %d switches, %d climate defs",
        len(SENSOR_MAP), base_count, brand, brand_count,
        len(SENSOR_MAP) - base_count - brand_count,
        len(LIGHT_DEFS), len(SWITCH_DEFS), len(CLIMATE_DEFS),
    )


# Human-readable mappings for raw SCU string values
_VALUE_LABELS: dict[str, dict[str, str]] = {
    "door_driver": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "door_passenger": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "wiping_water_empty": {"OFF": "Off", "ON": "On"},
    "motor_oil_warning": {"OFF": "Off", "ON": "On"},
    "ignition_state": {
        "IGN_LOCK": "Off",
        "IGN_OFF": "Accessory",
        "IGN_ACC": "Accessory",
        "IGN_ON": "On",
        "IGN_START": "Starting",
    },
    "lock_status": {
        "Vehicle unlocked": "Unlocked",
        "Vehicle external locked": "Locked",
        "Vehicle internal locked": "Locked (inside)",
    },
    "headlamp": {"OFF": "Off", "ON": "On"},
    "fog_front": {"OFF": "Off", "ON": "On"},
    "fog_rear": {"OFF": "Off", "ON": "On"},
    "high_beam": {"OFF": "Off", "ON": "On"},
    "parking_light": {"OFF": "Off", "ON": "On"},
    "turn_signal": {"OFF": "Off", "ON": "On"},
    # Chassis state flags (bus 1, slots 17-22) — remapped from vehicle lights
    "parking_brake": {"OFF": "Off", "ON": "On"},
    "standheizung_available": {"OFF": "Off", "ON": "On"},
    "standheizung_state": {"OFF": "Off", "ON": "On"},
    "cruise_control_can": {"OFF": "Off", "ON": "On"},
    "downhill_assist": {"OFF": "Off", "ON": "On"},
    "coolant_warning": {"OFF": "Off", "ON": "On"},
    "heater_fan_speed": {"OFF": "Off", "ECO": "Eco", "HOT": "Hot", "HIGH": "High", "VENT": "Vent"},
    "heater_state": {"False": "Off", "True": "On"},
}

# Integer-to-string label maps for sensors that report numeric codes.
_INT_LABELS: dict[str, dict[int, str]] = {
    "dpf_status": {0: "Normal", 1: "Regeneration"},
    "fridge_mode": {0: "On", 1: "Eco", 2: "Boost", 8: "Off"},
    "fridge_status": {0: "Open", 1: "Closed"},  # Operating state labels from SCU, not physical door
}

# Sentinel float values that indicate "sensor unavailable / not connected".
# The SCU stores 32768 (0x8000) as CAN "no data" — scaled to float as 3276.8.
_FLOAT_SENTINELS: set[float] = {3276.8, 32768.0, 65535.0, 6553.5}

# Mercedes Sprinter 7G-TRONIC automatic transmission gear mapping.
# CAN bus reports gear position as integers; this maps them to readable labels.
# Confirmed: 100 = P (observed while parked).
# TODO: Capture R, N, D values while driving via mitmproxy (#5).
_GEAR_MAP: dict[int, str] = {
    0: "N",
    1: "1",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    100: "P",
}

# All PiaRequest payloads captured from the Hymer Connect app.
# These initialise sensor groups and subscribe to all sensor data from the SCU.
# The server requires all of them to be sent in sequence.
_PIA_REQUESTS = (
    "EhcI/4kTEgd2MC4zMi4wGNr5ws4GIgIKAA==",
    "ErUKCMO2AhIHdjAuMzIuMBja+cLOBiKfChqcCgoKCAEQAVIEY2FuMAoKCAIQAVIEY2FuMAoKCAMQAVIEY2FuMAoKCAQQAVIEY2FuMAoKCAUQAVIEY2FuMAoKCAYQAVIEY2FuMAoKCAcQAVIEY2FuMAoKCAgQAVIEY2FuMAoKCAkQAVIEY2FuMAoKCAoQAVIEY2FuMAoKCAsQAVIEY2FuMAoKCAwQAVIEY2FuMAoKCA0QAVIEY2FuMAoKCA4QAVIEY2FuMAoKCA8QAVIEY2FuMAoKCBAQAVIEY2FuMAoKCBEQAVIEY2FuMAoKCBIQAVIEY2FuMAoKCBMQAVIEY2FuMAoKCBQQAVIEY2FuMAoKCBUQAVIEY2FuMAoKCBYQAVIEY2FuMAoKCBcQAVIEY2FuMAoKCAEQA1IEbGluMQoKCAIQA1IEbGluMQoKCAMQA1IEbGluMQoKCAQQA1IEbGluMQoKCAUQA1IEbGluMQoKCAYQA1IEbGluMQoKCAcQA1IEbGluMQoKCAgQA1IEbGluMQoKCAkQA1IEbGluMQoKCAoQA1IEbGluMQoKCAsQA1IEbGluMQoKCAwQA1IEbGluMQoKCA0QA1IEbGluMQoKCA4QA1IEbGluMQoKCA8QA1IEbGluMQoKCBAQA1IEbGluMQoKCBEQA1IEbGluMQoKCBIQA1IEbGluMQoKCBMQA1IEbGluMQoKCBQQA1IEbGluMQoKCBUQA1IEbGluMQoKCBYQA1IEbGluMQoKCAEQCFIEbGluMgoKCAIQCFIEbGluMgoKCAMQCFIEbGluMgoKCAQQCFIEbGluMgoKCAUQCFIEbGluMgoKCAYQCFIEbGluMgoKCAcQCFIEbGluMgoECAEQCwoECAIQCwoECAEQDAoECAIQDAoECAMQDAoECAEQDwoECAIQDwoECAMQDwoECAEQEAoECAIQEAoECAEQEwoECAIQEwoECAEQFQoECAIQFQoECAEQFgoECAIQFgoECAEQGAoECAIQGAoECAMQGAoECAEQGQoECAIQGQoECAEQGwoECAIQGwoECAMQGwoECAEQHgoECAIQHgoECAMQHgoECAQQHgoECAUQHgoECAYQHgoECAcQHgoECAgQHgoECAkQHgoECAoQHgoECAsQHgoECAwQHgoECA0QHgoECA4QHgoKCAEQIlIEbGluMQoKCAIQIlIEbGluMQoKCAMQIlIEbGluMQoKCAQQIlIEbGluMQoKCAUQIlIEbGluMQoKCAYQIlIEbGluMQoKCAcQIlIEbGluMQoECAEQJQoECAIQJQoECAEQKwoECAIQKwoECAEQLAoECAIQLAoKCAgQLVIEbGluMQoKCAkQLVIEbGluMQoKCAoQLVIEbGluMQoKCAsQLVIEbGluMQoKCAgQMVIEbGluMQoKCAoQMVIEbGluMQoKCAsQMVIEbGluMQoKCAQQOlIEbGluMQoKCAUQOlIEbGluMQoKCAYQOlIEbGluMQoKCAcQOlIEbGluMQoKCAgQOlIEbGluMQoKCAkQOlIEbGluMQoKCAoQOlIEbGluMQoKCAsQOlIEbGluMQoKCAwQOlIEbGluMQoKCA0QOlIEbGluMQoKCA4QOlIEbGluMQoKCAEQY1IEY2FuMgoKCAIQY1IEY2FuMgoKCAMQY1IEY2FuMgoKCAQQY1IEY2FuMgoKCAUQY1IEY2FuMgoKCAYQY1IEY2FuMgoKCAcQY1IEY2FuMgoKCAgQY1IEY2FuMgoKCAkQY1IEY2FuMgoKCAoQY1IEY2FuMg==",
    "EhsIqdQjEgd2MC4zMi4wGNr5ws4GIgZKBAoCCAA=",
    "EhcIn7UFEgd2MC4zMi4wGNv5ws4GKgIaAA==",
    "EhcItPYkEgd2MC4zMi4wGNv5ws4GYgIKAA==",
    "EhcIjI8GEgd2MC4zMi4wGNv5ws4GSgIKAA==",
    "EhUIjekiEgd2MC4zMi4wGNz5ws4GegA=",
    # Entries 7-12 removed: were device COMMANDS (light ON/OFF, fridge ECO/OFF,
    # water valve ON/OFF) captured during an app session, NOT subscriptions.
    # Re-sending them on every resubscribe would toggle devices every 60 seconds.
)


def build_subscription_requests() -> list[str]:
    """Build PiaRequest payloads for sensor data subscription.

    Returns a list of Base64-encoded protobuf payloads ready to send
    as PiaRequest arguments.  The 7 requests initialise different
    sensor groups and trigger the full data flow from the SCU.
    """
    return list(_PIA_REQUESTS)


def build_refresh_command() -> str:
    """Build a PiaRequest poll/refresh command to force SCU to re-report all states.

    The EHG app sends this after subscribing (shows "aktualisiere").
    Uses protobuf field 9 (empty) which triggers a full state refresh.
    """
    import random
    msg_id = random.randint(1, 10_000_000)
    ts = int(time.time())

    wrapper = _encode_varint_field(1, msg_id)
    wrapper += _encode_bytes_field(2, b"v0.32.0")
    wrapper += _encode_varint_field(3, ts)
    wrapper += _encode_bytes_field(9, b"")  # field 9 = refresh/poll

    payload = _encode_bytes_field(2, wrapper)
    return base64.b64encode(payload).decode("ascii")


def build_restart_system_request(*, cold: bool = True) -> str:
    """Build a Request.command.restart PIA request to reboot the SCU.

    Mirrors the EHG app's request.command.restart path:
    - Request.command → field 9
    - CommandRequestTopic.restart → field 2
    - RestartCommand.cold → field 1 (1 = cold reboot)

    Credit: Dan Simms (dan-simms1/hymer-connect-ha) decoded this protocol path.
    """
    import random
    msg_id = random.randint(1, 10_000_000)
    ts = int(time.time())

    # RestartCommand: field 1 = cold (bool as varint)
    restart_cmd = _encode_varint_field(1, 1 if cold else 0)
    # CommandRequestTopic: field 2 = restart
    command_topic = _encode_bytes_field(2, restart_cmd)

    # Request envelope
    wrapper = _encode_varint_field(1, msg_id)
    wrapper += _encode_bytes_field(2, b"v0.32.0")
    wrapper += _encode_varint_field(3, ts)
    wrapper += _encode_bytes_field(9, command_topic)  # field 9 = command

    payload = _encode_bytes_field(2, wrapper)
    return base64.b64encode(payload).decode("ascii")


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_field(field_number: int, wire_type: int, data: bytes) -> bytes:
    """Encode a protobuf field with tag and data."""
    tag = _encode_varint((field_number << 3) | wire_type)
    return tag + data


def _encode_varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint field."""
    return _encode_field(field_number, 0, _encode_varint(value))


def _encode_bytes_field(field_number: int, data: bytes) -> bytes:
    """Encode a length-delimited field."""
    return _encode_field(field_number, 2, _encode_varint(len(data)) + data)


def _encode_str_field(field_number: int, value: str) -> bytes:
    """Encode a string as a length-delimited field."""
    data = value.encode("utf-8")
    return _encode_bytes_field(field_number, data)


def _encode_float_field(field_number: int, value: float) -> bytes:
    """Encode a 32-bit float field (wire type 5)."""
    return _encode_field(field_number, 5, struct.pack("<f", value))


def build_light_command(
    bus_id: int,
    sensor_id: int,
    *,
    bool_value: bool | None = None,
    uint_value: int | None = None,
    str_value: str | None = None,
) -> str:
    """Build a PiaRequest payload to control a light or switch.

    Args:
        bus_id: The bus ID (e.g. 11 for living ceiling, 3 for main switch).
        sensor_id: 1=on/off, 2=brightness, 3=color_temp.
        bool_value: True/False for on/off (sensor_id=1).
        uint_value: 0-100 for brightness/color_temp (sensor_id=2,3).
        str_value: String value (e.g. "On"/"Off" for main switch on bus 3).

    Returns:
        Base64-encoded protobuf payload ready to send as PiaRequest argument.
    """
    # Build sensor entry: field1=sensor_id, field2=bus_id, field3/4/5=value
    sensor_data = _encode_varint_field(1, sensor_id)
    sensor_data += _encode_varint_field(2, bus_id)
    if str_value is not None:
        sensor_data += _encode_str_field(4, str_value)
    elif bool_value is not None:
        sensor_data += _encode_varint_field(5, 1 if bool_value else 0)
    elif uint_value is not None:
        sensor_data += _encode_varint_field(3, uint_value)

    # Nest: sensor_data inside field1 of sub2, inside field2 of inner
    sub2 = _encode_bytes_field(1, sensor_data)
    inner = _encode_bytes_field(2, sub2)

    # Build wrapper: msg_id, version, timestamp, command
    import random
    msg_id = random.randint(1, 10_000_000)
    version_bytes = b"v0.32.0"
    ts = int(time.time())

    wrapper = _encode_varint_field(1, msg_id)
    wrapper += _encode_bytes_field(2, version_bytes)
    wrapper += _encode_varint_field(3, ts)
    wrapper += _encode_bytes_field(4, inner)

    # Top-level: field 2 = wrapper
    payload = _encode_bytes_field(2, wrapper)

    return base64.b64encode(payload).decode("ascii")


def build_multi_sensor_command(
    sensors: list[dict],
) -> str:
    """Build a PiaRequest payload with multiple sensor entries.

    Each sensor dict must have:
        bus_id: int
        sensor_id: int
    And one of:
        bool_value: bool
        uint_value: int
        str_value: str
        float_value: float

    Used for heater setpoint (temp + fuel type) and boiler mode commands.
    """
    import random

    entries = b""
    for s in sensors:
        sensor_data = _encode_varint_field(1, s["sensor_id"])
        sensor_data += _encode_varint_field(2, s["bus_id"])
        if "bool_value" in s:
            sensor_data += _encode_varint_field(5, 1 if s["bool_value"] else 0)
        elif "uint_value" in s:
            sensor_data += _encode_varint_field(3, s["uint_value"])
        elif "str_value" in s:
            sensor_data += _encode_str_field(4, s["str_value"])
        elif "float_value" in s:
            sensor_data += _encode_float_field(6, s["float_value"])
        entries += _encode_bytes_field(1, sensor_data)

    inner = _encode_bytes_field(2, entries)

    msg_id = random.randint(1, 10_000_000)
    ts = int(time.time())

    wrapper = _encode_varint_field(1, msg_id)
    wrapper += _encode_bytes_field(2, b"v0.32.0")
    wrapper += _encode_varint_field(3, ts)
    wrapper += _encode_bytes_field(4, inner)

    payload = _encode_bytes_field(2, wrapper)
    return base64.b64encode(payload).decode("ascii")


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a varint, return (value, new_pos)."""
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


def _decode_protobuf(data: bytes) -> list[tuple[int, int, Any]]:
    """Decode raw protobuf into (field_number, wire_type, value) tuples."""
    fields: list[tuple[int, int, Any]] = []
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except (IndexError, ValueError):
            break
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:  # varint
            value, pos = _decode_varint(data, pos)
            fields.append((field_number, 0, value))
        elif wire_type == 1:  # fixed64
            if pos + 8 > len(data):
                break
            value = struct.unpack_from("<d", data, pos)[0]
            pos += 8
            fields.append((field_number, 1, value))
        elif wire_type == 5:  # fixed32
            if pos + 4 > len(data):
                break
            value = struct.unpack_from("<f", data, pos)[0]
            pos += 4
            fields.append((field_number, 5, round(value, 2)))
        elif wire_type == 2:  # length-delimited
            length, pos = _decode_varint(data, pos)
            if pos + length > len(data):
                break
            value = data[pos : pos + length]
            pos += length
            fields.append((field_number, 2, value))
        else:
            break
    return fields


def _try_string(data: bytes) -> str | None:
    """Try decoding bytes as UTF-8 printable string."""
    try:
        text = data.decode("utf-8")
        if text and all(c.isprintable() or c in "\r\n\t" for c in text):
            return text
    except (UnicodeDecodeError, ValueError):
        pass
    return None


def _parse_sensor_entry(data: bytes) -> dict[str, Any] | None:
    """Parse a single sensor entry from protobuf bytes.

    Each sensor carries its value in exactly one of several typed protobuf
    fields (uint, string, bool, float, int).  However the SCU sometimes
    populates *both* a uint/int field **and** the bool field for the same
    sensor.  Because ``True == 1`` in Python the bool would silently
    satisfy an ``on_value=1`` check even when the uint is 0.

    To avoid this, we collect *all* value candidates and prefer the more
    specific numeric types (uint → field 3, int → field 7) over the
    boolean (field 5) whenever both are present.
    """
    fields = _decode_protobuf(data)
    sensor_id = 0
    bus_id = 0
    bus_name = ""
    # Collect value candidates keyed by protobuf field number.
    values: dict[int, Any] = {}

    for fn, wt, v in fields:
        if fn == 1 and wt == 0:
            sensor_id = v
        elif fn == 2 and wt == 0:
            bus_id = v
        elif fn == 3 and wt == 0:
            values[3] = v  # uint
        elif fn == 4 and wt == 2:
            s = _try_string(v)
            if s is not None:
                values[4] = s
        elif fn == 5 and wt == 0:
            values[5] = bool(v)  # bool stored as varint
        elif fn == 6 and wt == 5:
            values[6] = v  # float32
        elif fn == 7 and wt == 0:
            values[7] = v  # signed int (as varint)
        elif fn == 10 and wt == 2:
            s = _try_string(v)
            if s:
                bus_name = s

    # Pick the best value: prefer string → float → uint → int → bool.
    # uint/int take precedence over bool to avoid True==1 confusion.
    value: Any = None
    for candidate_field in (4, 6, 3, 7, 5):
        if candidate_field in values:
            value = values[candidate_field]
            break

    if not sensor_id and value is None:
        return None

    return {
        "sensor_id": sensor_id,
        "bus_id": bus_id,
        "bus_name": bus_name,
        "value": value,
    }


def decode_pia_payload(b64_payload: str) -> dict[str, Any]:
    """Decode a PiaResponse Base64 payload into named sensor values.

    Returns a dict keyed by sensor name (e.g. "battery_voltage": 12.8).
    Unknown sensors are keyed as "bus{bus_id}_s{sensor_id}".
    """
    try:
        raw = base64.b64decode(b64_payload)
    except Exception:
        _LOGGER.warning("Failed to base64-decode PIA payload")
        return {}

    sensors: dict[str, Any] = {}
    top_fields = _decode_protobuf(raw)

    for fn, wt, v in top_fields:
        if wt != 2 or not isinstance(v, bytes):
            continue

        # Try to find sensor entries at multiple nesting levels
        _extract_sensors_recursive(v, sensors, depth=0)

    return sensors


def _extract_sensors_recursive(
    data: bytes, sensors: dict[str, Any], depth: int
) -> None:
    """Recursively search for sensor entries in nested protobuf."""
    if depth > 5:
        return

    fields = _decode_protobuf(data)

    # Check if this looks like a sensor entry (has field 1 + field 2 as varints)
    has_sid = any(fn == 1 and wt == 0 for fn, wt, _ in fields)
    has_bus = any(fn == 2 and wt == 0 for fn, wt, _ in fields)
    has_value = any(
        (fn in (3, 4, 5, 6, 7) and wt in (0, 2, 5))
        for fn, wt, _ in fields
    )

    if has_sid and has_bus and has_value:
        # Guard against message wrappers that mimic sensor structure.
        # Wrappers carry F1=msg_id (e.g. 39747) and F3=epoch-ms timestamp;
        # real sensors have IDs < 1000.  Wrappers must fall through to
        # recursion so the actual sensor entries nested inside get decoded.
        #
        # Additionally, real sensor entries appear at depth 2-3 in the
        # protobuf hierarchy.  Entries at depth >= 4 are misinterpreted
        # container structures that produce phantom sensor values (e.g.
        # fresh_water_level=0 at depth 5 overwriting the real value).
        #
        # Exception: known SENSOR_MAP entries at depth 4 are accepted.
        # The SCU nests real-time push updates one level deeper than the
        # initial subscription response.  Without this, sensors like
        # fridge_status (37,2) and heater_window_switch_closed (58,14)
        # silently stop updating after the initial state is received.
        sid_val = next((v for fn, wt, v in fields if fn == 1 and wt == 0), 0)
        bus_val = next((v for fn, wt, v in fields if fn == 2 and wt == 0), 0)
        is_known = (bus_val, sid_val) in SENSOR_MAP
        if sid_val < 1000 and bus_val < 1000 and (depth <= 3 or (depth == 4 and is_known)):
            entry = _parse_sensor_entry(data)
            if entry and entry["value"] is not None:
                key = (entry["bus_id"], entry["sensor_id"])
                mapped = SENSOR_MAP.get(key)
                if mapped:
                    name, unit, transform = mapped
                    val = entry["value"]
                    # Filter out CAN/SCU sentinel "not available" values
                    if isinstance(val, (int, float)) and val in _FLOAT_SENTINELS:
                        return
                    if transform == "div10" and isinstance(val, (int, float)):
                        val = val / 10
                    elif transform == "div100" and isinstance(val, (int, float)):
                        val = val / 100
                    elif transform == "div1000" and isinstance(val, (int, float)):
                        val = val / 1000
                    elif transform == "div3600" and isinstance(val, (int, float)):
                        val = round(val / 3600, 1)
                    elif transform == "invert100" and isinstance(val, (int, float)):
                        val = 100 - val
                    # Map raw string values to readable labels
                    if isinstance(val, str) and name in _VALUE_LABELS:
                        val = _VALUE_LABELS[name].get(val, val)
                    # Map integer values to readable labels (gear, fridge, etc.)
                    if isinstance(val, int) and name in _INT_LABELS:
                        val = _INT_LABELS[name].get(val, val)
                    # Map gear integer to readable position
                    if name == "current_gear" and isinstance(val, int):
                        val = _GEAR_MAP.get(val, str(val))
                    sensors[name] = val
                    # Discovery: track mapped sensor changes at DEBUG
                    prev = _discovery_previous.get(name)
                    if prev != val:
                        _discovery_previous[name] = val
                        _LOGGER.debug(
                            "DISCOVERY mapped (%d,%d) %s: %r → %r",
                            entry["bus_id"], entry["sensor_id"],
                            name, prev, val,
                        )
                        # Log door/window state changes at INFO so they
                        # are visible without enabling DEBUG logging.
                        if name in ("fridge_status", "heater_window_switch_closed"):
                            _LOGGER.info(
                                "State change (%d,%d) %s: %r → %r (depth=%d)",
                                entry["bus_id"], entry["sensor_id"],
                                name, prev, val, depth,
                            )
                else:
                    fallback = f"bus{entry['bus_id']}_s{entry['sensor_id']}"
                    sensors[fallback] = entry["value"]
                    # Discovery logging: log unmapped sensor value changes
                    # to help identify what unknown slots actually report.
                    prev = _discovery_previous.get(fallback)
                    if prev != entry["value"]:
                        _discovery_previous[fallback] = entry["value"]
                        _LOGGER.info(
                            "DISCOVERY unmapped (%d,%d) %s: %r → %r",
                            entry["bus_id"], entry["sensor_id"],
                            fallback, prev, entry["value"],
                        )
            return

    # Not a sensor entry (or wrapper) — recurse into length-delimited sub-fields
    for fn, wt, v in fields:
        if wt == 2 and isinstance(v, bytes) and len(v) > 2:
            _extract_sensors_recursive(v, sensors, depth + 1)
