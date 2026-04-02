# HYMER Connect for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom integration to connect your HYMER / Erwin Hymer Group motorhome or caravan to [Home Assistant](https://www.home-assistant.io/).

> **Status:** Early development — authentication flow and sensor mapping are being validated against the live API.

## Supported Brands

This integration works with all Erwin Hymer Group brands equipped with a **Smart Interface Unit (SIU)**:

| Brand | | Brand |
|-------|-|-------|
| HYMER | | Carado |
| Bürstner | | Laika |
| Dethleffs | | Sunlight |
| Eriba | | FreeOnTour |
| LMC | | Niesmann+Bischoff |

## Features

### Sensors
- **Battery** — level (%), voltage (V), chassis battery voltage (V)
- **Water tanks** — fresh water level (%), grey water level (%)
- **Temperature** — indoor (°C), outdoor (°C)
- **Tire pressure** — front left, front right, back left, back right (bar)

### Binary Sensors
- **SIU online** — vehicle connectivity status
- **Mains power** — shore power connected
- **Door / Window** — open/closed state
- **Alarm** — alarm system active
- **Heater / Fridge** — running state

### Dashboard
A ready-to-use Lovelace dashboard is included in `dashboards/hymer_connect.yaml`.

## Installation

### HACS (recommended)
1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/BetaHydri/hymer-connect-ha` as **Integration**
4. Search for "HYMER Connect" and install
5. Restart Home Assistant

### Manual
1. Copy the `hymer_connect` folder into your `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → + Add Integration**
2. Search for **HYMER Connect**
3. Select your brand and enter your HYMER Connect app credentials
4. The integration will create sensor entities for your vehicle

## Dashboard Setup

1. Go to **Settings → Dashboards → + Add Dashboard**
2. Open the new dashboard → Edit → three dots → **Raw configuration editor**
3. Paste the contents of [`dashboards/hymer_connect.yaml`](dashboards/hymer_connect.yaml)
4. Save

## API

This integration communicates with the HYMER Connect cloud API at `smartrv.erwinhymergroup.com`. It uses the same OAuth2 ROPC authentication as the official HYMER Connect web and mobile apps.

### Authentication

| Parameter | Value |
|-----------|-------|
| **Endpoint** | `POST https://smartrv.erwinhymergroup.com/api/v2/oauth/token` |
| **Grant type** | `password` (OAuth2 ROPC) |
| **Client auth** | HTTP Basic `OAUTH2_CLIENT:OAUTH2_CLIENT` |
| **Content-Type** | `application/x-www-form-urlencoded` |
| **Body** | `grant_type=password&username=<email>&password=<password>` |

The API returns `access_token`, `refresh_token`, and `id_token` (JWT, RS256). Token refresh uses the same endpoint with `grant_type=refresh_token`.

The `access_token` JWT contains these claims:
- `account_number` — UUID of the user account
- `user_name` — email address
- `scope` — `["default"]`
- `tenant` — `"ehg"` (Erwin Hymer Group)
- `client_id` — `"OAUTH2_CLIENT"`
- `exp` — expiry timestamp (tokens expire after ~15 minutes)

### API Domains

| Domain | IP | Purpose |
|--------|----|---------|
| `smartrv.erwinhymergroup.com` | 20.4.141.205 | Authentication, SignalR negotiate, web app |
| `scc-api.smartrv.erwinhymergroup.com` | 20.103.22.48 | REST API data endpoints (Azure API Management) |
| `scc-rvtwin.smartrv.erwinhymergroup.com` | 13.107.226.45 | Vehicle twin data (RV digital twin) |
| `scc-appcomm.smartrv.erwinhymergroup.com` | 20.4.141.205 | SignalR hub (alias of smartrv) |
| `ehg-prod-signalr.service.signalr.net` | varies | Azure SignalR Service WebSocket |

### REST API Endpoints

