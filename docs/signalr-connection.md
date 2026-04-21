# SignalR Connection Architecture

> **Last updated:** 2026-04-21 (v2.23.1)

This document explains how the HYMER Connect integration maintains its real-time
connection to the vehicle SCU (Smart Connectivity Unit) through Azure SignalR Service.
It covers the connection lifecycle, token management, reconnection logic, and lessons
learned from production issues.

> **Important — 12V Safety:** The integration **never** automatically switches the
> 12V main power on or off. All reconnects, refreshes, resubscribes, and backoff
> retries are purely **connection-level** operations — they only manage the WebSocket
> link to the cloud, no switch commands are sent. The 12V state only changes when
> the user explicitly toggles it via HA or the EHG app. This is critical because
> the 12V rail powers downstream devices (private router, local HA instance, etc.)
> that would drain the battery if left on unintentionally.

## Overview

```
Home Assistant
    └── coordinator.py (DataUpdateCoordinator, polls every 60s)
            └── signalr_client.py (WebSocket connection)
                    └── Azure SignalR Service (ehg-prod-signalr.service.signalr.net)
                            └── SCU in vehicle (Smart Connectivity Unit)
```

All sensor data and control commands flow through a single SignalR WebSocket
connection. There is no REST API for real-time data — the SCC REST API only
provides static metadata (VIN, model, URNs).

## Connection Establishment

The connection requires a **5-step handshake**:

1. **Negotiate step 1** — `POST scc-appcomm/datahub/negotiate` (no auth headers)
   Returns: Azure SignalR URL + short-lived JWT token (~1 hour)

2. **Negotiate step 2** — `POST {azure_url}/negotiate` with JWT bearer
   Returns: `connectionToken` for WebSocket URL

3. **WebSocket connect** — `wss://ehg-prod-signalr.service.signalr.net/client/?hub=datahub&id={connectionToken}&access_token={jwt}`

4. **Protocol handshake** — Send `{"protocol": "json", "version": 1}`

5. **UpdateTokens** — Send OAuth2 access token + EHG remote access token + vehicle/SCU URNs
   This authenticates the connection and enables data flow

6. **PIA subscription** — Send 7 protobuf-encoded PiaRequest messages to subscribe
   to all sensor groups, plus a refresh command to force initial state push

After step 6, the SCU starts pushing `PiaResponse` messages with sensor data.

## Token Types

The integration manages **4 different tokens** — confusing them causes silent failures:

| Token | Source | Lifetime | Used For |
|-------|--------|----------|----------|
| OAuth2 access token | `POST /api/v2/oauth/token` (ROPC) | ~1 hour | REST API calls, UpdateTokens `accessToken` field |
| OAuth2 refresh token | Same endpoint | Long-lived | Refreshing OAuth2 access token on 401 |
| SignalR negotiate JWT | `POST scc-appcomm/datahub/negotiate` | ~1 hour | WebSocket URL `access_token` parameter |
| EHG remote access token | `POST /api/ehg/v1/vehicles/{urn}/remoteAccessToken` | ~30 min | UpdateTokens `ehgAccessToken` field — required for remote commands |

### Token Refresh Strategy

- **OAuth2 access token**: Auto-refreshed on 401 responses via `_request()` retry
- **SignalR negotiate JWT**: Not refreshable — connection must be recycled before expiry
- **EHG remote access token**: Refreshed every 15 min via `send_refresh()` → `_send_update_tokens()`

## SCU Data Freshness

The SCU does **not** continuously push sensor data on its own. After the initial
subscription response, it goes silent within **2–3 minutes** unless periodically
prodded. Without prodding, the stale-data detector (`STALE_DATA_TIMEOUT = 3 min`)
triggers a reconnect — which is wasteful and causes unnecessary churn.

### Two-Tier Polling Strategy (v2.23.1+)

