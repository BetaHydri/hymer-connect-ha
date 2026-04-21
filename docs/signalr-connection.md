# SignalR Connection Architecture

> **Last updated:** 2026-04-21 (v2.23.0)

This document explains how the HYMER Connect integration maintains its real-time
connection to the vehicle SCU (Smart Connectivity Unit) through Azure SignalR Service.
It covers the connection lifecycle, token management, reconnection logic, and lessons
learned from production issues.

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
- **EHG remote access token**: Refreshed every 15 min via `resubscribe()` → `_send_update_tokens()`

## Connection Lifecycle

### Normal Operation

```
connect → listen loop (receives PiaResponse messages)
                ↕ send commands (PiaRequest for lights, heater, etc.)
                ↕ resubscribe every 10 min (refresh stale sensor values)
                ↕ UpdateTokens every 15 min (keep EHG access token valid)
    ~50 min → proactive disconnect (before negotiate JWT expires)
                → reconnect (new negotiate → new WebSocket → new subscriptions)
```

The connection is **proactively recycled every 50 minutes** (`MAX_CONNECTION_AGE = 50 * 60`)
to avoid hitting the Azure SignalR JWT expiry (~1 hour). This is by design and produces
expected log messages:

```
SignalR connection lost — scheduling immediate reconnect
SignalR connected for urn:ehg:vehicle:...
```

### Standby Mode (12V Off)

When the 12V main switch is off, the SCU enters standby:
- The WebSocket stays open but no sensor data is pushed
- The stale-data timeout (`STALE_DATA_TIMEOUT = 3 min`) is **skipped** to avoid
  unnecessary reconnections during standby
- A safety cap (`STANDBY_MAX_SILENCE = 30 min`) forces reconnect even in standby
  to handle edge cases (e.g., 12V toggled back ON but `main_switch` sensor still cached as "Off")

### SCU Reconnect (12V Off → On)

When 12V is toggled back ON, the SCU reboots and registers a new session at Azure SignalR.
The integration detects this via `scu_connected` transitioning `false → true` and automatically:
1. Re-sends UpdateTokens (refreshes routing at the hub)
2. Re-subscribes to all sensor data
3. Waits 2 seconds for SCU boot before acting

Without this, commands are silently rejected because the hub's routing table points
to the old SCU session.

## Reconnection Logic

### Trigger Sources

| Trigger | Handler | Backoff |
|---------|---------|---------|
| WebSocket closed/error | `_on_connection_lost()` | Reset to 60s |
| No WebSocket activity for 90s | Keepalive timeout in `listen()` | Reset to 60s |
| Connection age > 50 min | `needs_reconnect` property | Immediate |
| Send failure | `_send_with_retry()` | Immediate (1 retry) |

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

### Message Breakdown (v2.23.0)

| Source | Frequency | Messages | Per Hour |
|--------|-----------|----------|----------|
| PIA resubscribe | Every 10 min | 7 + 1 refresh | ~48 |
| UpdateTokens refresh | Every 15 min | 1 | ~4 |
| Client keepalive ping | Every 30s | 1 | ~120 |
| Server pings (responded to) | Variable | ~1/min | ~60 |
| **Total outbound** | | | **~232** |

### Previous Traffic (pre-v2.23.0) — Caused Disconnects

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

> **Do not poll/resubscribe more frequently than the mobile app.**
> The SCU pushes state changes automatically after the initial subscription.
> Resubscribe only refreshes slow-changing values (battery SOC, solar current)
> that the SCU doesn''t push proactively. 10-minute intervals are sufficient.

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

### Why Not Use the HA Poll Interval for Resubscribe?

The HA coordinator polls every 60s for REST metadata updates. Initially, we piggybacked
PIA resubscriptions on this poll — sending 8 messages every 60s. This caused server-side
disconnects after 4-5 hours. The fix was decoupling resubscribe to its own 10-minute timer.

### Why Fire-and-Forget for Periodic UpdateTokens?

During initial connect, we wait for the UpdateTokens completion response. During periodic
refresh (every 15 min), we use fire-and-forget because the listen loop is already running
and will receive the completion message. Waiting would block the coordinator poll.

### Why Detect SCU Reconnect via `scu_connected`?

When 12V is toggled OFF→ON, the SCU reboots and gets a new session at Azure SignalR.
Our existing WebSocket stays open (it''s connected to the Azure hub, not directly to the SCU),
but the hub''s routing table now points to the SCU''s new session. Without re-sending
UpdateTokens, our commands go to the old (dead) session and are silently dropped.

## File Reference

| File | Role |
|------|------|
| `coordinator.py` | Connection lifecycle, reconnection backoff, command routing |
| `signalr_client.py` | WebSocket management, PIA protocol, keepalive, listen loop |
| `api.py` | OAuth2 auth, token refresh, SignalR negotiate, REST API |
| `pia_decoder.py` | Protobuf encode/decode for PIA sensor data and commands |
| `const.py` | Timing constants, API URLs, header names |
