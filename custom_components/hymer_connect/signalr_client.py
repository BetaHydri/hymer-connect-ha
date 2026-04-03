"""SignalR client for the HYMER Connect datahub.

Connects to Azure SignalR Service via the scc-appcomm negotiate endpoint
and exchanges PiaRequest/PiaResponse messages over WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import aiohttp

from .api import HymerConnectApi, HymerConnectApiError
from .const import USER_AGENT
from .pia_decoder import decode_pia_payload

_LOGGER = logging.getLogger(__name__)

# SignalR protocol constants
SIGNALR_RECORD_SEPARATOR = "\x1e"
MSG_TYPE_INVOCATION = 1
MSG_TYPE_COMPLETION = 3
MSG_TYPE_PING = 6


class HymerSignalRClient:
    """SignalR WebSocket client for the HYMER datahub."""

    def __init__(
        self,
        api: HymerConnectApi,
        session: aiohttp.ClientSession,
        vehicle_urn: str,
        scu_urn: str,
        on_sensor_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the SignalR client."""
        self._api = api
        self._session = session
        self._vehicle_urn = vehicle_urn
        self._scu_urn = scu_urn
        self._on_sensor_update = on_sensor_update
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._sensor_data: dict[str, Any] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        """Return True if the WebSocket is connected."""
        return self._connected

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

        if not azure_url or not signalr_token:
            raise HymerConnectApiError(
                "SignalR negotiate did not return url/accessToken"
            )

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

        _LOGGER.debug("SignalR handshake accepted")

        # Step 5: Send UpdateTokens
        await self._send_update_tokens()
        self._connected = True
        _LOGGER.info("SignalR connected to datahub for %s", self._vehicle_urn)

    async def _send_update_tokens(self) -> None:
        """Send UpdateTokens invocation to authenticate the SignalR connection."""
        if not self._ws:
            return

        # Get ehgAccessToken via confirmation token
        ehg_access_token = ""
        try:
            result = await self._api.get_confirmation_token()
            ehg_access_token = result.get("token", "")
        except HymerConnectApiError:
            _LOGGER.warning("Could not get confirmation token for UpdateTokens")

        msg = {
            "arguments": [
                {
                    "accessToken": self._api.access_token,
                    "ehgAccessToken": ehg_access_token,
                    "vehicleUrn": self._vehicle_urn,
                    "scuUrn": self._scu_urn,
                }
            ],
            "invocationId": "0",
            "target": "UpdateTokens",
            "type": MSG_TYPE_INVOCATION,
        }
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
                        result = parsed.get("result", {})
                        response = result.get("response", {}) if isinstance(result, dict) else {}
                        status = response.get("status", "UNKNOWN")
                        _LOGGER.debug("UpdateTokens result: %s", status)
                        return
                    if parsed.get("type") == MSG_TYPE_INVOCATION:
                        # Got a PiaResponse before completion — process it
                        self._handle_message(parsed)
                        return
            elif raw_msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                raise HymerConnectApiError("WebSocket closed during UpdateTokens")

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle an incoming SignalR message."""
        msg_type = msg.get("type")

        if msg_type == MSG_TYPE_PING:
            return

        target = msg.get("target", "")
        args = msg.get("arguments", [])

        if target == "PiaResponse" and args:
            b64_payload = args[0] if isinstance(args[0], str) else ""
            if b64_payload:
                sensor_data = decode_pia_payload(b64_payload)
                self._sensor_data.update(sensor_data)
                _LOGGER.debug(
                    "PiaResponse: %d fields updated", len(sensor_data)
                )
                if self._on_sensor_update:
                    self._on_sensor_update(self._sensor_data)

    async def listen(self) -> None:
        """Listen for incoming messages on the WebSocket."""
        if not self._ws:
            return

        self._running = True
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
                            self._handle_message(parsed)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.warning("SignalR WebSocket closed/error")
                    break
        finally:
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
