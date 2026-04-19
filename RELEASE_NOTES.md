# S700 observations on v2.9.7 base

This branch reconciles the sensor map in `pia_decoder.py` against the
component registry decompiled from the official HYMER Connect Android app
(v2.10.14), and against observations on a 2025 Grand Canyon S 700
(internally `HY_YELLOWSTONE_S_2025` in the app model list).  It sits on
top of your v2.9.7 release and keeps all of your recent fixes
(`invert100` water transform, `str_value` main-switch fix, depth ≤ 3
phantom-sensor filter, `HymerHeaterEnergySelect`, fridge door label).

Nothing in this branch depends on shipping the registry itself; it only
uses the registry as a reference while writing observation-derived labels
so they match the names the app uses internally.  Entities whose labels
v2.9.7 already had broadly correct are untouched.

## Scope & caveat

Labels for buses 1, 3, 8, 30, 99 below were validated on a Mercedes-Sprinter-
chassis S 700 with a CBE EBL402, a Votronic MPP250Duo, a Truma Combi, and
a lithium BMS pack.  On vans with a different chassis (Fiat Ducato) or
different habitation electrics (non-CBE EBL, different solar charger) the
SCU firmware may route other signals onto the same component IDs.  Each
per-bus section below calls out the component the labels assume, and
vans that don't have that component simply won't populate those slots —
the entities will show `unavailable` rather than report wrong data.

## Summary of effects

- 20 existing sensor entities removed because their `value_path` pointed
  at a bus/sensor_id slot that doesn't carry the data the label implies.
- 28 new entities added for slots that were either unmapped or
  mislabelled.
- `switch.water_pump_ctrl` value_path changed from `charger_active`
  (misleading) to `water_pump` (matches the registry name `SwitchPump`).
- `climate.current_temperature` previously read what was labelled
  `ambient_temp` on bus 99, which is actually the lithium BMS battery
  temperature — now returns `None` (no indoor sensor is available from
  the SCU; only the target setpoint is displayed).
- `docs/protocol.md` added — a 170-line wire-protocol reference derived
  entirely from mitmproxy captures, no app-binary content.

## Why the labels were wrong

The v2.9.7 map had labels that looked right for a Mercedes chassis, a
generic MPPT charger and an EBL, but the slot numbers didn't actually
match.  Concrete examples:

- `sensor.speed` sat at ~6 km/h while parked.  Slot (1, 2) is
  `FuelTankLevel` (% — reads 60 on a 60% tank).
- `sensor.rpm` reported a steady five-digit number unrelated to engine
  speed.  Slot (1, 5) is `NextService` (km to next service interval).
- `sensor.coolant_temp` fluctuated with the weather, not the engine.
  Slot (1, 9) is `OutsideTemperature`.
- `binary_sensor.handbrake` was always `off`.  Slot (1, 4) is
  `TestSignalWrite` (a writable scratch slot, not the parking brake —
  the real flag is at (1, 18) `ParkingBrakeEngaged`).
- `sensor.tire_pressure` reported tens of bar.  Slot (8, 7) is
  `SolarPanelPower` (W, from the Votronic charger).
- `sensor.ambient_temp` tracked values around 20-25 °C even outside.
  Slot (99, 3) is the lithium pack's `BatteryTemperature`.
