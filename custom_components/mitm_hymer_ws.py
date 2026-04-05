"""mitmproxy addon — capture & decode Hymer Connect SignalR WebSocket traffic.

Usage:
    mitmweb -s mitm_hymer_ws.py --listen-port 8080

Output files (timestamped in logs/):
    ws_capture_<timestamp>.jsonl   — one JSON object per WS message
    ws_sensors_<timestamp>.json    — accumulated decoded sensor state

Targets issues:
    #14 fuel_range, #15 engine_hours, #16 fuel_level,
    #18 light controls, #20 solar voltage, #7 unmapped bus IDs,
    #12 Truma boiler
"""

from __future__ import annotations

import base64
import json
import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import ctx, http
from mitmproxy.websocket import WebSocketMessage

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SIGNALR_HOSTS = {
    "ehg-prod-signalr.service.signalr.net",
    "scc-appcomm.smartrv.erwinhymergroup.com",
}
LOG_DIR = Path(__file__).parent / "logs"
_TS = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
JSONL_PATH = LOG_DIR / f"ws_capture_{_TS}.jsonl"
SENSOR_PATH = LOG_DIR / f"ws_sensors_{_TS}.json"

# Sensor map (subset — enough for decoding; full map in pia_decoder.py)
_SENSOR_MAP: dict[tuple[int, int], str] = {
    # can0
    (1, 1): "odometer", (1, 2): "speed", (1, 3): "lock_status",
    (1, 4): "handbrake", (1, 5): "rpm", (1, 6): "adblue_level",
    (1, 7): "engine_hours", (1, 8): "vin_text", (1, 9): "coolant_temp",
    (1, 10): "engine_running", (1, 11): "door_driver", (1, 12): "door_passenger",
    (1, 13): "door_sliding", (1, 14): "door_rear", (1, 15): "ignition_state",
    (1, 16): "seatbelt_warning", (1, 17): "turn_signal", (1, 18): "headlamp",
    (1, 19): "parking_light", (1, 20): "fog_front", (1, 21): "fog_rear",
    (1, 22): "high_beam", (1, 23): "language",
    # lin1
    (3, 1): "main_switch", (3, 2): "power_source", (3, 3): "charger_active",
    (3, 4): "charge_phase", (3, 5): "battery_voltage", (3, 6): "battery_current",
    (3, 7): "chassis_battery_voltage", (3, 8): "light_1_level", (3, 9): "light_2_level",
    (3, 10): "battery_soc", (3, 11): "battery_type",
    (3, 12): "switch_12v_1", (3, 13): "switch_12v_2", (3, 14): "switch_12v_3",
    (3, 15): "switch_12v_4", (3, 16): "switch_12v_5", (3, 17): "switch_12v_6",
    (3, 18): "switch_12v_7", (3, 19): "solar_voltage", (3, 20): "solar_connected",
    (3, 21): "solar_charger_status", (3, 22): "switch_22",
    # solar charger (15)
    (15, 1): "solar_charger_boost", (15, 2): "solar_current", (15, 3): "solar_panel_temp",
    # lin2
    (8, 1): "gray_water_sensor", (8, 2): "indoor_temp", (8, 3): "outdoor_temp",
    (8, 4): "vent_1", (8, 5): "vent_2", (8, 6): "vent_3", (8, 7): "tire_pressure",
    # alarm/step
    (11, 1): "alarm_armed", (11, 2): "alarm_battery",
    (12, 1): "step_retracted", (12, 2): "step_sensor_2", (12, 3): "step_sensor_3",
    # water pump (16)
    (16, 1): "water_pump", (16, 2): "water_pump_status",
    # dimmer (19) — lights issue #18
    (19, 1): "dimmer_1", (19, 2): "dimmer_2", (19, 3): "dimmer_3",
    (19, 4): "dimmer_4", (19, 5): "dimmer_5", (19, 6): "dimmer_6",
    (19, 7): "dimmer_7", (19, 8): "dimmer_8", (19, 9): "dimmer_9",
    (19, 10): "dimmer_10", (19, 11): "dimmer_11", (19, 12): "dimmer_12",
    (19, 13): "dimmer_13", (19, 14): "dimmer_14",
    # ext_light (16) — extended
    # roof_vent (21)
    (21, 1): "roof_vent_1", (21, 2): "roof_vent_2", (21, 3): "roof_vent_3",
    # fresh water (22)
    (22, 1): "fresh_water_sensor", (22, 2): "fresh_water_level",
    # screen (24)
    (24, 1): "screen_1", (24, 2): "screen_2",
    # grey water / inverter (25)
    (25, 1): "gray_water_sensor_ext", (25, 2): "gray_water_level",
    # generator (27)
    (27, 1): "generator_1", (27, 2): "generator_2",
    # gps (30)
    (30, 1): "gps_coordinates", (30, 2): "gps_utc_time", (30, 3): "gps_signal_quality",
    (30, 4): "gps_fix", (30, 5): "gps_altitude", (30, 6): "gps_satellites",
    (30, 7): "gps_heading",
    # heat_ctrl (34)
    (34, 1): "heat_switch_1", (34, 2): "heat_switch_2", (34, 3): "heat_mode",
    (34, 7): "heat_setpoint_raw",
    # fridge (37)
    (37, 1): "fridge_mode", (37, 2): "fridge_status",
    # wifi (43)
    (43, 1): "wifi_1", (43, 2): "wifi_2",
    # bluetooth (44)
    (44, 1): "bluetooth_1", (44, 2): "bluetooth_2",
    # scu (45)
    (45, 8): "scu_connected", (45, 11): "scu_firmware",
    # truma (49) — issue #12
    (49, 1): "truma_1", (49, 2): "truma_2", (49, 3): "truma_3",
    (49, 4): "truma_4", (49, 5): "truma_5", (49, 6): "truma_6",
    (49, 7): "truma_7", (49, 8): "truma_connected", (49, 9): "truma_9",
    (49, 10): "truma_status", (49, 11): "truma_firmware",
    (49, 12): "truma_12", (49, 13): "truma_13", (49, 14): "truma_14",
    # heater (58) — issue #12
    (58, 1): "heater_1", (58, 2): "heater_2", (58, 3): "heater_3",
    (58, 4): "heater_fuel_type", (58, 5): "heater_fan_speed",
    (58, 6): "heater_fuel_type_2", (58, 7): "heater_state",
    (58, 8): "heater_setpoint", (58, 9): "heater_electric_power",
    (58, 10): "heater_10", (58, 11): "heater_operating_mode",
    (58, 12): "heater_12", (58, 13): "heater_13", (58, 14): "heater_14",
    # can2
    (99, 1): "adblue_temp", (99, 2): "engine_torque", (99, 3): "ambient_temp",
    (99, 4): "lithium_soc", (99, 5): "fuel_range", (99, 6): "current_gear",
    (99, 7): "total_fuel_used", (99, 8): "lithium_soc_2", (99, 9): "cruise_control",
    (99, 10): "dpf_status",
}

