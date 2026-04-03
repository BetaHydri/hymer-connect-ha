# HYMER Connect for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom integration to connect your HYMER / Erwin Hymer Group motorhome or caravan to [Home Assistant](https://www.home-assistant.io/).

> **Status:** Early development — authentication flow and sensor mapping are being validated against the live API.

![HYMER Connect Integration in Home Assistant](./images/ha-screenshot.png)

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

```mermaid
graph TD
    AUTH["smartrv.erwinhymergroup.com<br/>POST /api/v2/oauth/token<br/>(OAuth2 ROPC + HTTP Basic Auth)"]
    API["scc-api.smartrv.erwinhymergroup<br/>REST API data endpoints<br/>(SCC-CsNgAccessToken header)"]

    AUTH -->|access_token| API

    VD["Vehicle Data<br/>/api/ehg/v1/<br/>vehicles, sius, sensors"]
    RT["RV Twin<br/>scc-rvtwin<br/>sensors/sync"]
    SR["SignalR Hub<br/>scc-appcomm<br/>/datahub (real-time)"]

    API --> VD
    API --> RT
    API --> SR

    SIU["SIU (Smart Interface Unit)<br/>Vehicle gateway (cellular/BLE)"]

    VD --> SIU
    RT --> SIU
    SR --> SIU

    TH["Truma Heater<br/>Alde Boiler<br/>Hegotec Lights"]
    DO["Dometic<br/>Fridge<br/>Victron"]
    SE["Sensors<br/>Battery, Temp<br/>Water, TPMS"]

    SIU -->|Vehicle Bus| TH
    SIU -->|Vehicle Bus| DO
    SIU -->|Vehicle Bus| SE
```

### SignalR DataHub (Real-Time Communication)

The SIU communicates with the cloud via an Azure SignalR Service hub. The app uses the `@microsoft/signalr` library.

| Property | Value |
|----------|-------|
| **Negotiate URL** | `POST https://scc-appcomm.smartrv.erwinhymergroup.com/datahub/negotiate?negotiateVersion=1` |
| **WebSocket URL** | `wss://ehg-prod-signalr.service.signalr.net/client/?hub=datahub` |
| **Protocol** | JSON (SignalR JSON protocol with `\x1e` delimiter) |
| **Auth for negotiate** | `Authorization: Bearer <access_token>` + `SCC-CsNgAccessToken: <access_token>` |
| **Auth for WebSocket** | JWT from negotiate response passed as `access_token` query parameter |

Connection states: `connecting` → `established` → `disconnected` (with auto-reconnect policy).

