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
# value_transform: None=raw, "div10"=divide by 10, "div100"=divide by 100, "div1000"=divide by 1000, "div3600"=seconds to hours
SENSOR_MAP: dict[tuple[int, int], tuple[str, str | None, str | None]] = {
    # Bus 1 — VehicleSignal (Mercedes Sprinter / Fiat Ducato chassis CAN).
    # Earlier labels on this bus did not match what the slots actually
    # report on the 2025 Grand Canyon S700 the integration was tested on:
    # (1, 2) labelled "speed" sits at ~6 when parked; reads as fuel % instead,
    # (1, 5) "rpm" is a constant large number; reads as km-to-service,
    # (1, 9) "coolant_temp" tracks weather not engine temperature, etc.
    # Each rename below has a trailing comment with the previous label.
    (1, 1): ("odometer", "km", "div1000"),
    (1, 2): ("fuel_level", "%", None),                       # was speed (km/h)
    (1, 3): ("lock_status", None, None),
    (1, 4): ("test_signal_write", None, None),               # was handbrake (writable slot)
    (1, 5): ("distance_to_service", "km", "div100"),         # was rpm
    (1, 6): ("adblue_level", "%", None),
    (1, 7): ("adblue_remaining_distance", "km", "div100"),   # was engine_hours
    (1, 8): ("vin_text", None, None),
    (1, 9): ("outside_temperature", "°C", None),             # was coolant_temp
    (1, 10): ("lightsense_night", None, None),               # was engine_running
    (1, 11): ("wiping_water_empty", None, None),             # was door_driver (washer fluid low)
    (1, 12): ("door_driver", None, None),                    # was door_passenger
    (1, 13): ("door_entrance", None, None),                  # was door_sliding (habitation entrance)
    (1, 14): ("motor_oil_warning", None, None),              # was door_rear
    (1, 15): ("ignition_state", None, None),
    (1, 16): ("engine_running", None, None),                 # was seatbelt_warning
    (1, 17): ("cooling_water_empty", None, None),            # was turn_signal
    (1, 18): ("parking_brake_engaged", None, None),          # was headlamp
    (1, 19): ("standheizung_available", None, None),         # was parking_light
    (1, 20): ("standheizung_state", None, None),             # was fog_front
    (1, 21): ("cruise_control_active", None, None),          # was fog_rear
    (1, 22): ("downhill_assist_active", None, None),         # was high_beam
    (1, 23): ("language_setting", None, None),               # was language
    # Bus 3 — CBE EBL402 habitation electrics panel.
    # Author's earlier labels didn't match the underlying slots on the S700:
    # (3, 3) "charger_active" is actually the SwitchPump (hence the switch
    # platform's water_pump write target has always been bus 3 sensor 3);
    # (3, 5-7) distinguishes living vs starter battery; (3, 10) labelled
    # "battery_soc %" is living battery capacity in Ah, not SoC%;
    # (3, 19) marked sentinel is the EBL outdoor temperature sensor;
    # (3, 20-21) labelled solar_* actually drive tank-refill behaviour;
    # (3, 22) labelled switch_22 is the ShoreLineConnected flag.
    # Slots 8/9 (FreshWaterLevel/WasteWaterLevel per registry) are NOT
    # relabelled here — on the S700 water is reported from bus 22/25, and
    # v2.9.2+ already handles that correctly with the invert100 transform.
    (3, 1): ("main_switch", None, None),                        # 12VSupply
    (3, 2): ("power_source", None, None),                       # Registry: ShoreLine — kept as power_source (tested, meaningful)
    (3, 3): ("water_pump", None, None),                         # was charger_active (SwitchPump)
    (3, 4): ("charge_phase", None, None),                       # Registry: ChargeMode — kept as charge_phase
    (3, 5): ("living_battery_voltage", "V", None),              # was battery_voltage
    (3, 6): ("living_battery_current", "A", None),              # was battery_current
    (3, 7): ("starter_battery_voltage", "V", None),             # was chassis_battery_voltage
    (3, 8): ("light_1_level", "%", None),                       # kept for backward compat (not water on this bus)
    (3, 9): ("light_2_level", "%", None),                       # kept for backward compat (not water on this bus)
    (3, 10): ("living_battery_capacity", "Ah", None),           # was battery_soc % — unit was wrong
    (3, 11): ("battery_type", None, None),                      # Registry: LivingBatteryType — kept as battery_type
    (3, 12): ("fresh_water_sensor_failure", None, None),        # was switch_12v_1
    (3, 13): ("waste_water_sensor_failure", None, None),        # was switch_12v_2
    (3, 14): ("outside_temp_sensor_failure", None, None),       # was switch_12v_3
    (3, 15): ("outside_temp_calib_failure", None, None),        # was switch_12v_4
    (3, 16): ("ebl_over_temperature", None, None),              # was switch_12v_5
    (3, 17): ("battery_keeper_active", None, None),             # was switch_12v_6
    (3, 18): ("d_plus_state", None, None),                      # was switch_12v_7
    (3, 19): ("ebl_outdoor_temp_sensor", "°C", None),           # was solar_voltage_sentinel (unit is °C not V)
    (3, 20): ("activate_tank_refill_interval", None, None),     # was solar_connected
    (3, 21): ("update_tank_level_immediately", None, None),     # was solar_charger_status
    (3, 22): ("shoreline_connected", None, None),               # was switch_22 (ShoreLineConnected)
    # Light: Schlafzimmer Ambientebeleuchtung / Bedroom ambient (bus 15)
    # sid=1: on/off, sid=2: brightness (WRITE only), sid=3: color_temp
    (15, 1): ("light_bedroom_ambient", None, None),
    (15, 2): ("light_bedroom_ambient_brightness", "%", None),
    (15, 3): ("light_bedroom_ambient_color_temp", None, None),
    # Light: Badezimmer Deckenbeleuchtung / Bathroom ceiling (bus 19)
    (19, 1): ("light_bathroom_ceiling", None, None),
    (19, 2): ("light_bathroom_ceiling_brightness", "%", None),
    # Bus 8 — Votronic MPP250Duo solar charger.
    # Author's labels had (8,1) as gray_water_sensor and (8,4-7) as
    # vent_* / tire_pressure which don't belong on this bus at all.
    # All seven slots are solar-charger signals per the registry.
    (8, 1): ("solar_active", None, None),             # was gray_water_sensor
    (8, 2): ("solar_voltage", "V", None),             # SolarPanelVoltage
    (8, 3): ("solar_current", "A", None),             # ChargingCurrent
    (8, 4): ("solar_error", None, None),              # was vent_1 (Error)
    (8, 5): ("solar_reduced_power", None, None),      # was vent_2 (ReducedPower)
    (8, 6): ("solar_aes_active", None, None),         # was vent_3 (AESActive)
    (8, 7): ("solar_power", "W", None),               # was tire_pressure/bar (SolarPanelPower W)
    # Light: Wohnraum Deckenbeleuchtung / Living room ceiling (bus 11)
    (11, 1): ("light_living_ceiling", None, None),
    (11, 2): ("light_living_ceiling_brightness", "%", None),
    # Light: Wohnraum Ambientebeleuchtung / Living room ambient (bus 12)
    (12, 1): ("light_living_ambient", None, None),
    (12, 2): ("light_living_ambient_brightness", "%", None),
    (12, 3): ("light_living_ambient_color_temp", None, None),
    # Bus 30 — ScuSignals (SCU platform: GPS, LTE, Bluetooth, chassis wake).
    # Author's labels treated all 14 slots as gps_*, but only (30,1)/(30,2)
    # are GPS related.  (30,3-7) are LTE/SCU telemetry and paired-BT counts;
    # (30,8-14) are chassis state flags including the WakeUpChassis command.
    (30, 1): ("gps_coordinates", None, None),           # GpsLocation (lat,lon string)
    (30, 2): ("scu_internal_time", None, None),         # was gps_utc_time
    (30, 3): ("lte_connection_quality", None, None),   # was gps_signal_quality
    (30, 4): ("lte_connection_state", None, None),     # was gps_fix
    (30, 5): ("scu_voltage", "V", None),                # was gps_altitude m (ScuVoltage V — different unit!)
    (30, 6): ("paired_bt_devices", None, None),        # was gps_satellites
    (30, 7): ("connected_bt_devices", None, None),     # was gps_heading °
    (30, 8): ("battery_cutoff_switch", None, None),    # was gps_sensor_8
    (30, 9): ("user_active", None, None),              # was gps_sensor_9
    (30, 10): ("d_plus", None, None),                  # was gps_sensor_10
    (30, 11): ("wake_up_chassis", None, None),         # was gps_sensor_11 (writable — wakes Mercedes CAN)
    (30, 12): ("battery_switch_active", None, None),   # was gps_sensor_12
    (30, 13): ("scu_shoreline_connected", None, None), # was gps_sensor_13
    (30, 14): ("vehicle_movement", None, None),        # was gps_sensor_14
    # Heating / Fridge control (34)
    # sid=1: fridge power (bool), sid=2: fridge ECO mode (bool),
    # sid=3: fridge cooling step (uint 1-5)
    (34, 1): ("fridge_power", None, None),
    (34, 2): ("fridge_eco", None, None),
    (34, 3): ("fridge_cooling_step", None, None),
    (34, 4): ("heat_ctrl_4", None, None),
    (34, 5): ("heat_ctrl_5", None, None),
    (34, 6): ("heat_ctrl_6", None, None),
    (34, 7): ("heat_setpoint_raw", None, "div1000"),
    # Light: Nachtlicht / Night light (bus 16)
    (16, 1): ("light_nightlight", None, None),
    (16, 2): ("light_nightlight_brightness", "%", None),
    # Light: Küchenbeleuchtung / Kitchen (bus 21)
    (21, 1): ("light_kitchen", None, None),
    (21, 2): ("light_kitchen_brightness", "%", None),
    (21, 3): ("light_kitchen_color_temp", None, None),
    # Water tanks — bus 22 = fresh water, bus 25 = grey water
    # Raw uint is inverted: 100 = empty (0%), 0 = full (100%)
    # Old releases showed both as 0-6% when empty — confirmed inverted scale
    (22, 1): ("fresh_water_sensor", None, None),
    (22, 2): ("fresh_water_level", "%", "invert100"),
    # Light: Außenbeleuchtung / Outside light (bus 24)
    (24, 1): ("light_outside", None, None),
    (24, 2): ("light_outside_brightness", "%", None),
    (24, 3): ("light_outside_color_temp", None, None),
    # Grey water (25)
    (25, 1): ("gray_water_sensor_ext", None, None),
    (25, 2): ("gray_water_level", "%", "invert100"),
    # Fridge (37)
    (37, 1): ("fridge_mode", None, None),
    (37, 2): ("fridge_status", None, None),
    # Light: Sitzgruppe Dachschrank / Seating area overhead (bus 43)
    (43, 1): ("light_seating_overhead", None, None),
    (43, 2): ("light_seating_overhead_brightness", "%", None),
    # Light: Schlafzimmer Dachschrank / Bedroom overhead (bus 44)
    (44, 1): ("light_bedroom_overhead", None, None),
    (44, 2): ("light_bedroom_overhead_brightness", "%", None),
    # SCU (45)
    (45, 8): ("scu_connected", None, None),
    (45, 9): ("scu_sensor_9", None, None),
    (45, 10): ("scu_sensor_10", None, None),
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
    (58, 10): ("heater_sensor_10", None, None),
    (58, 11): ("heater_operating_mode", None, None),
    (58, 12): ("heater_sensor_12", None, None),
    (58, 13): ("heater_sensor_13", None, None),
    (58, 14): ("heater_sensor_14", None, None),
    # Bus 99 — Lithium battery BMS (not "can2" extended chassis CAN).
    # Author's labels here were Mercedes CAN signal names that do not apply —
    # the S700's lithium pack reports BMS telemetry: BatteryVoltage,
    # BatteryCurrent, BatteryTemperature, StateOfCharge, TimeRemaining,
    # StateOfHealth, CapacityRemaining, RelativeCapacity, ChargeDetected,
    # DeviceFailure.  lithium_soc (slot 4) is retained as the canonical SoC.
    (99, 1): ("bms_battery_voltage", "V", None),        # was adblue_temp °C
    (99, 2): ("bms_battery_current", "A", None),        # was engine_torque %
    (99, 3): ("bms_battery_temperature", "°C", None),   # was ambient_temp (same °C, new meaning)
    (99, 4): ("lithium_soc", "%", None),                # BatteryStateOfCharge (kept)
    (99, 5): ("bms_time_remaining", "min", None),       # was fuel_range km
    (99, 6): ("bms_state_of_health", "%", None),        # was current_gear
    (99, 7): ("bms_capacity_remaining", "Ah", None),    # was total_fuel_used
    (99, 8): ("bms_relative_capacity", "%", None),      # was lithium_soc_2
    (99, 9): ("bms_charge_detected", None, None),       # was cruise_control
    (99, 10): ("bms_device_failure", None, None),       # was dpf_status
}