# Bus id → name
_BUS_NAMES: dict[int, str] = {
    1: "can0", 3: "lin1", 8: "lin2", 11: "alarm", 12: "step", 15: "awning",
    16: "ext_light", 19: "dimmer", 21: "roof_vent", 22: "fresh_water",
    24: "screen", 25: "inverter", 27: "generator", 30: "gps", 34: "heat_ctrl",
    37: "fridge", 43: "wifi", 44: "bluetooth", 45: "scu", 49: "truma",
    58: "heater", 99: "can2",
}


# ---------------------------------------------------------------------------
# Minimal protobuf decoder (no external dependency)
# ---------------------------------------------------------------------------
def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _decode_fields(data: bytes) -> list[tuple[int, int, object]]:
    fields: list[tuple[int, int, object]] = []
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except (IndexError, ValueError):
            break
        fn = tag >> 3
        wt = tag & 0x07
        if wt == 0:
            val, pos = _decode_varint(data, pos)
        elif wt == 1:
            if pos + 8 > len(data):
                break
            val = struct.unpack_from("<d", data, pos)[0]
            pos += 8
        elif wt == 5:
            if pos + 4 > len(data):
                break
            val = round(struct.unpack_from("<f", data, pos)[0], 4)
            pos += 4
        elif wt == 2:
            length, pos = _decode_varint(data, pos)
            if pos + length > len(data):
                break
            val = data[pos : pos + length]
            pos += length
        else:
            break
        fields.append((fn, wt, val))
    return fields


def _try_str(data: bytes) -> str | None:
    try:
        t = data.decode("utf-8")
        if t and all(c.isprintable() or c in "\r\n\t" for c in t):
            return t
    except (UnicodeDecodeError, ValueError):
        pass
    return None


