"""PIA Protobuf decoder/encoder for HYMER Connect sensor data.

Decodes Base64-encoded Protobuf payloads from SignalR PiaResponse messages.
Encodes PiaRequest subscription messages for sensor data streaming.
"""

from __future__ import annotations

import base64
import logging
import struct
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Sensor key map: (bus_id, sensor_id) → (name, unit, value_transform)
# value_transform: None=raw, "div10"=divide by 10, "div100"=divide by 100, "div1000"=divide by 1000
SENSOR_MAP: dict[tuple[int, int], tuple[str, str | None, str | None]] = {
    # can0 — Vehicle CAN bus
    (1, 1): ("odometer", "km", "div1000"),
    (1, 2): ("speed", "km/h", None),
    (1, 3): ("lock_status", None, None),
    (1, 4): ("handbrake", None, None),
    (1, 5): ("rpm", "rpm", "div100"),
    (1, 6): ("adblue_level", "%", None),
    (1, 7): ("engine_hours", "h", None),
    (1, 8): ("vin_text", None, None),
    (1, 9): ("coolant_temp", "\u00b0C", None),
    (1, 10): ("engine_running", None, None),
    (1, 11): ("door_driver", None, None),
    (1, 12): ("door_passenger", None, None),
    (1, 13): ("door_sliding", None, None),
    (1, 14): ("door_rear", None, None),
    (1, 15): ("ignition_state", None, None),
    (1, 16): ("seatbelt_warning", None, None),
    (1, 17): ("turn_signal", None, None),
    (1, 18): ("headlamp", None, None),
    (1, 19): ("parking_light", None, None),
    (1, 20): ("fog_front", None, None),
    (1, 21): ("fog_rear", None, None),
    (1, 22): ("high_beam", None, None),
    (1, 23): ("language", None, None),
    # lin1 — Habitation electrics
    (3, 1): ("main_switch", None, None),
    (3, 2): ("power_source", None, None),
    (3, 3): ("charger_active", None, None),
    (3, 4): ("charge_phase", None, None),
    (3, 5): ("battery_voltage", "V", None),
    (3, 6): ("battery_current", "A", None),
    (3, 7): ("chassis_battery_voltage", "V", None),
    (3, 8): ("light_1_level", "%", None),
    (3, 9): ("light_2_level", "%", None),
    (3, 10): ("battery_soc", "%", None),
    (3, 11): ("battery_type", None, None),
    (3, 12): ("switch_12v_1", None, None),
    (3, 13): ("switch_12v_2", None, None),
    (3, 14): ("switch_12v_3", None, None),
    (3, 15): ("switch_12v_4", None, None),
    (3, 16): ("switch_12v_5", None, None),
    (3, 17): ("switch_12v_6", None, None),
    (3, 18): ("switch_12v_7", None, None),
    (3, 19): ("solar_voltage", "V", None),
    (3, 20): ("solar_connected", None, None),
    (3, 21): ("solar_charger_status", None, None),
    (3, 22): ("switch_22", None, None),
    # Solar charger details (bus 15)
    # s1 is NOT "solar active" — it's False even while solar is charging.
    # Solar active state is determined by solar_connected (3,20) or power_source (3,2).
    (15, 1): ("solar_charger_boost", None, None),
    (15, 2): ("solar_current", "A", "div10"),
    (15, 3): ("solar_power", "W", None),
    # lin2 — Climate / secondary
    (8, 1): ("gray_water_sensor", None, None),
    (8, 2): ("indoor_temp", "\u00b0C", None),
    (8, 3): ("outdoor_temp", "\u00b0C", None),
    (8, 4): ("vent_1", None, None),
    (8, 5): ("vent_2", None, None),
    (8, 6): ("vent_3", None, None),
    (8, 7): ("tire_pressure", "bar", None),
    # Alarm (11)
    (11, 1): ("alarm_armed", None, None),
    (11, 2): ("alarm_battery", "%", None),
    # Step (12)
    (12, 1): ("step_retracted", None, None),
    (12, 2): ("step_sensor_2", None, None),
    (12, 3): ("step_sensor_3", None, None),
    # GPS (30)
    (30, 1): ("gps_coordinates", None, None),
    (30, 2): ("gps_utc_time", None, None),
    (30, 3): ("gps_signal_quality", None, None),
    (30, 4): ("gps_fix", None, None),
    (30, 5): ("gps_altitude", "m", None),
    (30, 6): ("gps_satellites", None, None),
    (30, 7): ("gps_heading", "\u00b0", None),
    # Heating control (34)
    (34, 1): ("heat_switch_1", None, None),
    (34, 2): ("heat_switch_2", None, None),
    (34, 3): ("heat_mode", None, None),
    (34, 7): ("heat_setpoint_raw", None, None),
    # Water pump (bus 16)
    (16, 1): ("water_pump", None, None),
    (16, 2): ("water_pump_status", None, None),
    # Water tanks — bus 22 = fresh water, bus 25 = grey water (confirmed: both ~6% when tanks empty)
    (22, 1): ("fresh_water_sensor", None, None),
    (22, 2): ("fresh_water_level", "%", None),
    (25, 1): ("gray_water_sensor_ext", None, None),
    (25, 2): ("gray_water_level", "%", None),
    # Fridge (37)
    (37, 1): ("fridge_mode", None, None),
    (37, 2): ("fridge_status", None, None),
    # SCU (45)
    (45, 8): ("scu_connected", None, None),
    (45, 11): ("scu_firmware", None, None),
    # Truma (49)
    (49, 8): ("truma_connected", None, None),
    (49, 10): ("truma_status", None, None),
    (49, 11): ("truma_firmware", None, None),
    # Truma heater (58)
    (58, 4): ("heater_fuel_type", None, None),
    (58, 5): ("heater_fan_speed", None, None),
    (58, 6): ("heater_fuel_type_2", None, None),
    (58, 7): ("heater_state", None, None),
    (58, 8): ("heater_setpoint", "\u00b0C", None),
    (58, 9): ("heater_electric_power", "W", None),
    (58, 11): ("heater_operating_mode", None, None),
    # can2 — Extended chassis CAN
    (99, 1): ("adblue_temp", "\u00b0C", None),
    (99, 2): ("engine_torque", "%", None),
    (99, 3): ("ambient_temp", "\u00b0C", None),
    (99, 4): ("fuel_consumption", None, None),
    (99, 5): ("fuel_range", "km", None),
    (99, 6): ("current_gear", None, None),
    (99, 7): ("total_fuel_used", None, None),
    (99, 8): ("trip_distance", None, None),
    (99, 9): ("cruise_control", None, None),
    (99, 10): ("dpf_status", None, None),
}

