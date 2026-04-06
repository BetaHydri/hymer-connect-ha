# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.2] - 2026-04-06

### Fixed

- **Brightness/color temp not reverting to stale SCU values** — optimistic brightness and color temp are no longer cleared on the 5s timer. They persist until the SCU pushes the updated value via SignalR (within ~5% tolerance). This prevents the slider from snapping back to old values after adjustment

## [2.4.1] - 2026-04-06

### Fixed

- **Bedroom ambient on/off restored** — removed `use_brightness_for_on_off` which was preventing sid=1 from being sent. Bedroom ambient now sends sid=1 for on/off like all other lights. Note: sid=1 on bus 15 is the private area group switch (same as the Privat Group light entity) — this is a hardware limitation

## [2.4.0] - 2026-04-06

### Changed

- **Optimistic hold reduced to 5s** — normal lights now refresh state after 5 seconds instead of 30. Bedroom ambient uses permanent optimistic (no timer)

## [2.3.9] - 2026-04-06

### Fixed

- **Bedroom ambient on/off via brightness** — re-enabled `use_brightness_for_on_off` for bedroom ambient (bus 15). On/off toggle now sends brightness=100/0 instead of sid=1 (avoiding group switch). Optimistic state is permanent (never auto-clears) so the on/off state stays until the next explicit toggle
- Other lights unchanged — still use sid=1 for on/off

## [2.3.8] - 2026-04-06

### Fixed

- **Lights don't turn on** — v2.3.7 broke all lights because HA always includes ATTR_BRIGHTNESS in kwargs for COLOR_TEMP/BRIGHTNESS modes, so `has_attrs` was always True and sid=1 was never sent. Reverted: normal lights always send sid=1 on turn_on, regardless of whether brightness/color_temp kwargs are present

## [2.3.7] - 2026-04-06

### Fixed

- **Brightness slider clears optimistic on state** — adjusting brightness was scheduling a clear that wiped the optimistic_on from the toggle. Now attribute-only changes don't schedule optimistic clear, preserving the on state from the previous toggle

## [2.3.6] - 2026-04-06

### Fixed

- **Optimistic hold increased to 30s** — bedroom ambient was falling back to off after 10s because bus 15 sid=1 read state doesn't reflect individual on/off. 30s hold gives enough time for normal use without bounce-back
- Note: brightness slider showing 0 when light is off is normal HA behavior — the stored value on the SCU is preserved

## [2.3.5] - 2026-04-06

### Fixed

- **Sliders don't turn light on anymore** — optimistic_on was always set to True in async_turn_on, causing HA to briefly show the light as on when just moving a slider. Now optimistic_on is only set when sid=1 is actually sent (pure on/off toggle). Adjusting brightness/color temp on an off light only stores the value without toggling the light state

## [2.3.4] - 2026-04-06

### Fixed

- **Brightness/color temp slider doesn't send sid=1 anymore** — for ALL lights, sid=1 (on) is only sent for pure on/off toggle (no attributes). When adjusting brightness or color temp sliders, only sid=2/sid=3 are sent. This prevents bus 15 group switch from being triggered when just adjusting bedroom ambient brightness/color temp

## [2.3.3] - 2026-04-06

### Changed

- **Bedroom ambient uses normal sid=1 on/off** — removed `use_brightness_for_on_off`. The app confirms brightness doesn't control on/off (min 1%, separate toggle). Bus 15 sid=1 is the private area group switch, but that's how the hardware works. Toggling bedroom ambient on/off will also toggle other private lights. Use the "Privat all lights" entity for intentional group control, or use brightness/color temp sliders for individual adjustment without toggling

## [2.3.2] - 2026-04-06

### Fixed

