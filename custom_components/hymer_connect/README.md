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

The API returns `access_token`, `refresh_token`, and `id_token` (JWT). Token refresh uses the same endpoint with `grant_type=refresh_token`.

### API Domains

| Domain | Purpose |
|--------|---------|
| `smartrv.erwinhymergroup.com` | Authentication, SignalR negotiate |
| `scc-api.smartrv.erwinhymergroup.com` | REST API data endpoints |
| `scc-rvtwin.smartrv.erwinhymergroup.com` | Vehicle twin data |
| `scc-appcomm.smartrv.erwinhymergroup.com` | SignalR hub |

### Architecture
```
Home Assistant → OAuth2 Auth → REST API → EHG Backend → SIU (vehicle)
                                     ↓
                              SignalR DataHub → Real-time updates
```

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
