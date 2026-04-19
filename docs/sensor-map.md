# PIA Sensor Bus Map — Grand Canyon S 600 CrossOver

> **Vehicle:** HYMER Grand Canyon S 600 CrossOver (2025)
> **Base:** Mercedes Sprinter 316 CDI
> **SCU Firmware:** 1.12.0.0
> **Validated:** April 2026 via mitmproxy captures + live HA correlation

This document maps every known `(bus_id, sensor_id)` slot to its sensor name,
unit, and value transform as observed on the S600. Other models (e.g. the S700)
may have different slot assignments on buses 1, 3, 8, 30, and 99 — see the
[Compatibility section](../README.md#compatibility-with-other-vehicles) in the README.

## Bus 1 — VehicleSignal (Mercedes Sprinter chassis CAN)

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (1, 1) | `odometer` | km | div1000 | Lifetime odometer |
| (1, 2) | `speed` | km/h | — | Vehicle speed (⚠️ S700: fuel_level) |
| (1, 3) | `lock_status` | — | — | Vehicle locked/unlocked string |
| (1, 4) | `handbrake` | — | — | Parking brake (⚠️ S700: test_signal_write) |
| (1, 5) | `rpm` | rpm | div100 | Engine RPM (⚠️ S700: distance_to_service) |
| (1, 6) | `adblue_level` | % | — | AdBlue tank level |
| (1, 7) | `engine_hours` | h | div3600 | Engine runtime (⚠️ S700: adblue_remaining_distance) |
| (1, 8) | `vin_text` | — | — | VIN string |
| (1, 9) | `coolant_temp` | °C | — | ⚠️ Reads ~9°C parked — likely outside_temperature (same as S700) |
| (1, 10) | `engine_running` | — | — | Engine on/off (⚠️ S700: lightsense_night) |
| (1, 11) | `door_driver` | — | — | Driver door open/closed (⚠️ S700: wiping_water_empty) |
| (1, 12) | `door_passenger` | — | — | Passenger door (⚠️ S700: door_driver) |
| (1, 13) | `door_sliding` | — | — | Sliding door (⚠️ S700: door_entrance) |
| (1, 14) | `door_rear` | — | — | Rear door (⚠️ S700: motor_oil_warning) |
| (1, 15) | `ignition_state` | — | — | IGN_LOCK/OFF/ACC/ON/START |
| (1, 16) | `seatbelt_warning` | — | — | (⚠️ S700: engine_running) |
| (1, 17) | `turn_signal` | — | — | (⚠️ S700: cooling_water_empty) |
| (1, 18) | `headlamp` | — | — | (⚠️ S700: parking_brake_engaged) |
| (1, 19) | `parking_light` | — | — | (⚠️ S700: standheizung_available) |
| (1, 20) | `fog_front` | — | — | (⚠️ S700: standheizung_state) |
| (1, 21) | `fog_rear` | — | — | (⚠️ S700: cruise_control_active) |
| (1, 22) | `high_beam` | — | — | (⚠️ S700: downhill_assist_active) |
| (1, 23) | `language` | — | — | Dashboard language code |

## Bus 3 — CBE EBL402 (habitation electrics)

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (3, 1) | `main_switch` | — | — | 12V main switch state. Write: str "On"/"Off" |
| (3, 2) | `power_source` | — | — | "Battery / solar operated", "Mains" etc. |
| (3, 3) | `charger_active` | — | — | Shore charger active. Also water pump write target (bool) |
| (3, 4) | `charge_phase` | — | — | Bulk/Absorption/Float/Idle |
| (3, 5) | `battery_voltage` | V | — | Living battery voltage |
| (3, 6) | `battery_current` | A | — | Living battery current (negative = discharging) |
| (3, 7) | `chassis_battery_voltage` | V | — | Starter battery voltage |
| (3, 8) | `light_1_level` | % | — | (⚠️ S700: fresh_water_level) |
| (3, 9) | `light_2_level` | % | — | (⚠️ S700: gray_water_level) |
| (3, 10) | `battery_soc` | % | — | Battery state of charge (⚠️ S700: Ah capacity) |
| (3, 11) | `battery_type` | — | — | "AGM/Lithium" |
| (3, 12–18) | `switch_12v_1..7` | — | — | 12V switch channels |
| (3, 19) | `solar_voltage_sentinel` | V | — | Always 3276.8 (sentinel). Real solar on bus 8 |
| (3, 20) | `solar_connected` | — | — | Solar panel connected flag |
| (3, 21) | `solar_charger_status` | — | — | MPPT charger status |
| (3, 22) | `switch_22` | — | — | (⚠️ S700: shoreline_connected) |

## Bus 8 — Voltronic MPP260CI (solar charger)

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (8, 1) | `gray_water_sensor` | — | — | ⚠️ S700: solar_active |
| (8, 2) | `solar_voltage` | V | — | Panel voltage (confirmed via live correlation) |
| (8, 3) | `solar_current` | A | — | Charge current |
| (8, 4) | `vent_1` | — | — | ⚠️ S700: solar_error |
| (8, 5) | `vent_2` | — | — | ⚠️ S700: solar_reduced_power |
| (8, 6) | `vent_3` | — | — | ⚠️ S700: solar_aes_active |
| (8, 7) | `tire_pressure` | bar | — | ⚠️ S700: solar_power (W) |

## Bus 11 — Living ceiling light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (11, 1) | `light_living_ceiling` | — | On/off |
| (11, 2) | `light_living_ceiling_brightness` | % | Brightness |

## Bus 12 — Living ambient light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (12, 1) | `light_living_ambient` | — | On/off |
| (12, 2) | `light_living_ambient_brightness` | % | Brightness |
| (12, 3) | `light_living_ambient_color_temp` | — | Color temperature |

## Bus 15 — Bedroom ambient light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (15, 1) | `light_bedroom_ambient` | — | On/off |
| (15, 2) | `light_bedroom_ambient_brightness` | % | Brightness |
| (15, 3) | `light_bedroom_ambient_color_temp` | — | Color temperature |

## Bus 16 — Night light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (16, 1) | `light_nightlight` | — | On/off |
| (16, 2) | `light_nightlight_brightness` | % | Brightness |

## Bus 19 — Bathroom ceiling light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (19, 1) | `light_bathroom_ceiling` | — | On/off |
| (19, 2) | `light_bathroom_ceiling_brightness` | % | Brightness |

## Bus 21 — Kitchen light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (21, 1) | `light_kitchen` | — | On/off |
| (21, 2) | `light_kitchen_brightness` | % | Brightness |
| (21, 3) | `light_kitchen_color_temp` | — | Color temperature |

## Bus 22 — Fresh water

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (22, 1) | `fresh_water_sensor` | — | — | Raw sensor |
| (22, 2) | `fresh_water_level` | % | invert100 | 100=empty, 0=full (inverted) |

## Bus 24 — Outside light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (24, 1) | `light_outside` | — | On/off |
| (24, 2) | `light_outside_brightness` | % | Brightness |
| (24, 3) | `light_outside_color_temp` | — | Color temperature |

## Bus 25 — Grey water

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (25, 1) | `gray_water_sensor_ext` | — | — | Raw sensor |
| (25, 2) | `gray_water_level` | % | invert100 | 100=empty, 0=full (inverted) |

## Bus 30 — ScuSignals (GPS + SCU telemetry)

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (30, 1) | `gps_coordinates` | — | Lat,Lng string (shared S600/S700) |
| (30, 2) | `gps_utc_time` | — | SCU internal time (shared S600/S700) |
| (30, 3) | `gps_signal_quality` | — | ⚠️ S700: lte_connection_quality |
| (30, 4) | `gps_fix` | — | ⚠️ S700: lte_connection_state |
| (30, 5) | `gps_altitude` | m | ⚠️ S700: scu_voltage (V) |
| (30, 6) | `gps_satellites` | — | ⚠️ S700: paired_bt_devices |
| (30, 7) | `gps_heading` | ° | ⚠️ S700: connected_bt_devices |
| (30, 8–14) | `gps_sensor_8..14` | — | Unmapped SCU state flags |

## Bus 34 — Thetford N4112A fridge (shared S600/S700)

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (34, 1) | `fridge_power` | Power on/off (bool write) |
| (34, 2) | `fridge_eco` | ECO/quiet mode (bool write) |
| (34, 3) | `fridge_cooling_step` | Cooling step 1–5 (uint write) |
| (34, 4–7) | `heat_ctrl_4..7` | Heater control / fridge setpoint raw |

## Bus 37 — Vehicle info (metadata)

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (37, 1) | `fridge_mode` | ⚠️ Likely VehicleType (static metadata, not fridge) |
| (37, 2) | `fridge_status` | ⚠️ Likely VehicleBrand (static metadata) |

## Bus 43 — Seating overhead light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (43, 1) | `light_seating_overhead` | — | On/off |
| (43, 2) | `light_seating_overhead_brightness` | % | Brightness |

## Bus 44 — Bedroom overhead light

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (44, 1) | `light_bedroom_overhead` | — | On/off |
| (44, 2) | `light_bedroom_overhead_brightness` | % | Brightness |

## Bus 45 — SCU / LIM module

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (45, 8) | `scu_connected` | SCU connectivity flag |
| (45, 9) | `scu_sensor_9` | Unknown |
| (45, 10) | `scu_sensor_10` | Unknown |
| (45, 11) | `scu_firmware` | SCU firmware version string |

## Bus 49 — Truma / LIM module

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (49, 8) | `truma_connected` | Truma connectivity flag |
| (49, 10) | `truma_status` | Truma status code |
| (49, 11) | `truma_firmware` | Truma firmware version string |

## Bus 58 — Truma Combi D6E heater (shared S600/S700)

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (58, 4) | `heater_fuel_type` | — | Fuel type string (Diesel/Electric/Both) |
| (58, 5) | `heater_fan_speed` | — | Fan speed (Off/ECO/High) |
| (58, 6) | `heater_fuel_type_2` | — | Energy source selector write target |
| (58, 7) | `heater_state` | — | Heater on/off state |
| (58, 8) | `heater_setpoint` | °C | Target temperature (float write) |
| (58, 9) | `heater_electric_power` | W | Electric power (0/900/1800) |
| (58, 10) | `heater_sensor_10` | — | Unknown |
| (58, 11) | `heater_operating_mode` | — | Operating mode string |
| (58, 12–14) | `heater_sensor_12..14` | — | Unknown |

## Bus 99 — Extended CAN / BMS

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (99, 1) | `adblue_temp` | °C | — | ⚠️ S700: bms_battery_voltage (V) |
| (99, 2) | `engine_torque` | % | — | ⚠️ S700: bms_battery_current (A) |
| (99, 3) | `ambient_temp` | °C | — | ⚠️ S700: bms_battery_temperature (°C) |
| (99, 4) | `lithium_soc` | % | — | Battery SOC (shared S600/S700) |
| (99, 5) | `fuel_range` | km | — | ⚠️ S700: bms_time_remaining (min) |
| (99, 6) | `current_gear` | — | — | ⚠️ S700: bms_state_of_health (%) |
| (99, 7) | `total_fuel_used` | — | — | ⚠️ S700: bms_capacity_remaining (Ah) |
| (99, 8) | `lithium_soc_2` | % | — | ⚠️ S700: bms_relative_capacity (%) |
| (99, 9) | `cruise_control` | — | — | ⚠️ S700: bms_charge_detected |
| (99, 10) | `dpf_status` | — | — | 0=Normal, 1=Regeneration. ⚠️ S700: bms_device_failure |

## Value Transforms

| Transform | Description |
|-----------|-------------|
| `div10` | Divide raw value by 10 |
| `div100` | Divide raw value by 100 |
| `div1000` | Divide raw value by 1000 |
| `div3600` | Convert seconds to hours |
| `invert100` | `100 - value` (inverted percentage) |

## S700 Conflicts Legend

Slots marked with ⚠️ have **different meanings on the Grand Canyon S700**.
See [PR #44](https://github.com/BetaHydri/hymer-connect-ha/pull/44) for the
S700 observations. A model-aware sensor map is planned to support both models
without conflicts.
