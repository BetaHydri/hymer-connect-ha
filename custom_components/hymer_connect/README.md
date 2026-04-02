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

This integration communicates with the HYMER Connect cloud API at `scc-api.smartrv.erwinhymergroup.com` (Azure API Management). It uses the same API as the official HYMER Connect mobile app.

### Architecture
```
Home Assistant → HTTPS REST API → Azure APIM → EHG Backend → SIU (vehicle)
```

Real-time updates via Azure SignalR Service are planned for a future release.

## Development Status

- [x] API base URL discovered (`scc-api.smartrv.erwinhymergroup.com`)
- [x] Integration skeleton (config flow, coordinator, sensors, binary sensors)
- [x] Reauth flow support
- [x] Dashboard YAML
- [ ] Auth flow validation with real credentials
- [ ] Actual API response mapping to entities
- [ ] Climate control entities (heater target temperature)
- [ ] Switch entities (lights, USB, water pump)
- [ ] SignalR real-time push updates

## License

This project is not affiliated with or endorsed by the Erwin Hymer Group.