| Tier | Method | Frequency | Messages | Purpose |
|------|--------|-----------|----------|---------|
| **Lightweight refresh** | `send_refresh()` | Every 60s (each poll) | 1 | Prod SCU to re-report current values |
| **Full resubscribe** | `resubscribe()` | Every 10 min | 7 + 1 | Reinitialise all sensor groups |

The **refresh command** (protobuf field 9 = empty) is the same "aktualisiere" command
the EHG app sends when the user swipes between views (Dashboard, Licht, Wasser, etc.)
or pulls to refresh. Each view change triggers a single refresh to get fresh values.
It triggers a full state report from the SCU without the overhead of re-sending all
7 subscription requests.

The **full resubscribe** re-sends all 7 PIA subscription requests to ensure no sensor
group is missed (e.g., after a reconnect where the initial subscription partially failed).

### Why the SCU Goes Silent

> **Note:** This is an educated guess based on observed behaviour, not confirmed
> by Hymer/EHG documentation.

The SCU firmware implements a request/response model rather than continuous
streaming — likely to conserve the **cellular data plan** included with the
vehicle. The LTE data cost is covered by Hymer (not the owner), so the SCU
minimises upstream traffic by only reporting values when explicitly asked.

- **Event-driven values** (light toggled, door opened, 12V switched) are pushed immediately
- **Slow-changing values** (battery SOC, solar current, temperatures) are only reported in response to refresh/subscription requests
- Without periodic prodding, the SCU assumes no client is actively watching and stops sending data after ~2–3 minutes

## Connection Lifecycle

### Normal Operation

```
connect → listen loop (receives PiaResponse messages)
                ↕ send commands (PiaRequest for lights, heater, etc.)
                ↔ refresh every 60s (1 msg — prod SCU to push fresh data)
                ↔ full resubscribe every 10 min (8 msgs — reinit sensor groups)
                ↕ UpdateTokens every 15 min (keep EHG access token valid)
    ~50 min → proactive disconnect (before negotiate JWT expires)
                → reconnect (new negotiate → new WebSocket → new subscriptions)
```

The connection is **proactively recycled every 50 minutes** (`MAX_CONNECTION_AGE = 50 * 60`)
to avoid hitting the Azure SignalR JWT expiry (~1 hour). This is purely a
**connection-level** operation — no device commands (12V, lights, etc.) are sent
during reconnection. It produces expected log messages:

```
SignalR connection lost — scheduling immediate reconnect
SignalR connected for urn:ehg:vehicle:...
```

### Standby Mode (12V Off)

When the 12V main switch is off, the SCU enters standby:
- The WebSocket stays open but no sensor data is pushed
- The stale-data timeout (`STALE_DATA_TIMEOUT = 3 min`) is **skipped** to avoid
  unnecessary reconnections during standby
- A safety cap (`STANDBY_MAX_SILENCE = 30 min`) forces a **WebSocket reconnect**
  even in standby. This only re-establishes the SignalR connection — it does
  **NOT** send a 12V switch-on command. The 12V remains off until manually
  switched back on by the user (via HA or EHG app). The reconnect handles the
  edge case where 12V was physically toggled back ON at the vehicle but the
  `main_switch` sensor is still cached as "Off" in HA

### SCU Reconnect (12V Off → On)

When 12V is toggled back ON **by the user**, the SCU reboots and registers a new session at Azure SignalR.
The integration detects this via `scu_connected` transitioning `false → true` and automatically:
1. Re-sends UpdateTokens (refreshes routing at the hub)
2. Re-subscribes to all sensor data
3. Waits 2 seconds for SCU boot before acting

This is a **read-only** recovery — it restores command delivery and data flow but
does not send any switch commands. Without it, commands would be silently rejected
because the hub's routing table points to the old SCU session.

## Reconnection Logic

### Trigger Sources

