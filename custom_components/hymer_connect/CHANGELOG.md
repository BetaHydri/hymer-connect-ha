# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