All endpoints require the `SCC-CsNgAccessToken` header with the `access_token` from authentication.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/ehg/v1/accounts/me` | Current user account info |
| GET | `/api/ehg/v1/accounts/available` | Check email availability |
| GET | `/api/ehg/v1/vehicles` | List of registered vehicles |
| GET | `/api/ehg/v1/sius` | List of Smart Interface Units |
| GET | `/api/ehg/v1/sensors` | Sensor data |
| GET | `/api/ehg/v1/legal-docs/latest` | Latest legal documents |
| GET | `/api/ehg/v1/firmwares/sius` | Firmware info for SIUs |
| POST | `/api/ehg/v1/updates` | Update management |
| POST | `/api/ehg/v1/accounts/standard/resetPassword` | Password reset |
| GET | `/api/rv-twin/sensors/sync` | RV twin sensor sync |
| GET | `/api/rv-twin/rv-model/documents` | RV model documents |
| GET | `/api/rv-twin/rv-model/filters-hierarchy` | RV model filter hierarchy |
| GET | `/api/service-catalogue/services` | Service catalogue |
| GET | `/api/push-notifications/subscriptions/scu` | Push notification subscriptions |
| GET | `/datahub/negotiate` | SignalR negotiate (no auth required) |

### HTTP Headers

| Header | Description |
|--------|-------------|
| `SCC-CsNgAccessToken` | OAuth2 access token |
| `SCC-CsNgRemoteToken` | OAuth2 refresh token |
| `SCC-Locale` | Language code (e.g. `de`, `en`) |
| `SCC-PinCode` | PIN code for certain operations |
| `SCC-ScuUrn` | SIU URN for device-specific requests |

### Architecture

```
                    ┌──────────────────────────────────┐
                    │  smartrv.erwinhymergroup.com      │
                    │  POST /api/v2/oauth/token         │
                    │  (OAuth2 ROPC + HTTP Basic Auth)  │
                    └──────────┬───────────────────────┘
                               │ access_token
                    ┌──────────▼───────────────────────┐
                    │  scc-api.smartrv.erwinhymergroup  │
                    │  REST API data endpoints          │
                    │  (SCC-CsNgAccessToken header)     │
                    └──────────┬───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼──────┐ ┌───────▼───────┐
    │ Vehicle Data   │ │  RV Twin    │ │  SignalR Hub  │
    │ /api/ehg/v1/   │ │ scc-rvtwin  │ │ scc-appcomm   │
    │ vehicles,sius  │ │ sensors/sync│ │ /datahub      │
    │ sensors        │ │             │ │ (real-time)   │
    └────────────────┘ └─────────────┘ └───────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  SIU (Smart Interface Unit)       │
                    │  Vehicle gateway (cellular/BLE)   │
                    └──────────┬───────────────────────┘
                               │ Vehicle Bus
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼──────┐ ┌───────▼───────┐
    │ Truma Heater   │ │ Dometic     │ │ Sensors       │
    │ Alde Boiler    │ │ Fridge      │ │ Battery, Temp │
    │ Hegotec Lights │ │ Victron     │ │ Water, TPMS   │
    └────────────────┘ └─────────────┘ └───────────────┘
```

### Key Terminology

| Term | Description |
|------|-------------|
| **SIU** | Smart Interface Unit — central vehicle gateway module |
| **SCU** | Smart Control Unit (older term for SIU) |
| **CSNG** | Internal platform codename |
| **EHG** | Erwin Hymer Group |
| **Connected Component** | Any device on the vehicle bus (heaters, fridges, lights, etc.) |
| **DataHub** | SignalR hub for real-time cloud communication |
| **RV Twin** | Digital twin representation of the vehicle |

### Source App Analysis

This integration was reverse-engineered from:
- **HYMER Connect** Android app v2.10.14 (`com.ehg.hymerconnect`)
- React Native app with Hermes bytecode engine
- Nordic Semiconductor BLE stack for local SIU communication
- Microsoft SignalR for real-time cloud communication
- Protocol Buffers for structured vehicle messages

## Development Status

- [x] API base URL discovered
- [x] Auth endpoint discovered (`/api/v2/oauth/token` with HTTP Basic Auth)
- [x] Authentication tested successfully (returns access_token + refresh_token)
- [x] Integration skeleton (config flow, coordinator, sensors, binary sensors)
- [x] Reauth flow support
- [x] Dashboard YAML
- [ ] Actual API response mapping to entities
- [ ] Climate control entities (heater target temperature)
- [ ] Switch entities (lights, USB, water pump)
- [ ] Cover entities (awning, roof, dome)
- [ ] SignalR real-time push updates
- [ ] Device tracker (GPS location)

## License

This project is not affiliated with or endorsed by the Erwin Hymer Group.