| Trigger | Handler | Backoff | Sends commands? |
|---------|---------|---------|----------------|
| WebSocket closed/error | `_on_connection_lost()` | Reset to 60s | No — connection only |
| No WebSocket activity for 90s | Keepalive timeout in `listen()` | Reset to 60s | No — connection only |
| Connection age > 50 min | `needs_reconnect` property | Immediate | No — connection only |
| Send failure | `_send_with_retry()` | Immediate (1 retry) | Only retries the user''s command |

### Backoff Strategy

```
Failure 1: wait  60s
Failure 2: wait 120s
Failure 3: wait 240s
Failure 4: wait 480s
Failure 5: force OAuth2 token refresh, reset to 60s  ← hard reset
Failure 6: wait  60s (fresh cycle)
...
Cap: 900s (15 min) maximum between attempts
```

After **5 consecutive failures**, the integration assumes the OAuth2 token has expired
and forces a full token refresh before retrying. This prevents getting permanently stuck
in backoff when the auth state is stale.

### Command Retry (`_send_with_retry`)

All control commands (lights, heater, fridge, switches) use a 2-attempt strategy:

```
attempt 1: ensure_healthy → send → success? done
attempt 1: ensure_healthy → send → fail?
    → force reconnect
attempt 2: ensure_healthy → send → success? done
attempt 2: ensure_healthy → send → fail? → raise HomeAssistantError
```

This means **a single transient connection drop never causes a visible command failure** —
the user just sees a slightly delayed response.

## Traffic Budget

### Why Traffic Matters

The Azure SignalR Service (and/or the EHG backend) enforces connection limits.
Excessive message volume causes **server-side disconnects** without explicit error messages —
the WebSocket simply closes.

### Message Breakdown (v2.23.1)

| Source | Frequency | Messages | Per Hour |
|--------|-----------|----------|----------|
| PIA refresh (lightweight) | Every 60s | 1 | ~60 |
| PIA full resubscribe | Every 10 min | 7 + 1 refresh | ~48 |
| UpdateTokens refresh | Every 15 min | 1 | ~4 |
| Client keepalive ping | Every 30s | 1 | ~120 |
| Server pings (responded to) | Variable | ~1/min | ~60 |
| **Total outbound** | | | **~292** |

### v2.23.0 — Too Little Traffic (Caused Stale Data)

| Source | Frequency | Messages | Per Hour |
|--------|-----------|----------|----------|
| PIA resubscribe | Every 10 min | 7 + 1 refresh | ~48 |
| UpdateTokens refresh | Every 15 min | 1 | ~4 |
| Client keepalive ping | Every 30s | 1 | ~120 |
| **Total outbound** | | | **~172** |

The SCU went silent after ~3 min without prodding, triggering `STALE_DATA_TIMEOUT`
and unnecessary reconnects every ~10 min (matching the resubscribe interval).

### Pre-v2.23.0 — Too Much Traffic (Caused Server Disconnects)

| Source | Frequency | Messages | Per Hour |
|--------|-----------|----------|----------|
| PIA resubscribe | Every 60s | 7 + 1 refresh | **~480** |
| UpdateTokens refresh | Every 15 min | 1 | ~4 |
| Client keepalive ping | Every 30s | 1 | ~120 |
| **Total outbound** | | | **~604** |

The EHG mobile app sends subscriptions **once on connect** and never resubscribes.
Our previous 60s resubscribe was ~480× the app''s rate, which triggered disconnects
after 4-5 hours of continuous operation.

### Lesson Learned

> **The SCU needs regular prodding but not heavy resubscription.**
> A single lightweight refresh command (field 9) every 60 seconds is enough to
> keep data flowing. The full 7-subscription resubscribe should only run every
> 10 minutes. Sending all 8 messages every 60 seconds (~480/hr) triggers
> server-side disconnects; sending nothing for 10 minutes causes the SCU to
> go silent and triggers stale-data reconnects.

## Troubleshooting

### Symptom: "SignalR connection lost" every ~50 minutes

**This is normal.** The connection is proactively recycled before the Azure JWT expires.
Check that it''s followed by "SignalR connected for..." within a few seconds.