# Human-readable mappings for raw SCU string values
_VALUE_LABELS: dict[str, dict[str, str]] = {
    "door_driver": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "door_passenger": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "door_sliding": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "door_rear": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
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
    "heater_fan_speed": {"OFF": "Off", "ECO": "Eco", "HIGH": "High"},
    "heater_state": {"False": "Off", "True": "On"},
}

# Integer-to-string label maps for sensors that report numeric codes.
_INT_LABELS: dict[str, dict[int, str]] = {
    "fridge_mode": {0: "On", 1: "Eco", 2: "Boost", 8: "Off"},
    "fridge_status": {0: "Running", 1: "Off", 2: "Standby"},
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
    "Eh8I29wPEgd2MC4zMi4wGOn5ws4GIgoSCAoGCAEQDygB",
    "Eh8IibUiEgd2MC4zMi4wGO75ws4GIgoSCAoGCAEQDygA",
    "Ei4I9vYmEgd2MC4zMi4wGPb5ws4GIhkSFwoJCAUQOiIDRUNPCgoIBBA6IgRCb3Ro",
    "Ei4I+qQIEgd2MC4zMi4wGPz5ws4GIhkSFwoJCAUQOiIDT0ZGCgoIBBA6IgRCb3Ro",
    "Eh8I9v8UEgd2MC4zMi4wGIH6ws4GIgoSCAoGCAIQIigB",
    "Eh8IveYQEgd2MC4zMi4wGIL6ws4GIgoSCAoGCAIQIigA",
)


def build_subscription_requests() -> list[str]:
    """Build PiaRequest payloads for sensor data subscription.

    Returns a list of Base64-encoded protobuf payloads ready to send
    as PiaRequest arguments.  All 13 requests are needed — the first
    ones initialise different sensor groups before the big subscription
    triggers the full data flow.
    """
    return list(_PIA_REQUESTS)


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
            else:
                fallback = f"bus{entry['bus_id']}_s{entry['sensor_id']}"
                sensors[fallback] = entry["value"]
        return

    # Not a sensor entry — recurse into length-delimited sub-fields
    for fn, wt, v in fields:
        if wt == 2 and isinstance(v, bytes) and len(v) > 2:
            _extract_sensors_recursive(v, sensors, depth + 1)
