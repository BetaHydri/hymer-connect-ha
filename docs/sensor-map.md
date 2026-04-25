# PIA Sensor Bus Map — Grand Canyon S 600 CrossOver

> **Vehicle:** HYMER Grand Canyon S 600 CrossOver (2025)
> **Base:** Mercedes Sprinter 419 CDI
> **SCU Firmware:** 1.12.0.0
> **Validated:** April 2026 via mitmproxy captures + live HA correlation
> **Discovery scan:** 2026-04-23 — 129 sensors, 129 mapped, 0 unmapped. Vehicle-verified at Unterföhring.

This document maps every known `(bus_id, sensor_id)` slot to its sensor name,
unit, and value transform as observed on the S600. Other models (e.g. the S700)
may have different slot assignments on buses 1, 3, 8, 30, and 99 — see the
[Compatibility section](../README.md#compatibility-with-other-vehicles) in the README.

## Bus 1 — VehicleSignal (Mercedes Sprinter chassis CAN)

| Slot | Sensor Name | Unit | Transform | Notes |
|------|------------|------|-----------|-------|
| (1, 1) | `odometer` | km | div1000 | Lifetime odometer |
| (1, 2) | `fuel_level` | % | — | Diesel fuel level (confirmed: EHG app 73% = sensor 72.72) |
| (1, 3) | `lock_status` | — | — | Vehicle locked/unlocked string |
| (1, 4) | `handbrake` | — | — | Handbrake state |
| (1, 5) | `distance_to_service` | km | div100 | km to next service interval (was: rpm) |
| (1, 6) | `adblue_level` | % | — | AdBlue tank level |
| (1, 7) | `engine_hours` | h | div3600 | Engine runtime |
| (1, 8) | `vin_text` | — | — | VIN string |
| (1, 9) | `outside_temperature` | °C | — | Mercedes outside temperature sensor (bumper-mounted). Confirmed 2026-04-20: read 13°C → 16°C tracking real ambient weather in Unterföhring. Same value as Mercedes cockpit "Außentemperatur" display. |
| (1, 10) | `engine_running` | — | — | Engine on/off |
| (1, 11) | `wiping_water_empty` | — | — | Washer fluid low warning (per S700 PR #44; was door_sliding — never updated on S600) |
| (1, 12) | `door_driver` | — | — | Driver door (confirmed at vehicle 2026-04-20, re-confirmed 2026-04-23). MB API: `doorstatusfrontleft` |
| (1, 13) | `door_passenger` | — | — | Passenger door (confirmed at vehicle 2026-04-20, re-confirmed 2026-04-23). MB API: `doorstatusfrontright` |
| (1, 14) | `motor_oil_warning` | — | — | Shows "SNA" (Sensor Not Available) on S600. Per S700 PR #44: engine oil warning. Not a door — confirmed 2026-04-23. Sliding/rear doors only via MB API (`doorstatusrearright`, `decklidstatus`). |
| (1, 15) | `ignition_state` | — | — | IGN_LOCK/OFF/ACC/ON/START |
| (1, 16) | `seatbelt_warning` | — | — | Seatbelt warning |
| (1, 17) | `coolant_warning` | — | — | Coolant low warning (was: turn_signal) |
| (1, 18) | `parking_brake` | — | — | Parking brake engaged (was: headlamp — confirmed by "ON" while parked) |
| (1, 19) | `standheizung_available` | — | — | Auxiliary heater fitted (was: parking_light) |
| (1, 20) | `standheizung_state` | — | — | Auxiliary heater on/off (was: fog_front) |
| (1, 21) | `cruise_control_can` | — | — | Cruise control active (was: fog_rear) |
| (1, 22) | `downhill_assist` | — | — | Downhill assist active (was: high_beam) |
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
| (3, 8) | `fresh_water_level_ebl` | % | — | **Fresh water level** from EBL402 tank input (per S700 PR #44). Discovery: `0` with empty tank. |
| (3, 9) | `grey_water_level_ebl` | % | — | **Grey water level** from EBL402 tank input (per S700 PR #44). Discovery: `0` with empty tank. |
| (3, 10) | `battery_soc` | % | — | Battery state of charge. Discovery: 95%. (⚠️ S700: Ah capacity, not %) |
| (3, 11) | `battery_type` | — | — | "AGM/Lithium" |
| (3, 12–18) | `switch_12v_1..7` | — | — | 12V switch channels |
| (3, 19) | `solar_voltage_sentinel` | V | — | Always 3276.8 (sentinel). Real solar on bus 8 |
| (3, 20) | `solar_connected` | — | — | Solar panel connected. Discovery: `1` (int, not bool) |
| (3, 21) | `solar_charger_status` | — | — | MPPT charger status. Discovery: `1` (int) |
| (3, 22) | `shoreline_connected` | — | — | Shore power connected. Discovery: `False` (bool) |

## Bus 8 — Voltronic MPP260CI (MPPT solar charger)

All 7 slots are solar charger data. Some code labels in `pia_decoder.py` still
carry legacy names from an earlier S700-based sensor map where bus 8 was the
grey water / ventilation bus. The actual sensor values are from the Voltronic
MPPT charger. Solar power is computed as `voltage × current` instead of reading
the raw slot (8, 7) directly.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (8, 1) | `solar_active` | — | MPPT "charging active" flag. Computed from `solar_current > 0`. Legacy code label: `gray_water_sensor` |
| (8, 2) | `solar_voltage` | V | Panel voltage — confirmed 19.9V live |
| (8, 3) | `solar_current` | A | Charge current — confirmed 2.1A live |
| (8, 4) | `solar_error` | — | MPPT error flag. Legacy code label: `vent_1` |
| (8, 5) | `solar_reduced_power` | — | MPPT reduced power flag. Legacy code label: `vent_2` |
| (8, 6) | `solar_aes_active` | — | MPPT AES mode flag. Legacy code label: `vent_3` |
| (8, 7) | `solar_power` | W | MPPT power output. Computed as V×I instead. Legacy code label: `tire_pressure` |

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

## Bus 22 — Outside LED bar (confirmed at vehicle 2026-04-23)

Previously labelled as fresh water tank. Confirmed at vehicle 2026-04-23: both water tanks were empty but bus 22 showed 88%, matching LED bar brightness on bus 25. Bus 22 is the outside LED bar — same physical light as bus 25 (separate SCU component registration). Sensor entities disabled by default (bus 25 is the primary control channel).

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (22, 1) | `light_led_bar_2` | — | On/off (duplicate of bus 25) |
| (22, 2) | `light_led_bar_2_brightness` | % | Brightness (tracks bus 25 LED bar) |

## Bus 24 — All Wohnen light group

Sending (24,1)=true toggles all living area lights (ceiling, ambient, kitchen, seating). **NOT an individual outside light** — verified 2026-04-22: toggling activates all Wohnen lights.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (24, 1) | `light_wohnen_group` | — | On/off. Toggles all Wohnen lights |
| (24, 2) | `light_wohnen_group_brightness` | % | Group brightness (sentinel: 10000 when off) |
| (24, 3) | `light_wohnen_group_color_temp` | — | Group color temperature context |

## Bus 25 — Outside LED bar (confirmed via mitmproxy 2026-04-22)

Previously mislabelled as grey water. Mitmproxy capture confirmed the EHG app sends on/off + brightness commands to bus 25 when toggling the LED bar. Issue #46 resolved.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (25, 1) | `light_led_bar` | — | On/off (bool) |
| (25, 2) | `light_led_bar_brightness` | % | Brightness (0-100) |

## Bus 27 — All Privat light group (discovered 2026-04-22)

Discovered by `tools/discover_sensors.py`. Same structure as Bus 24 (All Wohnen group). Sending (27,1)=true toggles all bedroom/bath lights. **NOT the outside LED bar** — verified by user: toggling (27,1) activates all private area lights.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (27, 1) | `light_privat_group` | — | On/off (bool). Toggles all Privat lights |
| (27, 2) | `light_privat_group_brightness` | % | Group brightness (sentinel: 10000 when off) |
| (27, 3) | `light_privat_group_color_temp` | — | Group color temperature context |

## Bus 30 — ScuSignals (GPS + SCU telemetry)

Slots 1-2 are shared across S600/S700. Slots 3-7 carry GPS data on the S600
(confirmed via live traces 2026-04-19) but LTE/BT telemetry on the S700.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (30, 1) | `gps_coordinates` | — | Lat,Lng string (shared S600/S700) |
| (30, 2) | `gps_utc_time` | — | SCU internal time (shared S600/S700) |
| (30, 3) | `gps_signal_quality` | — | Confirmed "excellent" on S600. S700: `lte_connection_quality` |
| (30, 4) | `gps_fix` | — | Confirmed `true` on S600. S700: `lte_connection_state` |
| (30, 5) | `gps_altitude` | m | Confirmed 13.1m on S600. S700: `scu_voltage` (V) |
| (30, 6) | `gps_satellites` | — | Confirmed 3 on S600. S700: `paired_bt_devices` |
| (30, 7) | `gps_heading` | ° | Confirmed 0° on S600. S700: `connected_bt_devices` |
| (30, 8) | `scu_flag_1` | — | `False` — unknown flag |
| (30, 9) | `lte_connected` | — | `True` — LTE connection state |
| (30, 10) | `scu_flag_2` | — | `False` — unknown flag |
| (30, 11) | `paired_bt_devices` | — | `3` — BT paired device count (confirmed) |
| (30, 12) | `scu_flag_5` | — | `True` — unknown flag |
| (30, 13) | `scu_flag_3` | — | `False` — unknown flag |
| (30, 14) | `scu_flag_4` | — | `False` — unknown flag |

## Bus 34 — Thetford N4112A fridge (shared S600/S700)

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (34, 1) | `fridge_power` | Power on/off (bool write). Discovery: `False` |
| (34, 2) | `fridge_eco` | ECO/quiet mode (bool write). Discovery: `False` |
| (34, 3) | `fridge_cooling_step` | Cooling step 1–5 (uint write). Discovery: `2` |
| (34, 4) | `heat_ctrl_4` | Heater control value. Discovery: `0` (int) |
| (34, 5) | `heat_ctrl_5` | Heater control flag. Discovery: `False` (bool) |
| (34, 6) | `heat_ctrl_6` | Heater control value. Discovery: `0` (int) |
| (34, 7) | `heat_setpoint_raw` | Fridge setpoint raw (div1000). Discovery: `13.0` |

## Bus 37 — Fridge status

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (37, 1) | `fridge_mode` | Fridge operating mode. Discovery: `Off` (string) |
| (37, 2) | `fridge_status` | Fridge door state. SCU reports int 0=Open, 1=Closed. Exposed as `binary_sensor.hymer_fridge_door` (v2.32.0). Real-time push updates arrive at protobuf depth 4 — fixed in v2.36.6. |

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
| (45, 8) | `scu_connected` | SCU connectivity flag. Discovery: `True` |
| (45, 9) | `scu_sensor_9` | Discovery: `False` (bool) |
| (45, 10) | `scu_sensor_10` | Discovery: `False` (bool) |
| (45, 11) | `scu_firmware` | SCU firmware version string. Discovery: `1.12.0.0` |

## Bus 49 — Truma / LIM module

| Slot | Sensor Name | Notes |
|------|------------|-------|
| (49, 8) | `truma_connected` | Truma connectivity flag |
| (49, 10) | `truma_status` | Truma status code |
| (49, 11) | `truma_firmware` | Truma firmware version string |

## Bus 58 — Truma Combi D6E heater (shared S600/S700)

EHG canonical name in parentheses where the local sensor key is a legacy
misnomer kept for backwards-compatibility with existing dashboards/history.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (58, 4) | `heater_fuel_type` (EHG: `heater_air_energy_source`) | — | Heater air energy source string (Gas/Electric/Mix). `rw` |
| (58, 5) | `heater_fan_speed` (EHG: `water_heater_mode`) | — | **Boiler** mode (Off/ECO/HOT). The legacy `heater_fan_speed` name is misleading — this is the water-heater (boiler) mode, not the heater fan. The Truma fan power (Eco/High) is **not** exposed on the SCU bus and remains panel-only. `rw` |
| (58, 6) | `heater_fuel_type_2` (EHG: `heater_water_energy_source`) | — | Water heater energy source. `rw` |
| (58, 7) | `heater_state` (EHG: `panel_busy`) | — | Panel-busy flag (bool). `r` |
| (58, 8) | `heater_setpoint` (EHG: `target_air_temperature`) | °C | Target air temperature, float write, range -273…30. `rw` |
| (58, 9) | `heater_electric_power` (EHG: `power_limit`) | W | Electric heating element power (0/900/1800). `rw` |
| (58, 10) | `heater_combi_error` (EHG: `combi_error`) | — | Combi error flag (bool). `r` |
| (58, 11) | `heater_operating_mode` (EHG: `heater_air_mode`) | — | Heater air mode string (`OFF` / `Normal` / `Automatic`). Read-only in practice — SCU silently rolls back writes. `rw` per metadata |
| (58, 12) | `heater_response_error` (EHG: `response_error`) | — | Response error flag (bool). `r` |
| (58, 13) | `heater_shoreline_connected` (EHG: `shoreline_connected`) | — | Shoreline connected flag (bool). `r` |
| (58, 14) | `heater_window_switch_closed` (EHG: `window_switch_closed`) | — | Window contact closed (diesel safety interlock, bool). `r` |

## Bus 99 — BOS LUX LiFePO4 BMS (4×80Ah)

On the S600, bus 99 carries extended CAN data (AdBlue, ambient temp, fuel range,
gear). On the S700, the same bus carries LiFePO4 BMS data. The sensor names
below reflect the S700 BMS layout. Legacy S600 code labels are noted where
they differ.

| Slot | Sensor Name | Unit | Notes |
|------|------------|------|-------|
| (99, 1) | `bms_voltage` | V | BMS pack voltage. Legacy code label: `adblue_temp` |
| (99, 2) | `bms_current` | A | BMS current, negative = discharging. Legacy code label: `engine_torque` |
| (99, 3) | `bms_temperature` | °C | Pack cell temperature. Legacy code label: `ambient_temp` |
| (99, 4) | `lithium_soc` | % | Battery SOC (shared S600/S700) |
| (99, 5) | `bms_time_remaining` | min | Estimated runtime. Legacy code label: `fuel_range` |
| (99, 6) | `bms_state_of_health` | % | Battery SoH. Legacy code label: `current_gear` |
| (99, 7) | `bms_capacity_remaining` | Ah | Remaining capacity. Legacy code label: `total_fuel_used` |
| (99, 8) | `lithium_soc_2` | % | Relative capacity |
| (99, 9) | `bms_charge_detected` | — | Charge active flag. Legacy code label: `cruise_control` |
| (99, 10) | `bms_device_failure` | — | BMS error flag. Legacy code label: `dpf_status` |

## Value Transforms

| Transform | Description |
|-----------|-------------|
| `div10` | Divide raw value by 10 |
| `div100` | Divide raw value by 100 |
| `div1000` | Divide raw value by 1000 |
| `div3600` | Convert seconds to hours |
| `invert100` | `100 - value` (inverted percentage) |

## Power Flow — Understanding the Three Current Sensors

The S600 reports current from three independent measurement points:

```
Solar Panel (19V)
      │
      ▼
┌─────────────┐
│  Voltronic  │  solar_current (bus 8)  → raw panel output
│  MPPT 260CI │  e.g. 2.1 A @ 19.4V = 40.7W
└──────┬──────┘
       │  MPPT converts to battery voltage
       ▼
┌─────────────┐
│  BOS LUX    │  bms_current (bus 99)   → net flow at battery
│  LiFePO4 BMS│  positive = charging, negative = discharging
│  4×80Ah     │  e.g. +1.54 A (net charge into cells)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  CBE EBL402 │  battery_current (bus 3) → habitation load draw
│  Habitation │  negative = consuming power
│  Controller │  e.g. -0.37 A (SCU, fridge ECU, standby loads)
└─────────────┘
```

**Key relationships:**

- **Solar current** is measured at the panel side (higher voltage, lower
  current). After MPPT conversion the power stays the same but current
  increases at the lower battery voltage.
- **BMS current** is the net result: solar input minus habitation load.
  Positive means the battery is charging.
- **Battery current** (EBL) shows what the habitation system draws.
  This is always negative when loads are connected, even while solar is
  charging — it measures downstream of the battery, not the net flow.

A negative habitation current while BMS current is positive is normal —
the solar more than compensates for the load.

## Computed Fuel Sensors (v2.29.0)

These sensors are **not** read from a CAN bus slot. They are computed by the
coordinator from `(1,1) odometer` and `(1,2) fuel_level` plus the configured
diesel tank capacity (default: 93 L for Sprinter 419/519 CDI).

| Sensor | Unit | Description |
|--------|------|-------------|
| `fuel_level_liters` | L | `fuel_level_% × tank_capacity / 100` |
| `fuel_consumption` | L/100km | Trip-based: `(fuel_used_L / distance_km) × 100` |
| `fuel_range_estimated` | km | `fuel_liters / consumption_L100 × 100` |

**Trip tracking logic:**
- A reference point (odometer + fuel %) is stored on first reading
- Consumption is only computed after ≥ 5 km driven (noise filter)
- Refueling auto-detected when fuel level increases > 5% → trip resets
- Sanity bounds: only values between 2–60 L/100km are accepted

**Tank capacity configuration:**
Settings → Integrations → HYMER Connect → Configure → "Diesel tank capacity"
Range: 30–200 L. Common Sprinter values: 71 L (314/316 CDI), 93 L (419/519 CDI standard).

## S700 Conflicts Legend

Slots marked with ⚠️ have **different meanings on the Grand Canyon S700**.
See [PR #44](https://github.com/BetaHydri/hymer-connect-ha/pull/44) for the
S700 observations. A model-aware sensor map is planned to support both models
without conflicts.

## Bus 121 — Victron MultiPlus 12/1600/70 (inverter/charger) — NON-FUNCTIONAL

From EHG app metadata extraction (Dan, April 2026). SCU component 121 = VictronMultiplus.
**No data received** on S600 — even with Victron physically switched ON and entities
manually enabled. The Victron MultiPlus communicates via **VE.Bus** protocol, which
is apparently not bridged to the SCU's PIA bus on the S600. The slot definitions
exist in the EHG app metadata (suggesting EHG planned or has support on some
vehicle configurations).

**Hypothesis:** Vehicles equipped with a **Victron Cerbo GX** (or similar GX device)
may populate bus 121. The Cerbo acts as a protocol bridge (VE.Bus → CAN) and could
feed Victron data to the SCU via CAN bus, which the SCU then exposes as PIA slots.
The S600 does not have a Cerbo — only the bare MultiPlus 12/1600/70 wired directly
via VE.Bus. Higher-spec models (e.g. MLT 580 4×4, B-Klasse ModernComfort) that
ship with a Cerbo GX from the factory may see data on this bus.

All entities disabled by default.

| Slot | Sensor Name | R/W | Type | Notes |
|------|------------|-----|------|-------|
| (121, 1) | `victron_inverter_on` | rw | bool | Inverter power on/off |
| (121, 2) | `victron_inverter_state` | r | int | Inverter state code |
| (121, 3) | `victron_inverter_l1_voltage` | r | V | Inverter L1 output voltage |
| (121, 4) | `victron_inverter_l1_current` | r | A | Inverter L1 output current |
| (121, 5) | `victron_inverter_l1_frequency` | r | Hz | Inverter L1 output frequency |
| (121, 6) | `victron_inverter_l2_voltage` | r | V | Inverter L2 output voltage |
| (121, 7) | `victron_inverter_l2_current` | r | A | Inverter L2 output current |
| (121, 8) | `victron_inverter_l2_frequency` | r | Hz | Inverter L2 output frequency |
| (121, 9) | `victron_charger_on` | rw | bool | Charger power on/off |
| (121, 10) | `victron_charger_state` | r | — | Charger state |
| (121, 11) | `victron_charge_voltage` | r | V | Charge output voltage |
| (121, 12) | `victron_charge_current` | r | A | Charge output current |
| (121, 13) | `victron_max_charge_current` | rw | A | Maximum charge current limit |
| (121, 14) | `victron_input_current_limit` | rw | A | Shore power input current limit |
| (121, 15) | `victron_input_voltage` | r | V | Shore power input voltage |
| (121, 16) | `victron_input_current` | r | A | Shore power input current |
| (121, 17) | `victron_input_frequency` | r | Hz | Shore power input frequency |
| (121, 18) | `victron_device_failure` | r | — | Device failure status |
| (121, 19) | `victron_firmware` | r | — | Firmware version string |