# Human-readable mappings for raw SCU string values.
# Entries for sensor names that no longer exist after the bus-1 relabel
# (door_passenger, door_sliding, door_rear, headlamp, fog_*, high_beam,
# parking_light, turn_signal) have been removed.
_VALUE_LABELS: dict[str, dict[str, str]] = {
    "door_driver": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
    "door_entrance": {"OFF": "Closed", "CLS": "Closed", "ON": "Open", "OPN": "Open", "SNA": "N/A"},
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
    "heater_fan_speed": {"OFF": "Off", "ECO": "Eco", "HOT": "Hot", "HIGH": "High"},
    "heater_state": {"False": "Off", "True": "On"},
}

# Integer-to-string label maps for sensors that report numeric codes.
# dpf_status removed (bus 99,10 is now bms_device_failure).
_INT_LABELS: dict[str, dict[int, str]] = {
    "fridge_mode": {0: "On", 1: "Eco", 2: "Boost", 8: "Off"},
    "fridge_status": {0: "Open", 1: "Closed"},
}

# Sentinel float values that indicate "sensor unavailable / not connected".
# The SCU stores 32768 (0x8000) as CAN "no data" — scaled to float as 3276.8.
_FLOAT_SENTINELS: set[float] = {3276.8, 32768.0, 65535.0, 6553.5}

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
        sid_val = next((v for fn, wt, v in fields if fn == 1 and wt == 0), 0)
        bus_val = next((v for fn, wt, v in fields if fn == 2 and wt == 0), 0)
        if sid_val < 1000 and bus_val < 1000 and depth <= 3:
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
                    # Map integer values to readable labels (fridge, etc.)
                    if isinstance(val, int) and name in _INT_LABELS:
                        val = _INT_LABELS[name].get(val, val)
                    sensors[name] = val
                else:
                    fallback = f"bus{entry['bus_id']}_s{entry['sensor_id']}"
                    sensors[fallback] = entry["value"]
            return

    # Not a sensor entry (or wrapper) — recurse into length-delimited sub-fields
    for fn, wt, v in fields:
        if wt == 2 and isinstance(v, bytes) and len(v) > 2:
            _extract_sensors_recursive(v, sensors, depth + 1)