### Symptom: Connection drops and never reconnects

Check HA logs for:
- `"SignalR reconnect backoff: Xs remaining (attempt N/5)"` — backoff is active
- `"OAuth2 token refreshed after consecutive failures"` — hard reset triggered
- `"SignalR connection failed (N/5): ..."` — the actual error causing failures

**Common causes:**
1. **OAuth2 refresh token expired** — Re-authenticate by removing and re-adding the integration
2. **EHG servers down** — Check if the EHG app itself works
3. **Network issue** — Check HA''s internet connectivity

### Symptom: Commands sent from HA but nothing happens on vehicle

1. Check if SignalR is connected: look for recent "SignalR connected" in logs
2. Check UpdateTokens status: look for "UpdateTokens SUCCESS" or "UpdateTokens failed"
3. If UpdateTokens shows a non-OK status, the EHG remote access token may be expired
4. Try reloading the integration (Settings → Integrations → HYMER Connect → Reload)

### Symptom: Sensor data is stale / not updating

1. Check if 12V main switch is on (SCU stops pushing data in standby)
2. Check last "PIA re-subscription sent" log entry — should be within last 10 min
3. If no resubscription logs, the connection is likely dead — check reconnection logs

### Symptom: "Command failed after reconnect+retry"

The connection is fully broken and automatic recovery failed. Actions:
1. Reload the integration
2. If reload fails, check HA logs for auth errors
3. As last resort, remove and re-add the integration

## Architecture Decisions

### Why Proactive Connection Recycling?

Azure SignalR JWTs expire after ~1 hour. Rather than waiting for a mid-command
failure, we proactively disconnect at 50 minutes and reconnect with a fresh token.
This ensures commands always have a valid connection.

### Why Not Use the HA Poll Interval for Full Resubscribe?

The HA coordinator polls every 60s for REST metadata updates. Initially, we piggybacked
full PIA resubscriptions (8 messages) on this poll. This caused server-side
disconnects after 4-5 hours (~480 msgs/hr). Reducing to 10-min-only caused
the SCU to go silent after ~3 min. The solution is a **two-tier approach**:
lightweight refresh (1 msg) every poll, full resubscribe every 10 min.

### Why Fire-and-Forget for Periodic UpdateTokens?

During initial connect, we wait for the UpdateTokens completion response. During periodic
refresh (every 15 min), we use fire-and-forget because the listen loop is already running
and will receive the completion message. Waiting would block the coordinator poll.

### Why Detect SCU Reconnect via `scu_connected`?

When 12V is toggled OFF→ON **by the user**, the SCU reboots and gets a new session at Azure SignalR.
Our existing WebSocket stays open (it''s connected to the Azure hub, not directly to the SCU),
but the hub''s routing table now points to the SCU''s new session. Without re-sending
UpdateTokens, our commands go to the old (dead) session and are silently dropped.
Note: this recovery only restores the connection — it never sends switch commands.

### Why Does the Integration Never Auto-Switch 12V?

The 12V main switch controls the habitation power rail. When 12V is on, downstream
devices (private router, local HA instance, Truma heater standby, etc.) draw power
from the lithium battery. Automatically switching 12V on would cause unintended
battery drain when the owner is away. Therefore, all automatic operations in the
integration (reconnects, refreshes, resubscribes, backoff retries, SCU reconnect
detection) are strictly **connection-level** — they never send 12V or any other
switch/light/device commands.

## File Reference

| File | Role |
|------|------|
| `coordinator.py` | Connection lifecycle, reconnection backoff, command routing |
| `signalr_client.py` | WebSocket management, PIA protocol, keepalive, listen loop |
| `api.py` | OAuth2 auth, token refresh, SignalR negotiate, REST API |
| `pia_decoder.py` | Protobuf encode/decode for PIA sensor data and commands |
| `const.py` | Timing constants, API URLs, header names |
