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
STALE_DATA_TIMEOUT = 10 * 60  # 10 min — no data = connection is likely dead


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
    ) -> None:
        """Initialize the SignalR client."""
        self._api = api
        self._session = session
        self._vehicle_urn = vehicle_urn
        self._scu_urn = scu_urn
        self._ehg_refresh_token = ehg_refresh_token  # Long-lived refresh token (ett=access-refresh)
        self._on_sensor_update = on_sensor_update
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._sensor_data: dict[str, Any] = {}
        self._connected = False
        self._signalr_token: str = ""
        self._connected_at: float = 0.0  # monotonic timestamp of connection
        self._last_data_received: float = 0.0  # monotonic timestamp of last data

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
        if self._last_data_received > 0:
            silent = now - self._last_data_received
            if silent > STALE_DATA_TIMEOUT:
                _LOGGER.warning(
                    "No SignalR data for %.0fs — connection likely dead",
                    silent,
                )
                return True
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

    async def resubscribe(self) -> None:
        """Re-send PIA subscriptions to trigger fresh sensor data from the SCU.

        The SCU only pushes updated values in response to subscription
        requests.  Without periodic re-subscribing, many sensors (battery SOC,
        solar current, fuel range, etc.) stay at their initial cached values.
        """
        if not self._ws or self._ws.closed or not self._connected:
            return

        requests = build_subscription_requests()
        _LOGGER.debug("Re-sending %d PiaRequest subscriptions", len(requests))
        for payload in requests:
            await self.send_pia_request(payload)

        # Send refresh command on resubscribe too
        refresh = build_refresh_command()
        await self.send_pia_request(refresh)

    async def _send_update_tokens(self) -> None:
        """Send UpdateTokens invocation to authenticate the SignalR connection.

        Uses the EHG refresh token (ett=access-refresh) to obtain a fresh
        short-lived access token (ett=access) via the remoteAccessToken API,
        then sends it in the UpdateTokens invocation.
        """
        if not self._ws:
            return

        access = self._api.access_token
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

        # Exchange refresh token for a fresh short-lived access token
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

        # Wait for completion response
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
                if self._on_sensor_update:
                    self._on_sensor_update(self._sensor_data)

    async def listen(self) -> None:
        """Listen for incoming messages on the WebSocket."""
        if not self._ws:
            return

        self._running = True
        _LOGGER.info("SignalR listen loop started for %s", self._vehicle_urn)
        msg_count = 0
        try:
            async for msg in self._ws:
                if not self._running:
                    break
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
                            # Respond to ping with ping
                            await self._ws.send_str(
                                json.dumps({"type": MSG_TYPE_PING})
                                + SIGNALR_RECORD_SEPARATOR
                            )
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
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.warning(
                        "SignalR WebSocket closed/error after %d messages", msg_count
                    )
                    break
        except Exception:
            _LOGGER.warning(
                "SignalR listen loop exception after %d messages",
                msg_count,
                exc_info=True,
            )
        finally:
            _LOGGER.warning(
                "SignalR listen loop ended after %d messages — will reconnect on next poll",
                msg_count,
            )
            self._connected = False
            self._running = False

    async def send_pia_request(self, b64_payload: str) -> None:
        """Send a PiaRequest message to the SCU."""
        if not self._ws or self._ws.closed:
            _LOGGER.warning("Cannot send PiaRequest — not connected")
            return

        msg = {
            "arguments": [b64_payload],
            "target": "PiaRequest",
            "type": MSG_TYPE_INVOCATION,
        }
        await self._ws.send_str(
            json.dumps(msg) + SIGNALR_RECORD_SEPARATOR
        )

    async def send_light_command(
        self,
        bus_id: int,
        sensor_id: int,
        *,
        bool_value: bool | None = None,
        uint_value: int | None = None,
        str_value: str | None = None,
    ) -> None:
        """Send a light/switch control command to the SCU.

        Args:
            bus_id: Bus ID (e.g. 11 for living ceiling, 3 for main switch).
            sensor_id: 1=on/off, 2=brightness, 3=color_temp.
            bool_value: True/False for on/off.
            uint_value: 0-100 for brightness/color_temp.
            str_value: String value (e.g. "On"/"Off" for main switch).
        """
        payload = build_light_command(
            bus_id, sensor_id,
            bool_value=bool_value, uint_value=uint_value, str_value=str_value,
        )
        _LOGGER.info(
            "Sending light command: bus=%d sid=%d bool=%s uint=%s str=%s",
            bus_id, sensor_id, bool_value, uint_value, str_value,
        )
        await self.send_pia_request(payload)

    async def send_multi_sensor_command(
        self,
        sensors: list[dict],
    ) -> None:
        """Send a multi-sensor command to the SCU.

        Args:
            sensors: List of sensor dicts with bus_id, sensor_id, and value.
        """
        payload = build_multi_sensor_command(sensors)
        _LOGGER.info(
            "Sending multi-sensor command: %s",
            [(s.get("bus_id"), s.get("sensor_id")) for s in sensors],
        )
        await self.send_pia_request(payload)

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
