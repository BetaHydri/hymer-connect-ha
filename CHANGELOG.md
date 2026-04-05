# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.10.1] - 2026-04-05

### Fixed

- **engine_hours wrong divisor** — v1.10.0 used `div100` (= 36174h, impossible for a 9-month-old vehicle). Raw CAN value is in **seconds**. Corrected to `div3600`: 3,617,400s ÷ 3600 = **1,004.8 hours**

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
- **Removed false `fuel_consumption` sensor** — bus 99 s4 was misidentified as fuel consumption; it's actually Lithium battery SOC
- **Removed false `trip_distance` sensor** — bus 99 s8 was misidentified as trip distance (showed 93 "km" when actual trip was 0.1 km); it's a duplicate Lithium SOC value
- **Outdoor temperature** — confirmed as cached Mercedes CAN value from last drive (shows 3°C when actual outdoor temp is 19°C). Only updates when engine is running

## [1.9.0] - 2026-04-05

### Added

- **Periodic PIA re-subscription** — the coordinator now re-sends all PIA subscription requests on each 60-second poll cycle. This is required because the SCU only pushes updated sensor values in response to subscription requests. Without re-subscribing, sensors like battery SOC, solar current, fuel range, and trip distance stay at their initial cached values. Confirmed via 5-minute delta capture: re-subscribing triggered fuel_range, trip_distance, engine_torque, and total_fuel_used updates

### Changed

- **Outdoor temperature** — documented as Mercedes CAN cached value (bus 8 s3 / bus 99 s3). Only updates when the engine is running. The Hymer has no dedicated outdoor temperature sensor; requires a mitmproxy capture of Mercedes me API for real-time outdoor temp

## [1.8.6] - 2026-04-05

### Fixed

- **Stale sensor data / no live updates** — SignalR listen loop could silently die (unhandled exception in message handler, WebSocket disconnect), leaving sensor data frozen at initial values. Fixed with proper error handling, automatic reconnection, stale client cleanup, and diagnostic logging

## [1.8.5] - 2026-04-05

### Fixed

- **Solar Active always showing "Aus"** — bus 15 s1 is a PWM pulse indicator, not a steady charging flag. Changed `solar_active` to be computed from `solar_current > 0`

## [1.8.4] - 2026-04-05

### Fixed

- **False errors in HA log** — coordinator and SignalR client used `warning` level for normal operational messages. Downgraded to `info`/`debug` level

## [1.8.3] - 2026-04-05

### Changed

- **Solar voltage removed** — bus 3 s19 always reports sentinel 3276.8; SCU does not expose solar panel voltage via SignalR
- **Solar power removed** — bus 15 s3 is not watts; renamed to `solar_panel_temp`
- **Dashboard** — removed solar voltage, solar power, and solar charger status entities

## [1.8.2] - 2026-04-05

### Fixed

- **Solar Active showing "Aus" while charging** — changed `solar_active` binary sensor to read from `solar_connected` (bus 3, s20). Bus 15 s1 renamed to `solar_charger_boost`

## [1.8.1] - 2026-04-05

### Fixed

- **Fresh water level wrong bus** — corrected from bus 21 s2 to bus 22 s2
- **Grey water level wrong bus** — corrected from bus 12 s2 to bus 25 s2

## [1.8.0] - 2026-04-05

### Added

- **Solar current sensor** (bus 15, s2) — solar panel charge current in amps
- **Solar power sensor** (bus 15, s3) — solar panel output power in watts
- **Solar active binary sensor** (bus 15, s1) — solar charger active state
- **Fresh water level sensor** (bus 21, s2) — fresh water tank fill percentage
- **Water pump binary sensor** (bus 16, s1) — water pump on/off state
- **Sentinel value filtering** — CAN "no data" values filtered out
- **30+ missing translations** — added translation keys for all existing sensors

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
- Dashboard YAML updated with new solar entity IDs

## [1.7.2] - 2026-04-04

### Fixed

- **Protobuf value priority** — prefer uint/int over bool when multiple value fields are present in protobuf sensor entries; prevents `True == 1` false matches for `on_value=1` binary sensors

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