def _parse_sensor(data: bytes) -> dict | None:
    """Parse one sensor entry from protobuf bytes."""
    fields = _decode_fields(data)
    sensor_id = bus_id = None
    values: dict[str, object] = {}
    bus_name = None
    for fn, wt, val in fields:
        if fn == 1 and wt == 0:
            sensor_id = val
        elif fn == 2 and wt == 0:
            bus_id = val
        elif fn == 3 and wt == 0:
            values["uint"] = val
        elif fn == 4 and wt == 2:
            s = _try_str(val)
            if s:
                values["str"] = s
        elif fn == 5 and wt == 0:
            values["bool"] = bool(val)
        elif fn == 6 and wt == 5:
            values["float"] = val
        elif fn == 7 and wt == 0:
            values["int"] = val if val < (1 << 63) else val - (1 << 64)
        elif fn == 10 and wt == 2:
            s = _try_str(val)
            if s:
                bus_name = s
    if sensor_id is None or bus_id is None:
        return None
    key = (bus_id, sensor_id)
    name = _SENSOR_MAP.get(key, f"unknown_{bus_id}_{sensor_id}")
    return {
        "bus_id": bus_id,
        "sensor_id": sensor_id,
        "bus_name": bus_name or _BUS_NAMES.get(bus_id, f"bus{bus_id}"),
        "name": name,
        "values": values,
        "key": f"({bus_id},{sensor_id})",
    }


def decode_pia_payload(b64: str) -> list[dict]:
    """Decode a base64 PIA protobuf payload → list of sensor dicts."""
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return []
    sensors = []
    # Walk the top-level protobuf looking for nested containers
    top = _decode_fields(raw)
    for fn, wt, val in top:
        if wt != 2 or not isinstance(val, bytes):
            continue
        # Try to find sensor arrays at various nesting depths
        sub = _decode_fields(val)
        for fn2, wt2, val2 in sub:
            if wt2 != 2 or not isinstance(val2, bytes):
                continue
            sub2 = _decode_fields(val2)
            for fn3, wt3, val3 in sub2:
                if fn3 == 1 and wt3 == 2 and isinstance(val3, bytes):
                    s = _parse_sensor(val3)
                    if s:
                        sensors.append(s)
            # Also try direct sensor parse at this level
            s = _parse_sensor(val2)
            if s:
                sensors.append(s)
        # Try direct parse at top level
        s = _parse_sensor(val)
        if s:
            sensors.append(s)
    return sensors


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_jsonl_file = None
_all_sensors: dict[str, dict] = {}
_msg_count = 0
_ws_count = 0


def _ensure_log():
    global _jsonl_file
    if _jsonl_file is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _jsonl_file = open(JSONL_PATH, "a", encoding="utf-8")
        ctx.log.info(f"[HymerWS] Logging to {JSONL_PATH}")


def _log_entry(entry: dict):
    _ensure_log()
    _jsonl_file.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    _jsonl_file.flush()