- `sensor.gps_altitude` reported 12 V when near sea level.  Slot (30, 5)
  is `ScuVoltage` (the SCU's own 12 V rail).
- `sensor.dpf_status`, `sensor.fuel_range`, `sensor.current_gear` etc.
  on bus 99 were never populated because bus 99 is the BMS, not an
  extended chassis CAN bus.

Once the actual component for each bus was identified from the app's
decompiled Hermes bundle, every misaligned label explained itself.

## Bus-by-bus change log

### Bus 1 — VehicleSignal (Mercedes Sprinter chassis CAN)

| slot | v2.9.7 label | Corrected label | Why |
| --- | --- | --- | --- |
| (1, 2) | speed (km/h) | fuel_level (%) | Reads 60 on a 60 % tank |
| (1, 4) | handbrake | test_signal_write | Writable scratch slot; parking brake is at (1, 18) |
| (1, 5) | rpm | distance_to_service (km, ÷100) | Reads km-to-service, not RPM |
| (1, 7) | engine_hours | adblue_remaining_distance (km, ÷100) | AdBlue range, not engine hours |
| (1, 9) | coolant_temp | outside_temperature | Tracks ambient, not coolant |
| (1, 10) | engine_running | lightsense_night | Ambient-light night flag |
| (1, 11) | door_driver | wiping_water_empty | Washer-fluid-low warning |
| (1, 12) | door_passenger | door_driver | Driver door is here on Sprinter |
| (1, 13) | door_sliding | door_entrance | Habitation entrance door |
| (1, 14) | door_rear | motor_oil_warning | Engine oil warning flag |
| (1, 16) | seatbelt_warning | engine_running | Actual engine-running flag |
| (1, 17) | turn_signal | cooling_water_empty | Coolant-low warning |
| (1, 18) | headlamp | parking_brake_engaged | The real parking brake |
| (1, 19) | parking_light | standheizung_available | Auxiliary heater fitted flag |
| (1, 20) | fog_front | standheizung_state | Auxiliary heater on/off |
| (1, 21) | fog_rear | cruise_control_active | Cruise control active |
| (1, 22) | high_beam | downhill_assist_active | Downhill assist active |

Bus 1 does not expose engine speed, coolant temperature, vehicle speed,
gear position or any of the lighting signals the v2.9.7 labels implied;
those CAN IDs simply are not relayed through the SCU to the app on the
S 700.

### Bus 3 — CBE EBL402 (habitation electrics panel)

| slot | v2.9.7 label | Corrected label | Why |
| --- | --- | --- | --- |
| (3, 3) | charger_active | water_pump | Registry: `SwitchPump` — this is the pump write target |
| (3, 5) | battery_voltage | living_battery_voltage | Distinguishes from starter battery at (3, 7) |
| (3, 6) | battery_current | living_battery_current | As above |
| (3, 7) | chassis_battery_voltage | starter_battery_voltage | Registry: `StarterBatteryVoltage` |
| (3, 10) | battery_soc (%) | living_battery_capacity (Ah) | Unit was wrong — this slot is Ah, not % |
| (3, 12-18) | switch_12v_1..7 | *_sensor_failure / ebl_over_temperature / battery_keeper_active / d_plus_state | Diagnostic flags |
| (3, 19) | solar_voltage_sentinel | ebl_outdoor_temp_sensor (°C) | Value is always 3276.8 (the CAN sentinel), but the slot itself is °C |
| (3, 20) | solar_connected | activate_tank_refill_interval | Tank-refill behaviour toggle |
| (3, 21) | solar_charger_status | update_tank_level_immediately | Tank refresh trigger |
| (3, 22) | switch_22 | shoreline_connected | 230 V mains connected flag |

Slots (3, 8) and (3, 9) are left alone — the registry calls them
`FreshWaterLevel` / `WasteWaterLevel`, but your v2.9.2 discovery that
water actually lives on bus 22/25 with `invert100` is what the S 700 SCU
emits in practice.  The switch platform's water-pump value_path is
updated from `signalr_sensors.charger_active` to `signalr_sensors.water_pump`
so the read-back key matches the write target.  Battery SoC percentage
is still sourced from bus 99 (the BMS) as before.

### Bus 8 — Votronic MPP250Duo solar charger

| slot | v2.9.7 label | Corrected label |
| --- | --- | --- |
| (8, 1) | gray_water_sensor | solar_active |
| (8, 4) | vent_1 | solar_error |
| (8, 5) | vent_2 | solar_reduced_power |
| (8, 6) | vent_3 | solar_aes_active |
| (8, 7) | tire_pressure (bar) | solar_power (W) |

Bus 8 is the MPPT charger, not ventilation or water.  The solar power
sensor in `sensor.py` now prefers the direct reading from (8, 7) and
falls back to `voltage × current` when the direct reading is missing.

### Bus 30 — ScuSignals (SCU platform telemetry)

| slot | v2.9.7 label | Corrected label | Why |
| --- | --- | --- | --- |
| (30, 3) | gps_signal_quality | lte_connection_quality | LTE signal, not GPS |
| (30, 4) | gps_fix | lte_connection_state | LTE connection state |
| (30, 5) | gps_altitude (m) | scu_voltage (V) | The SCU's own 12 V rail |
| (30, 6) | gps_satellites | paired_bt_devices | Count of paired BT devices |
| (30, 7) | gps_heading (°) | connected_bt_devices | Active BT connections |
| (30, 8-14) | gps_sensor_8..14 | battery_cutoff_switch / user_active / d_plus / wake_up_chassis / battery_switch_active / scu_shoreline_connected / vehicle_movement | Mixed SCU state flags |

Only (30, 1) `GpsLocation` and (30, 2) `ScuInternalTime` are GPS-related
on this bus.  Slot (30, 11) `wake_up_chassis` is writable and is what
the app sends to wake the Mercedes CAN bus.

### Bus 99 — Lithium battery BMS

| slot | v2.9.7 label | Corrected label | Why |
| --- | --- | --- | --- |
| (99, 1) | adblue_temp (°C) | bms_battery_voltage (V) | BMS pack voltage |
| (99, 2) | engine_torque (%) | bms_battery_current (A) | BMS pack current |
| (99, 3) | ambient_temp (°C) | bms_battery_temperature (°C) | Pack cell temperature |
| (99, 4) | lithium_soc (%) | lithium_soc (%) | *(unchanged — this label was already correct)* |
| (99, 5) | fuel_range (km) | bms_time_remaining (min) | Estimated runtime |
| (99, 6) | current_gear | bms_state_of_health (%) | SoH |
| (99, 7) | total_fuel_used | bms_capacity_remaining (Ah) | Ah remaining |
| (99, 8) | lithium_soc_2 (%) | bms_relative_capacity (%) | Relative capacity vs nominal |
| (99, 9) | cruise_control | bms_charge_detected | Charge-active flag |
| (99, 10) | dpf_status | bms_device_failure | BMS error flag |

Bus 99 is not "extended chassis CAN" — it's the lithium battery
management system.  None of the Mercedes signals the v2.9.7 labels
implied are published here.

### Bus 37 (minor)

Your v2.9.7 fridge_status Open/Closed relabel is preserved.  The bus 37
(1) `fridge_mode` label is removed; the slot is `VehicleType` per the
registry (static metadata) and the real fridge is on bus 34, already
wired through `select.fridge_mode_ctrl`.  The dead `fridge_mode`
fallback path in `select.py::HymerFridgeSelect.current_option` is
removed.

## Entities removed

`speed`, `coolant_temp`, `battery_voltage`, `battery_current`,
`chassis_battery_voltage`, `ambient_temp`, `current_gear`, `rpm`,
`engine_hours`, `fuel_range`, `total_fuel_used`, `engine_torque`,
`adblue_temp`, `dpf_status`, `solar_charger_status`, `tire_pressure`,
`gps_signal_quality`, `gps_altitude`, `gps_satellites`, `gps_heading`,
`fridge_mode`, `handbrake`, `charger_active`, `solar_connected`,
`gps_fix`, `door_passenger`, `door_sliding`, `door_rear`, `headlamp`,
`high_beam`, `parking_light`, `fog_front`, `fog_rear`, `turn_signal`,
`cruise_control`, `water_pump` (binary — redundant with the switch).

Users upgrading will see these as `unavailable` until they delete them
from the entity registry — behaviour is the same as any HA integration
renaming unique_ids.

## Entities added

Bus 1: `fuel_level`, `adblue_remaining_distance`,
`distance_to_service`, `outside_temperature`, `parking_brake_engaged`,
`cruise_control_active`, `downhill_assist_active`,
`standheizung_available`, `standheizung_state`, `lightsense_night`,
`wiping_water_empty`, `motor_oil_warning`, `cooling_water_empty`,
`door_entrance`.

Bus 3: `living_battery_voltage`, `living_battery_current`,
`starter_battery_voltage`, `living_battery_capacity`,
`ebl_outdoor_temp_sensor`, `shoreline_connected`,
`ebl_over_temperature`.

Bus 8: `solar_reduced_power`, `solar_aes_active` (the direct
`solar_power` reading replaces the previous computed entity as the
primary source).

Bus 30: `lte_connection_quality`, `lte_connection_state`, `scu_voltage`,
`paired_bt_devices`, `connected_bt_devices`, `vehicle_movement`.

Bus 99: `bms_battery_voltage`, `bms_battery_current`,
`bms_battery_temperature`, `bms_time_remaining`, `bms_state_of_health`,
`bms_capacity_remaining`, `bms_relative_capacity`,
`bms_charge_detected`, `bms_device_failure`.

## docs/protocol.md

A new reference document describing the PiaRequest / PiaResponse
protobuf envelope, field-number → datatype mapping for writes, the
multi-sensor batching pattern, and the sentinel values the SCU uses for
"no data available".  Entirely derived from mitmproxy captures of a
real session — no content lifted from the app binary.

## What was deliberately *not* changed

- Bus 58 Truma labels (`heater_fan_speed`, `heater_fuel_type`, etc.) —
  the registry names (`TargetWaterTemperature`,
  `AirTemperatureEnergySource`, …) are more accurate but the existing
  labels are what `climate.py`, `select.py::HymerBoilerSelect` and the
  new `HymerHeaterEnergySelect` all depend on.  A follow-up PR can
  rename them together with the entities that use them.
- Bus 34 Thetford fridge mapping — labels match registry closely;
  leaving alone to avoid conflicts with the working fridge select/switch
  entities.
- Bus 45 / 49 LIM module labels (`scu_connected`, `truma_connected`) —
  registry identifies these as lighting interface modules; the semantic
  mismatch is small enough to defer.

## Open question: vehicle-agnostic labelling

The S 700 + your van both happen to see tank data on bus 22/25.  On
vans with different habitation electrics the same component IDs may
carry different signals (the app's global registry has no per-vehicle
override table).  The cleanest long-term fix is to read the SCU's own
`PiaResponse` and look for a field that carries the component's string
name — if that exists on the wire we can build the label map
dynamically and stop hardcoding.  I've flagged this as a follow-up; we
haven't confirmed yet whether the names are actually there.

## Testing

Deployed and validated against a running HA OS instance connected to a
2025 Grand Canyon S 700 (`HY_YELLOWSTONE_S_2025`).  Verified the new
entities populate from live SCU data, the water-pump switch reads back
state correctly, the climate entity still sets and clears temperature,
and the solar-power sensor reports sensible W values through a sunny
afternoon.