- **Bedroom ambient is_on** — for `use_brightness_for_on_off` lights only, `is_on` now checks brightness > 0 (since sid=1 is the group switch and doesn't reflect individual state). All other lights still use on_off_path

## [2.3.1] - 2026-04-06

### Added

- **Private area group switch** — bus 15 sid=1 controls all private area lights (bedroom ambient, nightlight, bathroom, bedroom overhead). Added as 10th light entity "Privat all lights"
- Dashboard: Master Switches section now shows both "All Wohnen" and "All Privat" side by side

## [2.3.0] - 2026-04-06

### Fixed

- **Bedroom ambient always shows on** — brightness-based is_on was reading non-zero brightness even when light is off (residual value). Reverted is_on to always use on_off_path for ALL lights (reading works correctly). The `use_brightness_for_on_off` flag now only affects the WRITE path (commands), not the READ path (state detection)

## [2.2.9] - 2026-04-06

### Fixed

- **Regression: all lights bouncing off** — v2.2.7 changed `is_on` to use brightness > 0 for ALL lights with brightness_path, but this broke lights where brightness reads 0 when off even though on_off_path reads True. Reverted: only bedroom ambient (use_brightness_for_on_off=True) uses brightness-based detection, all other lights use on_off_path as before

## [2.2.8] - 2026-04-06

### Fixed

- **Bedroom ambient sid 1 is a private area group switch** — sending on/off via sid 1 on bus 15 toggles ALL private area lights (bath, bedroom). Now uses brightness to control on/off instead:
  - Turn on: sets brightness > 0 (skips sid=1)
  - Turn off: sets brightness = 0 (skips sid=1)
  - Added `use_brightness_for_on_off` flag to entity description for bus 15

## [2.2.7] - 2026-04-06

### Fixed

- **Bedroom ambient on/off state** — bus 15 sid 1 doesn't reliably report on/off state. For lights with brightness_path, `is_on` now derives from brightness > 0 instead of the on_off_path. This prevents the bounce-off after the optimistic window expires

## [2.2.6] - 2026-04-06

### Fixed

- **Bedroom ambient brightness restored** — app screenshot confirms bus 15 has brightness (Helligkeit 26%) + color temp (Lichttemperatur 100). The `div10` transform was the bug: raw brightness value 26 was stored as 2.6 (looked like solar amps). Removed `div10` transform from `(15, 2)` and restored as `light_bedroom_ambient_brightness`
- Note: `solar_current` sensor is removed again — bus 15 sid 2 is confirmed as brightness, not solar

## [2.2.5] - 2026-04-06

### Fixed

- **Bedroom ambient bounce-off root cause** — bus 15 sid 2 is NOT brightness, it's solar current. Sending brightness commands to sid 2 was confusing the SCU and turning the light off
  - Reverted `(15, 2)` back to `solar_current` (restoring solar current + solar_active sensors)
  - Removed `brightness_path` from bedroom ambient — this light has on/off + color temp only
  - Brightness commands now gated on `brightness_path` existing (won't send sid=2 to lights without it)

## [2.2.4] - 2026-04-06

### Fixed

- **Bedroom ambient still bouncing off** — reordered command sequence: send `on` (sid=1) first, then brightness (sid=2), then color temp (sid=3). SCU needs the light on before accepting attribute changes
- Increased optimistic hold time from 5s to 10s to give SCU more time to process and reflect state

## [2.2.3] - 2026-04-06

### Fixed

- **Light turns off immediately after turning on** — immediate `async_request_refresh()` was reading stale SCU state before the command was processed. Now uses optimistic state: UI stays in the commanded state for 5 seconds while the SCU processes, then refreshes to confirm

## [2.2.2] - 2026-04-06

### Fixed

- **Bedroom ambient brightness + color temp** — `(15, 2)` remapped from `solar_current` to `light_bedroom_ambient_brightness`, `(15, 3)` from `solar_panel_temp` to `light_bedroom_ambient_color_temp`. Bedroom ambient now has brightness slider and warm↔cool color temp slider

## [2.2.1] - 2026-04-06

### Fixed

- **Night light brightness confirmed** — `(16, 2)` remapped from `water_pump_status` to `light_nightlight_brightness`. Night light now has a working brightness slider (confirmed by live test)

## [2.2.0] - 2026-04-06

### Added

- **Color temperature slider** — lights with color temp support (Living ambient, Kitchen) now show a warm↔cool slider in the HA UI
  - Maps SCU 0-100% range to 2700K (warm white) – 6500K (daylight)
  - Color temp commands sent via `(bus, sid=3, uint=0-100)` write protocol
- **Uniform light card dashboard** — all 9 lights use `type: light` cards showing on/off toggle, brightness slider, and color temp slider based on each light's capabilities

## [2.1.0] - 2026-04-06

### Added

- **Brightness slider controls** — lights with brightness support now show a slider in the HA UI
  - Living ceiling, Living ambient, Kitchen, Seating overhead, Bathroom ceiling, Bedroom overhead: brightness 0-100%
  - Bedroom ambient, Night light, Wohnen group: on/off only
- Brightness commands sent via `(bus, sid=2, uint=0-100)` write protocol

## [2.0.4] - 2026-04-06

### Fixed

- **Bus 24 is Wohnen group switch, not outside light** — toggling bus 24 turns on/off ALL living area lights (confirmed by user). Renamed to "Wohnen all lights" and moved to Wohnen section in dashboard. Outside light bus still needs to be identified via mitmproxy capture

## [2.0.3] - 2026-04-06

### Added

- **Outside light (LED strip)** — bus 24 added as 9th controllable light entity
- Dashboard updated with Außen (Outside) section

## [2.0.2] - 2026-04-06

### Fixed

- **6 of 8 lights not created** — lights with BRIGHTNESS color mode weren't registered by HA. Changed all lights to ONOFF mode so all 8 entities are created

## [2.0.1] - 2026-04-06

### Fixed

- **Import error on startup** — `ATTR_COLOR_TEMP` removed from `homeassistant.components.light` in newer HA versions. Removed unused import

## [2.0.0] - 2026-04-06

### Added

- **Light write controls** — 8 controllable HA light entities with on/off and brightness (#23, #6)
  - Turn lights on/off from Home Assistant via SignalR PiaRequest commands
  - Brightness control (0-100%) with HA slider
  - New `light.py` platform with `LightEntity` subclass
  - `build_light_command()` protobuf encoder in pia_decoder.py
  - `send_light_command()` method in signalr_client.py
  - `signalr_client` property exposed on coordinator
- **Dedicated Lights dashboard page** with Wohnen (Living) and Privat (Private) groups

### Known Issues

- Light state reading may not update when lights are toggled physically or via the Hymer app (#25)
- Outside light brightness shows 10000 instead of percentage (#21)

## [1.11.0] - 2026-04-05

### Added

- **Individual light sensors** — all 9 lights now mapped with on/off binary sensors and brightness percentage sensors (#18):
  - **Wohnen**: Living ceiling (bus 11), Living ambient (bus 12), Kitchen (bus 21), Seating overhead (bus 43)
  - **Privat**: Bedroom ambient (bus 15), Night light (bus 16), Bathroom ceiling (bus 19), Bedroom overhead (bus 44)
  - **Außen**: Outside light (bus 24)
- **8 new binary sensors** for light on/off state
- **6 new brightness sensors** showing last-used brightness percentage

### Changed

- **Sensor renames** — bus IDs previously misidentified as alarm/step/dimmer are actually individual lights:
  - Bus 11: `alarm_armed` → `light_living_ceiling`, `alarm_battery` → `light_living_ceiling_brightness`
  - Bus 12: `step_retracted` → `light_living_ambient`, `step_sensor_2` → `light_living_ambient_brightness`
  - Bus 16: `water_pump` → `light_nightlight` (shared bus — same signal)
  - Bus 15: `solar_charger_boost` → `light_bedroom_ambient` (shared bus with solar current)

## [1.10.1] - 2026-04-05

### Fixed

- **engine_hours wrong divisor** — v1.10.0 used `div100` (= 36174h, impossible for a 9-month-old vehicle). Raw CAN value is in **seconds**, not hundredths of hours. Corrected to `div3600` (seconds → hours): 3,617,400s ÷ 3600 = **1,004.8 hours** — plausible for 11k km with idle time

## [1.10.0] - 2026-04-05

### Fixed

- **engine_hours now shows correct value** — raw CAN value 3617400 was displayed as-is; now applies `div100` transform to show 36174.0 hours. Confirmed via mitmproxy traces across 3 sessions (#15)
- **Removed stale translation keys** — cleaned up orphaned `fuel_consumption`, `trip_distance`, `solar_voltage`, and `solar_power` entries from strings.json and translations/en.json that were left over from v1.9.1 sensor removal

### Added

- **heat_setpoint_raw div1000 transform** — heating control raw setpoint (bus 34, sensor 7) now converts from millidegrees to °C (raw 13000 → 13.0°C)
- **New sensor map entries from mitmproxy capture** — added 14 previously unmapped sensors discovered during Apr 5 WebSocket trace:
  - GPS extended: `(30, 8-14)` — additional GPS metadata sensors
  - Heat control: `(34, 4-6)` — additional heating controller sensors
  - SCU: `(45, 9-10)` — additional SCU status sensors
  - Heater: `(58, 10, 12-14)` — additional Truma heater sensors

## [1.9.1] - 2026-04-05

### Fixed

- **Battery SOC now shows correct live value** — was reading from bus 3 s10 (habitation electronics, stale at 95%). Now reads from bus 99 s4 (`lithium_soc`) which reports the actual Lithium BMS SOC (93%) and updates via re-subscription
- **Removed false `fuel_consumption` sensor** — bus 99 s4 was misidentified as fuel consumption; it’s actually Lithium battery SOC
- **Removed false `trip_distance` sensor** — bus 99 s8 was misidentified as trip distance (showed 93 “km” when actual trip was 0.1 km); it’s a duplicate Lithium SOC value
- **Outdoor temperature** — confirmed as cached Mercedes CAN value from last drive (shows 3°C when actual outdoor temp is 19°C). Only updates when engine is running

## [1.9.0] - 2026-04-05

### Added

- **Periodic PIA re-subscription** — the coordinator now re-sends all PIA subscription requests on each 60-second poll cycle. This is required because the SCU only pushes updated sensor values in response to subscription requests. Without re-subscribing, sensors like battery SOC, solar current, fuel range, and trip distance stay at their initial cached values. Confirmed via 5-minute delta capture: re-subscribing triggered fuel_range, trip_distance, engine_torque, and total_fuel_used updates

### Changed

- **Outdoor temperature** — documented as Mercedes CAN cached value (bus 8 s3 / bus 99 s3). Only updates when the engine is running. The Hymer has no dedicated outdoor temperature sensor; requires a mitmproxy capture of Mercedes me API for real-time outdoor temp

## [1.8.6] - 2026-04-05

### Fixed

- **Stale sensor data / no live updates** — SignalR listen loop could silently die (unhandled exception in message handler, WebSocket disconnect), leaving sensor data frozen at initial values. Fixed with:
  - Proper error handling in the listen loop — individual message errors no longer crash the entire loop
  - Automatic reconnection — coordinator now detects dead connections on each poll and reconnects with fresh subscriptions
  - Stale client cleanup — old SignalR client is properly stopped before creating a new one
  - Warning-level log when listen loop ends — logs message count for diagnostics

## [1.8.5] - 2026-04-05

### Fixed

- **Solar Active always showing "Aus"** — bus 15 s1 is a PWM pulse indicator, not a steady charging flag. Changed `solar_active` to be computed from `solar_current > 0` — shows "Ein" whenever solar is producing current, regardless of the charger’s internal pulse state

## [1.8.4] - 2026-04-05

### Fixed

- **False errors in HA log** — coordinator and SignalR client used `warning` level for normal operational messages ("SignalR not connected", "Data update", "UpdateTokens SUCCESS"), causing them to appear as errors in the HA UI. Downgraded to `info`/`debug` level. Only actual failures remain as warnings/errors

## [1.8.3] - 2026-04-05

### Changed

- **Solar voltage removed** — bus 3 s19 always reports sentinel 3276.8 even during active solar charging; the SCU does not expose solar panel voltage via SignalR. The Hymer app likely reads voltage from the solar charger directly via a different channel
- **Solar power removed** — bus 15 s3 is not watts (value 58 doesn’t match V×I); likely panel temperature or charger internal value (renamed to `solar_panel_temp`)
- **Solar active** — reverted to bus 15 s1 which toggles True/False during active charging (confirmed in live capture)
- **Dashboard** — removed solar voltage, solar power, and solar charger status entities (unavailable via SignalR)

## [1.8.2] - 2026-04-05

### Fixed

- **Solar Active showing "Aus" while charging** — bus 15 s1 is NOT the solar active flag (it’s False even during active charging); changed `solar_active` binary sensor to read from `solar_connected` (bus 3, s20) which correctly reports 1 when solar is active
- Bus 15 s1 renamed to `solar_charger_boost` (purpose still TBD)

## [1.8.1] - 2026-04-05

### Fixed

- **Fresh water level wrong bus** — was mapped to bus 21 s2 (=91%, a config value); corrected to bus 22 s2 which shows ~6% matching empty tanks
- **Grey water level wrong bus** — was mapped to bus 12 s2 (=35%, likely step/drainage sensor); corrected to bus 25 s2 which shows ~6% matching empty tanks
- Both water levels now match the Hymer Connect app's "<10%" display when tanks are empty

## [1.8.0] - 2026-04-05

### Added

- **Solar current sensor** (bus 15, s2) — solar panel charge current in amps (div10 transform)
- **Solar power sensor** (bus 15, s3) — solar panel output power in watts
- **Solar active binary sensor** (bus 15, s1) — indicates whether the solar charger is actively charging
- **Fresh water level sensor** (bus 21, s2) — fresh water tank fill percentage
- **Water pump binary sensor** (bus 16, s1) — water pump on/off state
- **Sentinel value filtering** — CAN "no data" values (3276.8, 32768, 65535, 6553.5) now filtered out in both the decoder and sensor entities, preventing display of stale/invalid readings
- **30+ missing translations** — added translation keys for all existing sensors that were previously untranslated

### Fixed

- **Solar voltage showing 3276.8V** — removed incorrect `div1000` transform; the protobuf float value IS the voltage directly (like battery voltage). The 3276.8 value was a CAN sentinel (32768/10) indicating "sensor unavailable" when main power is off
- **Fridge mode labels** — expanded from `{8: Off}` to `{0: On, 1: Eco, 2: Boost, 8: Off}`
- **Fridge status labels** — expanded from `{1: Off}` to `{0: Running, 1: Off, 2: Standby}`
- **Dashboard YAML** — added solar current, solar power, solar active, fresh water level, and water pump entities

## [1.7.4] - 2026-04-04

### Fixed

- **Solar voltage reading 3276.8V** — raw protobuf value is in millivolts; added `div1000` transform so it displays correctly as ~3.3V
- **Dashboard entity ID** — fixed `solar_voltage` entity reference to actual HA-generated ID `sensor.hymer_hymer_connect_hymer_spannung`

## [1.7.3] - 2026-04-04

### Fixed

- **Sensor misidentification — solar, not mains** (closes [#13](https://github.com/BetaHydri/hymer-connect-ha/issues/13)) — sensors (3,19), (3,20), (3,21) are the **solar panel** charger, not 230V mains power:
  - `ext_charger_voltage` → `solar_voltage` (reads ~2-3V with no sun, higher in daylight)
  - `mains_connected` → `solar_connected` (always 1 because solar panel is hardwired)
  - `charger_status` → `solar_charger_status` (1 = standby)
- Icons updated to `mdi:solar-power` / `mdi:solar-power-variant`

## [1.7.2] - 2026-04-04

### Fixed

- **Mains power sensor false positive** — `mains_connected` incorrectly reported "plugged in" when the vehicle was parked without shore power; caused by protobuf bool field (field 5) overwriting the uint field (field 3) — since Python `True == 1`, the `on_value=1` check always matched; fixed by preferring uint/int over bool when multiple value fields are present

## [1.7.1] - 2026-04-04

### Fixed

- **Door sensors inverted** — `OFF` now correctly maps to "Closed" (was incorrectly "Open"); confirmed via Mercedes-Benz app showing vehicle locked with all doors closed

## [1.7.0] - 2026-04-04

### Added

- **26 new sensor entities** (closes [#8](https://github.com/BetaHydri/hymer-connect-ha/issues/8)):
  - Engine: RPM, engine hours
  - Heater: state, electric power (W), operating mode
  - Fridge: mode, status
  - Fuel: range (km), consumption, total used, trip distance
  - Engine: torque (%), AdBlue temperature
  - DPF status
  - Charger: external voltage, charger status
  - Lights: dimmer level 1 & 2 (%)
  - Tire pressure (bar)
  - Alarm battery (%)
  - SCU firmware, Truma firmware, Truma status
  - GPS: satellites, heading
- **10 new binary sensor entities**:
  - Rear door, headlamp, high beam, parking light, fog front/rear, turn signal
  - Truma connected, step retracted

## [1.6.3] - 2026-04-04

### Fixed

- **SignalR log noise** — changed PiaResponse and SignalR message logs from WARNING to DEBUG level; connection events changed to INFO

## [1.6.2] - 2026-04-04

### Fixed

- **device_tracker setup error** — import `TrackerEntity` from `config_entry` module (fixes integration load failure in v1.6.1)

## [1.6.1] - 2026-04-04

### Fixed

- **Brand images** — move to `brand/` subfolder for HA 2026.3+ local brand API

## [1.6.0] - 2026-04-04

### Fixed

- **current_gear sensor** — map raw CAN value 100 to "P" (Park), gears 1-7 for drive positions (closes [#5](https://github.com/BetaHydri/hymer-connect-ha/issues/5))

### Added

- **device_tracker entity** — shows vehicle location on the HA map from GPS coordinates with altitude, heading, satellites, and signal quality as attributes (closes [#11](https://github.com/BetaHydri/hymer-connect-ha/issues/11))
- HC brand logo (icon.png, logo.png) for HA integration UI and GitHub README
- "Open in HACS" button in README

### Changed

- Hardened `.gitignore` — excludes `.venv*/`, `.env`, `private_*` files

## [1.5.2] - 2026-04-04

### Added

- Created GitHub issues for all known TODOs and missing functionality
- Updated README screenshots (new ha-screenshot.png, added ha-screenshot_2.png)
- Synced root README.md to v1.5.0 component version

### Known Issues

- ~~**current_gear shows raw value 100**~~ — fixed in v1.6.0 ([#5](https://github.com/BetaHydri/hymer-connect-ha/issues/5))
- **Integration is read-only** — no write controls for lights, heater, fridge, awning, switches ([#6](https://github.com/BetaHydri/hymer-connect-ha/issues/6))
- **9 bus IDs unmapped** — awning, ext_light, dimmer, roof_vent, screen, inverter, generator, wifi, bluetooth ([#7](https://github.com/BetaHydri/hymer-connect-ha/issues/7))
- **30+ mapped sensors not exposed as HA entities** — rpm, engine_hours, fridge, tire_pressure, fuel_range, and more ([#8](https://github.com/BetaHydri/hymer-connect-ha/issues/8))
- **Several sensors show Nicht verfügbar** — fresh water, fuel level, heater mode, lock status, duplicate sliding door ([#9](https://github.com/BetaHydri/hymer-connect-ha/issues/9))
- **Delta-only updates after reconnect** — SCU only sends full dump on first connection ([#10](https://github.com/BetaHydri/hymer-connect-ha/issues/10))
- ~~**GPS not exposed as device_tracker**~~ — fixed in v1.6.0 ([#11](https://github.com/BetaHydri/hymer-connect-ha/issues/11))
- **Truma boiler sensors unmapped** — bus 58 sensors 10-14 ([#12](https://github.com/BetaHydri/hymer-connect-ha/issues/12))

## [1.5.1] - 2026-04-04

### Changed

- **heater_mode → heater_fan_speed** — sensor (58,5) reports the Truma Combi 6E fan speed setting: Off/Eco/High (confirmed via PiaRequest protobuf decode)
- Added ECO and HIGH value labels for fan speed display
- Updated sensor icon to `mdi:fan`

## [1.5.0] - 2026-04-04

### Changed

- **heater_fan_speed → heater_electric_power** — Truma Combi 6E sensor (58,9) reports electric heating element power in Watts (0/900/1800), not fan speed

### Discovered (not yet mapped)

- **Fridge OFF state**: `fridge_mode=8`, `fridge_status=1` — can identify fridge on/off
- **Truma heater OFF state**: `heater_mode=Off`, `heater_state=False`, `heater_setpoint=-273.0` — correctly mapped
- **Truma boiler OFF state**: bus58 sensors 10-14 all False when boiler is off
- **Light control is write-only** — the app sends PiaRequest commands to toggle lights, but the SCU does not report light state changes back through sensor data. `light_1_level`/`light_2_level` (3,8)/(3,9) show 0% regardless of light state. Needs mitmproxy capture of write PiaRequests at vehicle.
- **Lights have dimmer + color temperature (CCT)** — each light group supports brightness % and warm↔cool white
- **SCU only sends full sensor dump on first connection** — subsequent connections receive delta updates only (~17 sensors)

## [1.4.0] - 2026-04-04

### Fixed

- Battery SOC: renamed from fresh_water_level to battery_soc (3,10) — matches app Lithium-Batterie 95%
- Chassis battery voltage: renamed from solar_voltage to chassis_battery_voltage (3,7) — matches app 12.3V
- AdBlue level: renamed from fuel_level to adblue_level (1,6) — matches app 88%
- Odometer divisor: div1000 (raw 11113500 / 1000 = 11,113.5 km)

## [1.3.0] - 2026-04-04

### Changed

- Doors converted to binary sensors with DOOR device class — HA auto-translates: Offen/Geschlossen (DE), Open/Closed (EN)
- Lock converted to binary sensor with LOCK device class — HA: Gesperrt/Entsperrt
- Main switch converted to binary sensor with POWER device class — HA: Ein/Aus
- No more mixed English/German labels — all states translated by HA based on user's language

### Removed

- Duplicate text sensors for doors, lock, and main switch (replaced by binary sensors)

## [1.2.1] - 2026-04-04

### Changed

- Door sensors now show "Open"/"Closed" instead of raw CAN values "OFF"/"CLS"/"SNA"
- Ignition sensor shows "Off"/"On"/"Starting" instead of "IGN_LOCK"/"IGN_ON"/"IGN_START"
- Lock status shows "Locked"/"Unlocked" instead of raw strings
- Headlamp, fog lights, heater mode show "On"/"Off" instead of raw "ON"/"OFF"

## [1.2.0] - 2026-04-04

### Added

- Proper friendly names for all 39 sensor and binary sensor entities (Odometer, Speed, Fuel level, Lock status, Ignition, Driver door, etc.)

### Fixed

- Entities showing generic "HYMER HYMER Connect (HYMER)" name instead of descriptive sensor names
- Heater setpoint showing -273.0°C when heater is off (now shows as unavailable)
- Translation keys in strings.json/en.json now match all sensor entity descriptions

## [1.1.0] - 2026-04-04

### Added

- **PiaRequest subscription** — integration now sends all 13 PiaRequest messages after UpdateTokens to subscribe to sensor data streams
- 142 live sensors now populate in Home Assistant (battery, GPS, water, temps, doors, heater, fridge, alarm, odometer, and more)

### Fixed

- Sensor entities were showing `unknown` because PiaRequest subscription messages were missing after SignalR connection
- Fixed subscription payload to use exact captured protobuf from the Hymer Connect app

## [1.0.0] - 2026-04-04

### Added

- **Real-time sensor data via SignalR** — 130+ sensors including odometer, GPS, battery, water levels, temperatures, door status, heater, fridge, alarm, and more
- **EHG Remote Access Token refresh flow** — discovered `POST /api/ehg/v1/vehicles/{urn}/remoteAccessToken` endpoint that exchanges a long-lived refresh token for short-lived access tokens
- **EHG Refresh Token field** in the integration config flow (optional, required for real-time sensors)
- **`get_remote_access_token()` method** in API client for automatic token exchange
- **Comprehensive README** with step-by-step token extraction guide, mermaid architecture diagrams, and sequence diagrams
- **`.env` support** for local development credentials (`.env` added to `.gitignore`)

### Changed

- **SignalR client rewritten** — single refresh-based authentication flow instead of multi-variant fallback attempts
- **Coordinator** passes EHG refresh token through to SignalR client
- **Config flow** updated with optional EHG refresh token input field
- **Version bumped** from 0.3.x to 1.0.0

### Removed

- Hardcoded owner activation token from `signalr_client.py`
- Multi-variant UpdateTokens fallback logic (no longer needed)
- Obsolete "Help Wanted" section from README
- Outdated development status checklist from README

### Security

- Removed all hardcoded tokens and credentials from source code
- Added `.env` to `.gitignore` to prevent credential leaks
- Credentials stored locally only, never in version control

## [0.3.16] - 2026-04-03

### Fixed

- Parse paginated EHG vehicles response (`{content: [...]}` wrapper) to correctly extract vehicle URN

## [0.3.15] - 2026-04-03

### Fixed

- Allow SignalR to start with only SCU URN when vehicle URN is not yet discovered

## [0.3.14] - 2026-04-03

### Fixed

- Upgrade coordinator URN discovery and SignalR start logs to WARNING level for visibility

## [0.3.13] - 2026-04-03

### Fixed

- Remove auth headers from SignalR negotiate request to match real app behavior

## [0.3.12] - 2026-04-03

### Fixed

- Try owner activation token (`ett=owner`) as `ehgAccessToken` in UpdateTokens

## [0.3.11] - 2026-04-03

### Fixed

- Use correct `vehicleUrn` (`urn:ehg:vehicle:hy-...`) from EHG API instead of SCU URN

## [0.3.10] - 2026-04-03

### Fixed

- Test multiple `ehgAccessToken` variants with SignalR negotiate token as `accessToken`

## [0.3.9] - 2026-04-03

### Fixed

- Try SignalR negotiate token as `accessToken` in UpdateTokens

## [0.3.8] - 2026-04-03

### Fixed

- Continue after UpdateTokens failure (connection authenticated via JWT in URL)
- Log all SignalR messages at WARNING level for debugging

## [0.3.7] - 2026-04-03

### Fixed

- Try multiple UpdateTokens argument format variants sequentially

## [0.3.6] - 2026-04-03

### Fixed

- Revert UpdateTokens to dict format with 3 keys

## [0.3.5] - 2026-04-03

### Fixed

- Use positional args for UpdateTokens instead of object

## [0.3.4] - 2026-04-03

### Fixed

- Upgrade SignalR flow logs to WARNING/INFO for system_log visibility

## [0.3.3] - 2026-04-03

### Changed

- Add `*.docx` to `.gitignore`

## [0.3.2] - 2026-04-03

### Fixed

- Re-authenticate on startup, fix token refresh URL encoding, propagate auth errors

## [0.3.0] - 2026-04-03

### Added

- **SignalR datahub integration** with real API protocol
- **PIA Protobuf decoder** — 131 sensors mapped from vehicle bus data
- Pre-computed Basic auth header to avoid encoding issues with special characters

## [0.1.0-alpha] - 2026-04-03

### Added

- Initial HYMER Connect integration for Home Assistant
- OAuth2 ROPC authentication with EHG cloud API
- REST API sensors (vehicle model, VIN, model year)
- Binary sensors (SIU online, mains power, doors, windows, alarm, heater, fridge)
- Config flow with brand selection and credential input
- Reauth flow support
- Ready-to-use Lovelace dashboard
- HACS compatibility

[1.3.0]: https://github.com/BetaHydri/hymer-connect-ha/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/BetaHydri/hymer-connect-ha/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/BetaHydri/hymer-connect-ha/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/BetaHydri/hymer-connect-ha/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.16...v1.0.0
[0.3.16]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.15...v0.3.16
[0.3.15]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.14...v0.3.15
[0.3.14]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.13...v0.3.14
[0.3.13]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.12...v0.3.13
[0.3.12]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.11...v0.3.12
[0.3.11]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.10...v0.3.11
[0.3.10]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.3.0...v0.3.2
[0.3.0]: https://github.com/BetaHydri/hymer-connect-ha/compare/v0.1.0-alpha...v0.3.0
[0.1.0-alpha]: https://github.com/BetaHydri/hymer-connect-ha/releases/tag/v0.1.0-alpha