def _save_sensors():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SENSOR_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "total_messages": _msg_count,
                "sensor_count": len(_all_sensors),
                "sensors": _all_sensors,
            },
            f,
            indent=2,
            default=str,
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# mitmproxy hooks
# ---------------------------------------------------------------------------
class HymerWSCapture:
    """Capture and decode Hymer Connect SignalR WebSocket traffic."""

    def websocket_message(self, flow: http.HTTPFlow):
        global _msg_count, _ws_count

        host = flow.request.pretty_host
        if not any(h in host for h in SIGNALR_HOSTS):
            return

        assert flow.websocket is not None
        msg: WebSocketMessage = flow.websocket.messages[-1]
        _msg_count += 1

        direction = "client→server" if msg.from_client else "server→client"
        content = msg.text if msg.is_text else base64.b64encode(msg.content).decode()

        # Parse SignalR JSON frames (delimited by \x1e)
        text = msg.text if msg.is_text else ""
        frames = [f.strip() for f in text.split("\x1e") if f.strip()] if text else []

        for frame_text in frames:
            try:
                frame = json.loads(frame_text)
            except json.JSONDecodeError:
                _log_entry({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "dir": direction,
                    "type": "raw",
                    "data": frame_text[:2000],
                })
                continue

            target = frame.get("target", "")
            msg_type = frame.get("type")

            entry: dict = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "dir": direction,
                "signalr_type": msg_type,
                "target": target,
            }

            # Ping
            if msg_type == 6:
                entry["type"] = "ping"
                _log_entry(entry)
                continue

            # UpdateTokens
            if target == "UpdateTokens":
                args = frame.get("arguments", [{}])
                entry["type"] = "UpdateTokens"
                if args and isinstance(args[0], dict):
                    entry["vehicle_urn"] = args[0].get("vehicleUrn", "")
                    entry["scu_urn"] = args[0].get("scuUrn", "")
                _log_entry(entry)
                ctx.log.info(f"[HymerWS] UpdateTokens {direction}")
                continue

            # UpdateTokens result
            if msg_type == 3:
                result = frame.get("result", {})
                entry["type"] = "result"
                entry["invocation_id"] = frame.get("invocationId")
                if isinstance(result, dict):
                    entry["status"] = result.get("response", {}).get("status", "")
                _log_entry(entry)
                ctx.log.info(f"[HymerWS] Result: {entry.get('status', 'unknown')}")
                continue

            # PiaRequest / PiaResponse — the main payload
            if target in ("PiaRequest", "PiaResponse"):
                args = frame.get("arguments", [])
                b64_payload = args[0] if args and isinstance(args[0], str) else ""

                sensors = decode_pia_payload(b64_payload) if b64_payload else []

                entry["type"] = target
                entry["payload_b64"] = b64_payload[:200] + ("..." if len(b64_payload) > 200 else "")
                entry["payload_len"] = len(b64_payload)
                entry["sensor_count"] = len(sensors)

                if sensors:
                    entry["sensors"] = sensors

                    # Highlight unknowns and issue-relevant sensors
                    unknowns = [s for s in sensors if s["name"].startswith("unknown_")]
                    issue_keys = {
                        "fuel_range", "engine_hours", "fuel_level", "adblue_level",
                        "solar_voltage", "solar_current", "solar_charger_boost",
                        "solar_panel_temp", "solar_charger_status", "solar_connected",
                        "light_1_level", "light_2_level",
                        "heater_setpoint", "heater_fan_speed", "heater_state",
                        "heater_operating_mode", "heater_electric_power",
                        "truma_connected", "truma_status", "truma_firmware",
                    }
                    highlighted = [s for s in sensors if s["name"] in issue_keys]

                    if unknowns:
                        ctx.log.warn(
                            f"[HymerWS] {len(unknowns)} UNKNOWN sensors: "
                            + ", ".join(f'{s["key"]}' for s in unknowns[:10])
                        )
                    if highlighted:
                        for s in highlighted:
                            ctx.log.info(
                                f"[HymerWS] >>> {s['name']} {s['key']}: {s['values']}"
                            )

                    # Also log any dimmer bus (19) sensors for light mapping
                    dimmer_sensors = [s for s in sensors if s["bus_id"] == 19]
                    if dimmer_sensors:
                        ctx.log.info(
                            f"[HymerWS] DIMMER bus sensors: "
                            + ", ".join(
                                f'{s["name"]} {s["key"]}={s["values"]}'
                                for s in dimmer_sensors
                            )
                        )

                    # Accumulate
                    for s in sensors:
                        _all_sensors[s["key"]] = {
                            "name": s["name"],
                            "bus_name": s["bus_name"],
                            "values": s["values"],
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                        }

                _log_entry(entry)

                if target == "PiaResponse" and sensors:
                    ctx.log.info(
                        f"[HymerWS] PiaResponse: {len(sensors)} sensors decoded"
                    )

                # Save accumulated sensors periodically
                if _msg_count % 10 == 0:
                    _save_sensors()

                continue

            # Any other SignalR message
            entry["type"] = "other"
            entry["data"] = json.dumps(frame, default=str)[:2000]
            _log_entry(entry)

    def done(self):
        """Called when mitmproxy shuts down."""
        global _jsonl_file
        _save_sensors()
        if _jsonl_file:
            _jsonl_file.close()
            _jsonl_file = None
        ctx.log.info(
            f"[HymerWS] Done. {_msg_count} messages, {len(_all_sensors)} sensors. "
            f"Files: {JSONL_PATH.name}, {SENSOR_PATH.name}"
        )


addons = [HymerWSCapture()]