> **⚠️ HELP WANTED — SignalR Hub Method Names**
>
> Sensor data (battery, water levels, temperatures, tire pressure) and vehicle controls (lights, heater, fridge, water pump) flow **exclusively through SignalR WebSocket** — there is NO REST API for live sensor data.
>
> The mobile app sends ~10.5 KB through the WebSocket and receives ~21 KB of sensor data back. However, the exact **SignalR hub method name** that the app invokes is unknown.
>
> **What we know:**
> - Hub endpoint: `datahub` on Azure SignalR Service
> - The app calls `hub.invoke("???", args)` with an unknown method name
> - The server responds with `type=1` messages containing sensor data
> - 40+ method names were tested — ALL return `HubException: Method does not exist`
> - The method names found in the Hermes bytecode bundle (`sendClientDataToHub`, `sendMessageToHub`, `subscribeToHubEvents`, `syncSensors`) are **JavaScript function names** in the app code, NOT the actual SignalR hub method names
> - The real hub method name is compiled into Hermes bytecode v96 operations and cannot be extracted as a plain string
>
> **How to help:**
> 1. **Decompile the Hermes bytecode** — The bundle is at `assets/index.android.bundle` in the APK (Hermes v96, ~13 MB). Tools like [`hermes-dec`](https://nicolo-ribaudo.github.io/hermes-dec/) may be able to decompile it
> 2. **Intercept WebSocket frames** — Use a rooted Android device with Frida to hook `HubConnection.invoke()` and log the method name + arguments
> 3. **Check the iOS app** — The iOS version may have a more readable JavaScript bundle (not compiled to Hermes bytecode)
>
> If you can decode the SignalR hub method name, please open an issue or PR!

### Communication Paths

**Cloud Path** (used by this integration):
```
Home Assistant → HTTPS REST API → EHG Backend → SignalR DataHub → SIU (via cellular)
```

**BLE Path** (local, not used by this integration):
```
Mobile App → BLE UART → SIU → Vehicle Bus → Connected Components
```

The SIU connects to the cloud via the vehicle's cellular modem. When BLE and cloud are both available, the app prefers the cloud path.

### Protobuf Message Types

The vehicle communication uses Protocol Buffers for structured messages. Key message types discovered in the app bundle:

#### Vehicle Data
| Message | Purpose |
|---------|---------|
| `ConnectedComponent` | Single device on vehicle bus |
| `ConnectedComponents` | Collection of all components |
| `ConnectedComponentControls` | Control commands for a component |
| `ConnectedComponentSettings` | Configuration for a component |
| `ConnectedComponentValue` / `Values` | Sensor and state values |
| `NonCommunicatingComponents` | Offline/unreachable components |

#### Device Management
| Message | Purpose |
|---------|---------|
| `DeviceTwin` | Azure IoT-style device twin |
| `DeviceInfo` / `DeviceInfoPatch` | Mobile device registration |
| `MobileDevices` | List of registered mobile devices |

#### Telemetry & Diagnostics
| Message | Purpose |
|---------|---------|
| `Telemetry` / `Telemetries` | Live telemetry data |
| `DiagnosticsData` / `DiagnosticsDataItem` | Diagnostic information |
| `SystemEvent` / `SystemEvents` | System event log |
| `Statistic` / `Statistics` | Usage statistics |

#### Automation & Notifications
| Message | Purpose |
|---------|---------|
| `Scenario` / `Scenarios` | Automation scenarios (scenes) |
| `ScenarioResult` / `ScenarioType` | Scenario execution results |
| `Notification` / `NotificationSubscriptions` | Push notification management |
| `AlarmType` | Alarm definitions |

### App Login Flow (Observed via PCAPdroid)

The complete network flow during a fresh login, in order:

| Step | Domain | Bytes Sent | Bytes Received | Purpose |
|------|--------|-----------|---------------|---------|
| 1 | `firebaseinstallations.googleapis.com` | 1.7 KB | 5.2 KB | Firebase SDK init |
| 2 | `firebase-settings.crashlytics.com` | 1.5 KB | 6.1 KB | Crashlytics config |
| 3 | `api2.branch.io` | — | — | Branch.io analytics |
| 4 | `config.mapbox.com` | 3.7 KB | 6.0 KB | Mapbox maps config |
| 5 | `distributions.crowdin.net` | 5.1 KB | 443.8 KB | Translation strings download |
| 6 | **`smartrv.erwinhymergroup.com`** | **4.5 KB** | **14.8 KB** | **Auth + config** |
| 7 | **`scc-api.smartrv.erwinhymergroup.com`** | **11.2 KB** | **14.4 KB** | **REST API calls** |
| 8 | **`scc-rvtwin.smartrv.erwinhymergroup.com`** | **2.7 KB** | **429.0 KB** | **Vehicle twin data** |
| 9 | `firebaselogging-pa.googleapis.com` | 2.5 KB | 5.9 KB | Firebase event logging |

### Firebase (NOT Used for Authentication)

The app includes Firebase SDKs but does **not** use Firebase for primary authentication:

| Property | Value |
|----------|-------|
| Firebase project | `smart-caravan-ddde6` |
| Firebase API key | `AIzaSyA1raPCBXULGkXVIBHjkDTI1IWJuDX9D9k` |
| Firebase DB URL | `https://smart-caravan-ddde6.firebaseio.com` |
| Password login | **DISABLED** at project level |

Firebase is used only for: Crashlytics (crash reporting), Analytics, Remote Config, and Installations.

### Key Terminology

| Term | Description |
|------|-------------|
| **SIU** | Smart Interface Unit — central vehicle gateway module |
| **SCU** | Smart Control Unit (older term for SIU) |
| **CSNG** | Internal platform codename (SiuFactoryCsngHttpApi, SccHttpApi) |
| **EHG** | Erwin Hymer Group |
| **Connected Component** | Any device on the vehicle bus (heaters, fridges, lights, etc.) |
| **DataHub** | SignalR hub for real-time cloud communication |
| **RV Twin** | Digital twin representation of the vehicle |
| **PIA** | Platform Integration API (internal) |
| **FOTA** | Firmware Over The Air |
| **BOS Battery** | Battery management system brand |
| **WWL** | Wireless Water Level sensor |

### Source App Analysis

This integration was reverse-engineered from:
- **HYMER Connect** Android app v2.10.14 (`com.ehg.hymerconnect`)
- React Native app with Hermes bytecode engine (compiled JS, ~13 MB)
- Nordic Semiconductor BLE stack for local SIU communication
- Microsoft SignalR (`@microsoft/signalr`) for real-time cloud communication
- Protocol Buffers for structured vehicle messages
- OkHttp for HTTP networking
- Web app SPA at `smartrv.erwinhymergroup.com` (React + Vite, provided the auth endpoint discovery)
- Azure infrastructure: API Management, SignalR Service, Spring Boot backend (nginx/1.25.1)

## Development Status

- [x] API base URL discovered
- [x] Auth endpoint discovered (`/api/v2/oauth/token` with HTTP Basic Auth)
- [x] Authentication tested successfully (returns access_token + refresh_token)
- [x] Integration skeleton (config flow, coordinator, sensors, binary sensors)
- [x] HA integration login works — device created with entities
- [x] Vehicle info via REST API (`/api/v2/assets`)
- [x] Account info via REST API (`/api/v2/accounts/me`)
- [x] Reauth flow support
- [x] Dashboard YAML
- [x] SignalR WebSocket connection + authentication working
- [ ] **🔴 SignalR hub method name for sensor data** ← CURRENT BLOCKER
- [ ] Actual sensor data mapping to entities
- [ ] Climate control entities (heater target temperature)
- [ ] Switch entities (lights, USB, water pump)
- [ ] Cover entities (awning, roof, dome)
- [ ] SignalR real-time push updates
- [ ] Device tracker (GPS location)

## Contributing

This project needs help with **reverse engineering the SignalR protocol**. See the [SignalR DataHub section](#signalr-datahub-real-time-communication) above for details.

**What's working:**
- OAuth2 authentication ✅
- REST API for vehicle/account info ✅
- SignalR WebSocket connection ✅

**What's blocked:**
- The exact SignalR hub method name the app uses to request sensor data from the SIU
- The method name is compiled into Hermes bytecode v96 and cannot be extracted as a plain string
- 40+ method names have been tested — all return "Method does not exist"

**Tools needed:**
- Hermes bytecode v96 decompiler (hbctool only supports up to v90)
- Or: Frida on a rooted Android device to hook `HubConnection.invoke()`
- Or: iOS app analysis (may have readable JavaScript)

If you have an EHG vehicle and can help, please open an issue!

## License

This project is not affiliated with or endorsed by the Erwin Hymer Group.
