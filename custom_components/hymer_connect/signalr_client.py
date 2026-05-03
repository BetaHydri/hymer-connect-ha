"""SignalR client for the HYMER Connect datahub.

Connects to Azure SignalR Service via the scc-appcomm negotiate endpoint
and exchanges PiaRequest/PiaResponse messages over WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

import aiohttp

from .api import HymerConnectApi, HymerConnectApiError
from .const import USER_AGENT
from .pia_decoder import build_subscription_requests, decode_pia_payload, build_light_command, build_multi_sensor_command, build_refresh_command

_LOGGER = logging.getLogger(__name__)

# SignalR protocol constants
SIGNALR_RECORD_SEPARATOR = "\x1e"
MSG_TYPE_INVOCATION = 1
MSG_TYPE_COMPLETION = 3
MSG_TYPE_PING = 6

# Connection health constants
MAX_CONNECTION_AGE = 50 * 60  # 50 min — reconnect before Azure token expires (~1h)
STALE_DATA_TIMEOUT = 3 * 60   # 3 min — no data = connection is likely dead
STANDBY_MAX_SILENCE = 30 * 60  # 30 min — even in standby, reconnect after this

# UpdateTokens refresh — the ehgAccessToken sent via UpdateTokens expires
# after ~30 min.  Without periodic refresh, remote-access commands (lights,
# heater, fridge) are silently rejected while system commands (12V switch)
# keep working.  The EHG app works around this by creating a fresh connection
# every time it opens.  We refresh UpdateTokens proactively instead.
UPDATE_TOKENS_INTERVAL = 15 * 60  # 15 min — refresh well before 30 min expiry

# WebSocket keepalive — detect dead connections faster than STALE_DATA_TIMEOUT
KEEPALIVE_INTERVAL = 30  # seconds between client-side pings
KEEPALIVE_TIMEOUT = 90   # seconds with zero WebSocket activity = connection dead


class HymerSignalRClient:
    """SignalR WebSocket client for the HYMER datahub."""

    def __init__(
        self,
        api: HymerConnectApi,
        session: aiohttp.ClientSession,
        vehicle_urn: str,
        scu_urn: str,
        ehg_refresh_token: str = "",
        on_sensor_update: Callable[[dict[str, Any]], None] | None = None,
        on_connection_lost: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the SignalR client."""
        self._api = api
        self._session = session
        self._vehicle_urn = vehicle_urn
        self._scu_urn = scu_urn
        self._ehg_refresh_token = ehg_refresh_token  # Long-lived refresh token (ett=access-refresh)
        self._on_sensor_update = on_sensor_update
        self._on_connection_lost = on_connection_lost
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._sensor_data: dict[str, Any] = {}
        self._connected = False
        self._signalr_token: str = ""
        self._connected_at: float = 0.0  # monotonic timestamp of connection
        self._last_data_received: float = 0.0  # monotonic timestamp of last data
        self._last_send_failed: bool = False
        self._last_update_tokens: float = 0.0  # monotonic timestamp of last UpdateTokens
        self._scu_was_disconnected: bool = False  # tracks scu_connected false→true transitions

    @property
    def connected(self) -> bool:
        """Return True if the WebSocket is connected and healthy."""
        if not self._connected or not self._ws or self._ws.closed:
            return False
        return True

    @property
    def needs_reconnect(self) -> bool:
        """Return True if the connection should be proactively recycled."""
        if not self._connected:
            return False
        now = time.monotonic()
        # Reconnect before Azure SignalR token expires
        age = now - self._connected_at
        if age > MAX_CONNECTION_AGE:
            _LOGGER.info(
                "SignalR connection age %.0fs exceeds max %ds — reconnect needed",
                age, MAX_CONNECTION_AGE,
            )
            return True
        # Detect dead connection (no data received for a long time)
        # BUT: skip this check when the 12V main switch is off (SCU standby).
        # In standby, the SCU stops streaming sensor data but the WebSocket
        # stays open for commands. Recycling during standby would trigger
        # exponential backoff and lose the connection. See issue #45.
        #
        # Safety cap: even in standby, force reconnect after STANDBY_MAX_SILENCE.
        # If the connection died during a 12V ON toggle (SCU wakes up, socket breaks
        # but main_switch in sensor_data is still "Off"), the stale-data check
        # would never trigger without this cap. See issue #46.
        if self._last_data_received > 0:
            main_switch = self._sensor_data.get("main_switch")
            is_standby = main_switch == "Off"
            silent = now - self._last_data_received
            if silent > STALE_DATA_TIMEOUT and not is_standby:
                _LOGGER.warning(
                    "No SignalR data for %.0fs — connection likely dead",
                    silent,
                )
                return True
            if silent > STANDBY_MAX_SILENCE and is_standby:
                _LOGGER.warning(
                    "No data for %.0fs even in standby — forcing reconnect (safety cap)",
                    silent,
                )
                return True
            if silent > STALE_DATA_TIMEOUT and is_standby:
                _LOGGER.debug(
                    "No data for %.0fs but 12V is off (standby) — keeping connection alive",
                    silent,
                )
        return False

    @property
    def sensor_data(self) -> dict[str, Any]:
        """Return the latest sensor data."""
        return self._sensor_data

    async def connect(self) -> None:
        """Establish the SignalR WebSocket connection."""
        # Step 1: Negotiate with scc-appcomm to get Azure SignalR URL + token
        try:
            negotiate1 = await self._api.signalr_negotiate()
        except HymerConnectApiError as err:
            _LOGGER.error("SignalR negotiate (step 1) failed: %s", err)
            raise

        azure_url = negotiate1.get("url")
        signalr_token = negotiate1.get("accessToken")

        _LOGGER.info(
            "SignalR negotiate (step 1): url=%s, hasToken=%s, keys=%s",
            bool(azure_url),
            bool(signalr_token),
            list(negotiate1.keys()) if isinstance(negotiate1, dict) else "not-dict",
        )

        if not azure_url or not signalr_token:
            raise HymerConnectApiError(
                "SignalR negotiate did not return url/accessToken"
            )

        self._signalr_token = signalr_token

        # Step 2: Negotiate with Azure SignalR to get connectionToken
        negotiate2_url = azure_url.replace("client/?", "client/negotiate?")
        headers = {
            "Authorization": f"Bearer {signalr_token}",
            "X-Requested-With": "XMLHttpRequest",
            "X-SignalR-User-Agent": (
                "Microsoft SignalR/6.0 "
                "(6.0.25; Unknown OS; Browser; Unknown Runtime Version)"
            ),
            "Content-Type": "text/plain;charset=UTF-8",
            "User-Agent": USER_AGENT,
        }

        try:
            async with self._session.post(
                negotiate2_url, headers=headers, data=""
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise HymerConnectApiError(
                        f"SignalR negotiate (step 2) failed: {resp.status} {text[:200]}"
                    )
                negotiate2 = await resp.json()
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"SignalR negotiate (step 2) error: {err}") from err

        connection_token = negotiate2.get("connectionToken")
        if not connection_token:
            raise HymerConnectApiError(
                "SignalR negotiate (step 2) did not return connectionToken"
            )

        # Step 3: Build WebSocket URL and connect
        ws_url = azure_url.replace("https://", "wss://")
        ws_url += f"&id={connection_token}&access_token={signalr_token}"

        try:
            self._ws = await self._session.ws_connect(
                ws_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Origin": azure_url.split("/client/")[0],
                },
            )
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"WebSocket connect failed: {err}") from err

        # Step 4: Send protocol handshake
        handshake = json.dumps({"protocol": "json", "version": 1})
        await self._ws.send_str(handshake + SIGNALR_RECORD_SEPARATOR)

        # Wait for handshake response
        msg = await self._ws.receive(timeout=10)
        if msg.type != aiohttp.WSMsgType.TEXT:
            raise HymerConnectApiError(f"Unexpected handshake response: {msg.type}")

        _LOGGER.info("SignalR handshake accepted")

        # Step 5: Send UpdateTokens
        try:
            await self._send_update_tokens()
        except Exception:
            _LOGGER.warning("UpdateTokens failed, continuing without it")

        self._connected = True
        self._connected_at = time.monotonic()
        self._last_data_received = time.monotonic()
        self._last_update_tokens = time.monotonic()
        self._scu_was_disconnected = False
        _LOGGER.info("SignalR connected to datahub for %s", self._vehicle_urn)

        # Step 6: Send PiaRequest subscription to start receiving sensor data
        try:
            await self._send_subscription()
        except Exception:
            _LOGGER.warning("PiaRequest subscription failed", exc_info=True)

    async def _send_subscription(self) -> None:
        """Send PiaRequest messages to subscribe to all sensor data from the SCU."""
        if not self._ws or self._ws.closed:
            return

        requests = build_subscription_requests()
        _LOGGER.info("Sending %d PiaRequest subscriptions", len(requests))
        for payload in requests:
            await self.send_pia_request(payload)

        # Send refresh command to force SCU to push fresh states
        # (like EHG app's "aktualisiere" on startup)
        refresh = build_refresh_command()
        _LOGGER.info("Sending refresh command to force SCU state update")
        await self.send_pia_request(refresh)

    async def send_refresh(self) -> None:
        """Send a lightweight refresh command to keep SCU data flowing.

        The SCU stops pushing sensor data after ~2-3 minutes of silence.
        This single-message refresh (field 9 = poll) prods the SCU to
        re-report all current values without the overhead of re-sending
        all 7 subscription requests.

        Also periodically refreshes UpdateTokens (every UPDATE_TOKENS_INTERVAL)
        to keep the ehgAccessToken valid.
        """
        if not self._ws or self._ws.closed or not self._connected:
            return

        # Periodically refresh UpdateTokens to prevent ehgAccessToken expiry
        token_age = time.monotonic() - self._last_update_tokens
        if token_age >= UPDATE_TOKENS_INTERVAL:
            _LOGGER.info(
                "UpdateTokens age %.0fs exceeds %ds — refreshing",
                token_age,
                UPDATE_TOKENS_INTERVAL,
            )
            try:
                await self._send_update_tokens(wait_response=False)
                self._last_update_tokens = time.monotonic()
            except Exception:
                _LOGGER.warning("Periodic UpdateTokens refresh failed", exc_info=True)

        refresh = build_refresh_command()
        await self.send_pia_request(refresh)

    async def resubscribe(self) -> None:
        """Re-send full PIA subscriptions + refresh to reinitialise all sensor groups.

        Heavier than send_refresh() — sends all 7 subscription requests plus
        a refresh command.  Use sparingly (every 10 min) to avoid excessive
        traffic that can cause server-side disconnects.
        """
        if not self._ws or self._ws.closed or not self._connected:
            return

        requests = build_subscription_requests()
        _LOGGER.debug("Re-sending %d PiaRequest subscriptions", len(requests))
        for payload in requests:
            await self.send_pia_request(payload)

        refresh = build_refresh_command()
        await self.send_pia_request(refresh)

    async def _refresh_tokens_and_resubscribe(self) -> None:
        """Re-send UpdateTokens + resubscribe after SCU reconnect.

        Called when scu_connected transitions false→true (12V OFF→ON).
        The SCU wakes from standby and registers a new session at the Azure
        SignalR hub. Without re-sending UpdateTokens, the hub's routing table
        is stale and remote-access commands (lights, heater, fridge) are
        silently rejected — while the 12V system command keeps working.
        """
        if not self._ws or self._ws.closed or not self._connected:
            return

        # Settle: let the SCU finish its boot sequence and register a
        # fresh session at the Azure SignalR hub.  3s is conservative —
        # observed SCU wake-up takes 2-3s before stable PiaResponses.
        await asyncio.sleep(3)

        try:
            await self._send_update_tokens(wait_response=False)
            self._last_update_tokens = time.monotonic()
            _LOGGER.info("UpdateTokens refreshed after SCU reconnect")
        except Exception:
            _LOGGER.warning(
                "UpdateTokens refresh after SCU reconnect failed",
                exc_info=True,
            )
            return

        # CRITICAL: wait for UpdateTokens routing to propagate server-side
        # before subscribing.  Without this delay, PiaRequest subscriptions
        # (and any subsequent set_value commands) can be processed under
        # the stale standby routing → SCU never sees them, requires reload.
        # Observed completion latency is 50-100ms; 750ms gives generous
        # margin without noticeably delaying first sensor data.
        await asyncio.sleep(0.75)

        # Re-subscribe to get fresh sensor data from the woken SCU
        try:
            await self._send_subscription()
            _LOGGER.info("Resubscribed after SCU reconnect")
        except Exception:
            _LOGGER.warning(
                "Resubscribe after SCU reconnect failed", exc_info=True
            )

    async def _send_update_tokens(self, wait_response: bool = True) -> None:
        """Send UpdateTokens invocation to authenticate the SignalR connection.

        Uses the EHG refresh token (ett=access-refresh) to obtain a fresh
        short-lived access token (ett=access) via the remoteAccessToken API,
        then sends it in the UpdateTokens invocation.

        Args:
            wait_response: If True, wait for the completion response from the
                server (used during initial connect when the listen loop is not
                running).  If False, fire-and-forget — the listen loop will
                receive the completion message (used during periodic refresh
                and SCU-reconnect re-auth while the listen loop is active).
        """
        if not self._ws:
            return

        scu = self._scu_urn
        vehicle = self._vehicle_urn

        if not self._ehg_refresh_token:
            _LOGGER.warning(
                "No EHG refresh token configured — cannot authenticate SignalR. "
                "Provide the EHG Remote Access Refresh Token in the integration config."
            )
            return

        if not vehicle:
            _LOGGER.warning("No vehicle URN — cannot request remote access token")
            return

        # Exchange refresh token for a fresh short-lived access token.
        # This call goes through _request() which auto-refreshes the OAuth2
        # access token on 401.  We read api.access_token AFTER this call
        # to ensure we get the refreshed value.
        try:
            ehg_access_token = await self._api.get_remote_access_token(
                vehicle, self._ehg_refresh_token
            )
            _LOGGER.info(
                "Obtained fresh EHG access token (len=%d) for %s",
                len(ehg_access_token),
                vehicle,
            )
        except HymerConnectApiError as err:
            _LOGGER.error("Failed to get remote access token: %s", err)
            return

        # Read OAuth2 access token AFTER get_remote_access_token() — it may
        # have been refreshed during the API call (401 → auto-refresh).
        access = self._api.access_token

        args = {
            "accessToken": access,
            "ehgAccessToken": ehg_access_token,
            "vehicleUrn": vehicle,
            "scuUrn": scu,
        }

        msg = {
            "arguments": [args],
            "invocationId": "0",
            "target": "UpdateTokens",
            "type": MSG_TYPE_INVOCATION,
        }
        _LOGGER.info("Sending UpdateTokens for %s", vehicle)
        await self._ws.send_str(
            json.dumps(msg) + SIGNALR_RECORD_SEPARATOR
        )

        if not wait_response:
            _LOGGER.info("UpdateTokens sent (fire-and-forget, listen loop will handle response)")
            return

        # Wait for completion response (only during initial connect)
        async for raw_msg in self._ws:
            if raw_msg.type == aiohttp.WSMsgType.TEXT:
                for part in raw_msg.data.split(SIGNALR_RECORD_SEPARATOR):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        parsed = json.loads(part)
                    except json.JSONDecodeError:
                        continue
                    if parsed.get("type") == MSG_TYPE_COMPLETION:
                        result_data = parsed.get("result", {})
                        error = parsed.get("error")
                        if error:
                            _LOGGER.error("UpdateTokens failed: %s", error)
                        else:
                            response = (
                                result_data.get("response", {})
                                if isinstance(result_data, dict)
                                else {}
                            )
                            status = response.get("status", "UNKNOWN")
                            if status in ("OK", "SUCCESS", "ACCEPTED"):
                                _LOGGER.info(
                                    "UpdateTokens SUCCESS for %s", vehicle
                                )
                            else:
                                _LOGGER.error(
                                    "UpdateTokens failed: status=%s", status
                                )
                        return
                    if parsed.get("type") == MSG_TYPE_INVOCATION:
                        _LOGGER.info(
                            "Got invocation during UpdateTokens: target=%s",
                            parsed.get("target"),
                        )
                        self._handle_message(parsed)
                        return
            elif raw_msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                _LOGGER.warning("WebSocket closed during UpdateTokens")
                return
            break

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle an incoming SignalR message."""
        msg_type = msg.get("type")

        if msg_type == MSG_TYPE_PING:
            return

        # Handle UpdateTokens completion responses (fire-and-forget mode)
        if msg_type == MSG_TYPE_COMPLETION:
            error = msg.get("error")
            result_data = msg.get("result", {})
            if error:
                _LOGGER.error("UpdateTokens completion: error=%s", error)
            else:
                response = (
                    result_data.get("response", {})
                    if isinstance(result_data, dict)
                    else {}
                )
                status = response.get("status", "UNKNOWN")
                if status in ("OK", "SUCCESS", "ACCEPTED"):
                    _LOGGER.info("UpdateTokens completion: SUCCESS")
                else:
                    _LOGGER.warning("UpdateTokens completion: status=%s", status)
            return

        target = msg.get("target", "")
        args = msg.get("arguments", [])

        _LOGGER.debug(
            "SignalR message: type=%s target=%s args_count=%d raw=%s",
            msg_type,
            target,
            len(args),
            json.dumps(msg, default=str)[:300],
        )

        if target == "PiaResponse" and args:
            b64_payload = args[0] if isinstance(args[0], str) else ""
            if b64_payload:
                sensor_data = decode_pia_payload(b64_payload)
                self._sensor_data.update(sensor_data)
                self._last_data_received = time.monotonic()
                _LOGGER.debug(
                    "PiaResponse: %d fields updated, keys=%s",
                    len(sensor_data),
                    list(sensor_data.keys())[:20],
                )

                # Detect SCU reconnect (scu_connected false→true).
                # After 12V OFF→ON the SCU wakes from standby and gets a new
                # session at the Azure SignalR hub.  Our old UpdateTokens
                # routing becomes stale → remote-access commands (lights,
                # heater, fridge) are silently rejected.  Re-sending
                # UpdateTokens + resubscribe restores command delivery
                # immediately.
                if "scu_connected" in sensor_data:
                    scu_now = sensor_data["scu_connected"]
                    if scu_now is True and self._scu_was_disconnected:
                        _LOGGER.info(
                            "SCU reconnected (scu_connected false→true) — "
                            "re-sending UpdateTokens + resubscribe"
                        )
                        self._scu_was_disconnected = False
                        asyncio.ensure_future(self._refresh_tokens_and_resubscribe())
                    elif scu_now is False:
                        self._scu_was_disconnected = True
                        _LOGGER.info("SCU disconnected (scu_connected=false)")

                if self._on_sensor_update:
                    self._on_sensor_update(self._sensor_data)

    async def listen(self) -> None:
        """Listen for incoming messages on the WebSocket.

        Uses a receive-with-timeout loop to send periodic keepalive pings
        and detect dead connections within KEEPALIVE_TIMEOUT seconds,
        instead of hanging forever on a half-open socket.
        """
        if not self._ws:
            return

        self._running = True
        _LOGGER.info("SignalR listen loop started for %s", self._vehicle_urn)
        msg_count = 0
        last_activity = time.monotonic()
        last_ping_sent = time.monotonic()
        try:
            while self._running and self._ws and not self._ws.closed:
                now = time.monotonic()

                # Check inactivity timeout — no data at all means dead
                if now - last_activity > KEEPALIVE_TIMEOUT:
                    _LOGGER.warning(
                        "No WebSocket activity for %.0fs — connection dead",
                        now - last_activity,
                    )
                    break

                # Send client-side keepalive ping periodically.
                # This also detects dead sockets fast: writing to a broken
                # TCP connection raises immediately.
                if now - last_ping_sent >= KEEPALIVE_INTERVAL:
                    try:
                        await self._ws.send_str(
                            json.dumps({"type": MSG_TYPE_PING})
                            + SIGNALR_RECORD_SEPARATOR
                        )
                        last_ping_sent = now
                    except Exception:
                        _LOGGER.warning(
                            "Failed to send keepalive ping — connection dead"
                        )
                        break

                # Wait for next message with timeout
                try:
                    msg = await asyncio.wait_for(
                        self._ws.receive(), timeout=KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    continue  # loop back to check timeout + send ping

                last_activity = time.monotonic()

                if msg.type == aiohttp.WSMsgType.TEXT:
                    for part in msg.data.split(SIGNALR_RECORD_SEPARATOR):
                        part = part.strip()
                        if not part:
                            continue
                        try:
                            parsed = json.loads(part)
                        except json.JSONDecodeError:
                            continue
                        if parsed.get("type") == MSG_TYPE_PING:
                            # Respond to server ping
                            try:
                                await self._ws.send_str(
                                    json.dumps({"type": MSG_TYPE_PING})
                                    + SIGNALR_RECORD_SEPARATOR
                                )
                            except Exception:
                                _LOGGER.warning(
                                    "Failed to respond to server ping — "
                                    "connection dead"
                                )
                                break
                        else:
                            msg_count += 1
                            try:
                                self._handle_message(parsed)
                            except Exception:
                                _LOGGER.warning(
                                    "Error handling SignalR message #%d",
                                    msg_count,
                                    exc_info=True,
                                )
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    _LOGGER.info(
                        "SignalR WebSocket closed after %d messages",
                        msg_count,
                    )
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.warning(
                        "SignalR WebSocket error after %d messages",
                        msg_count,
                    )
                    break
        except Exception:
            _LOGGER.warning(
                "SignalR listen loop exception after %d messages",
                msg_count,
                exc_info=True,
            )
        finally:
            _LOGGER.info(
                "SignalR listen loop ended after %d messages — "
                "requesting immediate reconnect",
                msg_count,
            )
            self._connected = False
            self._running = False
            # Notify coordinator to reconnect immediately instead of
            # waiting for the next poll interval + backoff.
            if self._on_connection_lost:
                self._on_connection_lost()

    async def send_pia_request(self, b64_payload: str) -> bool:
        """Send a PiaRequest message to the SCU.

        Returns True if the message was sent, False on failure.
        """
        if not self._ws or self._ws.closed:
            _LOGGER.warning("Cannot send PiaRequest — not connected")
            return False

        msg = {
            "arguments": [b64_payload],
            "target": "PiaRequest",
            "type": MSG_TYPE_INVOCATION,
        }
        try:
            await self._ws.send_str(
                json.dumps(msg) + SIGNALR_RECORD_SEPARATOR
            )
            return True
        except Exception:
            _LOGGER.error(
                "Failed to send PiaRequest — marking connection as dead for reconnect",
                exc_info=True,
            )
            self._connected = False
            self._last_send_failed = True
            return False

    async def send_light_command(
        self,
        bus_id: int,
        sensor_id: int,
        *,
        bool_value: bool | None = None,
        uint_value: int | None = None,
        str_value: str | None = None,
    ) -> bool:
        """Send a light/switch control command to the SCU.

        Args:
            bus_id: Bus ID (e.g. 11 for living ceiling, 3 for main switch).
            sensor_id: 1=on/off, 2=brightness, 3=color_temp.
            bool_value: True/False for on/off.
            uint_value: 0-100 for brightness/color_temp.
            str_value: String value (e.g. "On"/"Off" for main switch).

        Returns True if sent successfully, False on failure.
        """
        payload = build_light_command(
            bus_id, sensor_id,
            bool_value=bool_value, uint_value=uint_value, str_value=str_value,
        )
        # Note: despite the function name, this is a generic single-slot
        # set_value writer used by lights, switches, the fridge controller
        # (bus 34), the main switch, water pump, etc. The vehicle simply
        # receives a PiaRequest.set_value targeting (bus_id, sensor_id) —
        # the SCU routes it to the correct module based on bus_id.
        _LOGGER.info(
            "Sending set_value command: bus=%d sid=%d bool=%s uint=%s str=%s",
            bus_id, sensor_id, bool_value, uint_value, str_value,
        )
        return await self.send_pia_request(payload)

    async def send_multi_sensor_command(
        self,
        sensors: list[dict],
    ) -> bool:
        """Send a multi-sensor command to the SCU.

        Args:
            sensors: List of sensor dicts with bus_id, sensor_id, and value.

        Returns True if sent successfully, False on failure.
        """
        payload = build_multi_sensor_command(sensors)
        _LOGGER.info(
            "Sending multi-sensor command: %s",
            [(s.get("bus_id"), s.get("sensor_id")) for s in sensors],
        )
        return await self.send_pia_request(payload)

    async def start(self) -> None:
        """Connect and start listening in the background."""
        await self.connect()
        self._task = asyncio.ensure_future(self.listen())

    async def stop(self) -> None:
        """Stop listening and close the WebSocket."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        self._task = None
        _LOGGER.debug("SignalR client stopped")
