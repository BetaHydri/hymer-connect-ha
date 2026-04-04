# HYMER Connect for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom integration to connect your HYMER / Erwin Hymer Group motorhome or caravan to [Home Assistant](https://www.home-assistant.io/).

> **Status:** v1.0.0 — Real-time sensor data via SignalR is fully working! 130+ sensors including odometer, GPS, battery, water levels, temperatures, door status, and more. Requires a one-time token extraction (see [Obtaining the EHG Refresh Token](#obtaining-the-ehg-refresh-token)).

![HYMER Connect Integration in Home Assistant](https://raw.githubusercontent.com/BetaHydri/hymer-connect-ha/master/images/ha-screenshot.png)

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
4. *(Optional but required for real-time sensors)* Paste your **EHG Remote Access Refresh Token** (see [Obtaining the EHG Refresh Token](#obtaining-the-ehg-refresh-token) below)
5. The integration will create sensor entities for your vehicle

> **Without the refresh token**, the integration still works but only provides REST API data (vehicle model, VIN, year). **With the refresh token**, you get 130+ real-time sensors via SignalR (battery, GPS, water levels, temperatures, door status, odometer, etc.).

## Obtaining the EHG Refresh Token

The HYMER Connect cloud requires a special **EHG Remote Access Refresh Token** to stream real-time sensor data. This token is created during the initial Bluetooth (BLE) pairing between your phone and your vehicle's Smart Interface Unit (SIU). It is stored inside the Hymer Connect app and never expires.

Since there is no public API to generate this token, you must capture it **once** from your phone's network traffic using a proxy tool. After that, the integration refreshes it automatically — no further action needed.

### What you need

- A **PC** (Windows, Mac, or Linux) on the same WiFi as your phone
- An **Android phone** with the HYMER Connect app (the phone you paired with your vehicle via Bluetooth)
- **mitmproxy** installed on the PC ([download](https://mitmproxy.org/))
- **apk-mitm** to patch the app for HTTPS interception ([GitHub](https://github.com/nicbarker/apk-mitm))
- ~15 minutes of your time

### Step-by-step guide

#### 1. Install mitmproxy on your PC

```bash
# Windows (winget)
winget install mitmproxy

# macOS (Homebrew)
brew install mitmproxy

# Linux (pip)
pip install mitmproxy
```

#### 2. Patch the HYMER Connect APK

The app uses certificate pinning, which blocks proxy interception. You need to patch the APK to disable this:

```bash
# Install apk-mitm (requires Node.js)
npm install -g apk-mitm

# Download the HYMER Connect APK from your phone or APKMirror
# Then patch it:
apk-mitm com.ehg.hymerconnect.apk
```

This creates a patched APK file (e.g., `com.ehg.hymerconnect-patched.apk`).

#### 3. Install the patched APK on your phone

1. Uninstall the original HYMER Connect app from your phone
2. Enable "Install from unknown sources" in Android settings
3. Transfer the patched APK to your phone and install it
4. **Log in** to the patched app with your HYMER Connect credentials

> **Important:** You do NOT need to re-pair via Bluetooth. The patched app reuses the BLE pairing tokens stored on your phone from the original app's pairing session.

#### 4. Start the proxy on your PC

Find your PC's local IP address:

```powershell
# Windows
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -match 'Wi-Fi|WLAN|Ethernet' }

# macOS / Linux
ifconfig | grep "inet "
```

Start mitmproxy:

```bash
mitmdump --mode regular --listen-port 8080 --set flow_detail=3 -w hymer_trace.flow
```

#### 5. Configure your phone to use the proxy

1. Go to **Settings → Wi-Fi** (or Connections → Wi-Fi)
2. Long-press your home WiFi network → **Modify network** / **Manage network settings**
3. Set Proxy to **Manual**
   - **Proxy hostname:** Your PC's IP address (e.g., `192.168.178.154`)
   - **Proxy port:** `8080`
4. Save

#### 6. Install the mitmproxy CA certificate

1. Open Chrome on your phone and navigate to **http://mitm.it**
2. Tap **Android** to download the certificate
3. Open the downloaded file and install it (Settings → Security → Install certificates)
4. Name it `mitmproxy`, select **VPN and apps**

#### 7. Capture the token

1. **Force-close** the HYMER Connect app (swipe away from recent apps)
2. **Open** the patched HYMER Connect app
3. Wait for it to load the vehicle dashboard with sensor data
4. **Wait ~10 seconds** for data to flow
5. Close the app

#### 8. Extract the token

Stop mitmproxy (`Ctrl+C`). Then extract the refresh token from the captured traffic:

```bash
python3 -c "
from mitmproxy.io import FlowReader
import json

with open('hymer_trace.flow', 'rb') as f:
    reader = FlowReader(f)
    for flow in reader.stream():
        if hasattr(flow, 'request') and 'remoteAccessToken' in flow.request.url:
            body = json.loads(flow.request.content.decode('utf-8'))
            print('=== YOUR EHG REFRESH TOKEN ===')
            print(body['token'])
            print()
            print('Copy the token above and paste it into the')
            print('HYMER Connect integration configuration in Home Assistant.')
            break
    else:
        print('Token not found in trace. Make sure the app loaded sensor data.')
"
```

The output will be a long JWT string starting with `eyJ...`. This is your **EHG Remote Access Refresh Token**.

#### 9. Add the token to Home Assistant

1. Go to **Settings → Devices & Services**
2. Find **HYMER Connect** and click **Configure** (or re-add the integration)
3. Paste the token into the **EHG Remote Access Refresh Token** field
4. Save — real-time sensor data will start flowing within seconds

#### 10. Restore your phone

1. Remove the WiFi proxy settings on your phone (set Proxy back to **None**)
2. *(Optional)* Uninstall the patched APK and reinstall the original from the Play Store
3. *(Optional)* Remove the mitmproxy CA certificate from your phone

### How it works (technical details)

During manufacturing, each vehicle's SCU (Smart Control Unit / SIU) is registered in the EHG cloud with its unique URN (e.g., `urn:ehg:scu:s481.01.00.013.970`). When a vehicle owner pairs their phone with the SCU via Bluetooth, the cloud issues a long-lived **refresh token** that is bound to the phone's BLE MAC address, the user's account, and the vehicle. This token proves that the user has physical access to the vehicle.

```mermaid
sequenceDiagram
    participant Factory as 🏭 Factory
    participant Cloud as ☁️ EHG Cloud
    participant SCU as 🚐 SCU (Vehicle)
    participant Phone as 📱 Phone (App)
    participant HA as 🏠 Home Assistant

    Note over Factory,Cloud: Vehicle manufacturing
    Factory->>Cloud: Register SCU (urn:ehg:scu:...)
    Factory->>SCU: Install SCU with cellular modem

    Note over SCU,Phone: One-time BLE pairing (at vehicle)
    Phone->>SCU: BLE connect + authenticate
    SCU->>Cloud: Validate pairing request
    Cloud->>Phone: Owner token (ett=owner, no expiry)
    Cloud->>Phone: Refresh token (ett=access-refresh, no expiry)
    Note over Phone: Tokens stored permanently in app

    Note over Phone,Cloud: Normal remote operation (from anywhere)
    Phone->>Cloud: POST /remoteAccessToken {refresh_token}
    Cloud->>Phone: Access token (ett=access, 15 min)
    Phone->>Cloud: SignalR UpdateTokens {accessToken, ehgAccessToken}
    Cloud->>SCU: Forward via SignalR ↔ cellular
    SCU->>Cloud: PiaResponse (sensor data)
    Cloud->>Phone: PiaResponse (battery, GPS, temps, water...)

    Note over Phone,HA: One-time token capture (mitmproxy)
    Phone-->>HA: User copies refresh token from traffic capture

    Note over HA,Cloud: Home Assistant integration (automatic)
    HA->>Cloud: POST /oauth/token (username + password)
    HA->>Cloud: POST /remoteAccessToken {refresh_token}
    Cloud->>HA: Fresh access token (auto-refreshed every 15 min)
    HA->>Cloud: SignalR connect + UpdateTokens
    Cloud->>HA: Real-time sensor data (130+ sensors)
```

The refresh token (`ett=access-refresh`) has **no expiry** — you only need to capture it once. The integration automatically exchanges it for fresh short-lived access tokens every 15 minutes.

| Token Type | `kid` prefix | `ett` | Expiry | Source |
|-----------|-------------|-------|--------|--------|
| OAuth2 access | — | — | 15 min | `POST /api/v2/oauth/token` |
| Confirmation | `confirmation-token-key` | `confirmation` | 15 min | `POST /accounts/confirmationToken` |
| Owner activation | `main-user-activation-token-key` | `owner` | Never | BLE pairing |
| **Remote access refresh** | **`remote-access-refresh-token-key`** | **`access-refresh`** | **Never** | **BLE pairing (this is what you capture)** |
| Remote access | `remote-access-token-key` | `access` | 15 min | `POST /vehicles/{urn}/remoteAccessToken` |

## Dashboard Setup

1. Go to **Settings → Dashboards → + Add Dashboard**
2. Open the new dashboard → Edit → three dots → **Raw configuration editor**
3. Paste the contents of [`dashboards/hymer_connect.yaml`](https://github.com/BetaHydri/hymer-connect-ha/blob/master/dashboards/hymer_connect.yaml)
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
| `smartrv.erwinhymergroup.com` | 20.4.141.205 | Authentication, SignalR negotiate |
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
    subgraph "EHG Cloud (Azure)"
        AUTH["smartrv.erwinhymergroup.com<br/>POST /api/v2/oauth/token<br/>(OAuth2 ROPC)"]
        RAT["smartrv.erwinhymergroup.com<br/>POST /vehicles/{urn}/remoteAccessToken<br/>(exchange refresh → access token)"]
        API["scc-api.smartrv.erwinhymergroup<br/>REST API data endpoints"]
        NEG["scc-appcomm<br/>/datahub/negotiate<br/>(no auth required)"]
        SRH["ehg-prod-signalr.service.signalr.net<br/>Azure SignalR Hub<br/>(WebSocket + UpdateTokens)"]
        REG[("SCU Registry<br/>Vehicle URNs<br/>BLE MAC bindings<br/>Token validation")]
    end

    subgraph "Vehicle"
        SIU["SIU / SCU<br/>(Smart Interface Unit)<br/>Cellular + BLE gateway"]
        BUS["Vehicle Bus<br/>(CAN, LIN)"]
        DEV["Truma · Dometic · Victron<br/>Sensors · Battery · TPMS<br/>Lights · Fridge · Heater"]
    end

    subgraph "Home Assistant"
        HA["HYMER Connect<br/>Integration v1.0.0"]
    end

    subgraph "One-time Setup"
        PHONE["📱 Phone (BLE paired)"]
        MITM["mitmproxy capture"]
    end

    %% Factory registration
    REG ---|"SCU registered<br/>at manufacturing"| SIU

    %% BLE pairing creates refresh token
    PHONE ---|"BLE pairing"| SIU
    REG ---|"validates pairing<br/>issues refresh token"| PHONE

    %% Token capture
    PHONE -->|"traffic capture"| MITM
    MITM -->|"refresh token<br/>(one-time copy)"| HA

    %% HA runtime flow
    HA -->|"① username + password"| AUTH
    AUTH -->|"access_token"| HA
    HA -->|"② refresh token"| RAT
    RAT -->|"ehgAccessToken<br/>(15 min)"| HA
    HA -->|"③ negotiate"| NEG
    NEG -->|"SignalR URL + JWT"| HA
    HA -->|"④ UpdateTokens"| SRH
    SRH <-->|"⑤ PiaRequest /<br/>PiaResponse"| SIU

    %% Vehicle internals
    SIU <-->|"cellular"| SRH
    SIU <--> BUS
    BUS <--> DEV

    %% REST API
    HA -->|"vehicle info"| API
    API --> REG
```

### SignalR DataHub (Real-Time Communication)

The SIU communicates with the cloud via an Azure SignalR Service hub. The integration uses the `@microsoft/signalr`-compatible JSON protocol.

| Property | Value |
|----------|-------|
| **Negotiate URL** | `POST https://scc-appcomm.smartrv.erwinhymergroup.com/datahub/negotiate?negotiateVersion=1` |
| **WebSocket URL** | `wss://ehg-prod-signalr.service.signalr.net/client/?hub=datahub` |
| **Protocol** | JSON (SignalR JSON protocol with `\x1e` delimiter) |
| **Auth for negotiate** | None (no auth headers — matches real app behavior) |
| **Auth for WebSocket** | JWT from negotiate response passed as `access_token` query parameter |

Connection states: `connecting` → `established` → `disconnected` (with auto-reconnect policy).

### Communication Paths

**Cloud Path** (used by this integration):
```
Home Assistant → OAuth2 auth → refresh token exchange → SignalR negotiate →
  WebSocket → UpdateTokens → PiaRequest/PiaResponse → 130+ real-time sensors
    ↕ (via Azure SignalR + cellular modem)
  SIU (vehicle) ↔ Vehicle Bus ↔ Sensors, Heater, Fridge, Battery, GPS, ...
```

**BLE Path** (used only for initial pairing, not used by this integration):
```
Mobile App → BLE UART → SIU → Vehicle Bus → Connected Components
  ↕ (during pairing, cloud issues refresh token bound to BLE MAC + user + vehicle)
```

The SIU connects to the cloud via the vehicle's cellular modem. When BLE and cloud are both available, the app prefers the cloud path. The integration uses the cloud path exclusively.

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
