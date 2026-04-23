"""Data update coordinator for HYMER Connect.

Uses the SCC REST API for vehicle metadata and SignalR for real-time sensor data.
The coordinator polls REST periodically and merges SignalR push data on arrival.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HymerConnectApi, HymerConnectApiError, HymerConnectAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, TANK_CAPACITY_LITERS
from .signalr_client import HymerSignalRClient

_LOGGER = logging.getLogger(__name__)

# Reconnection backoff constants
_INITIAL_BACKOFF = 60  # 1 minute
_MAX_BACKOFF = 900  # 15 minutes
_MAX_CONSECUTIVE_FAILURES = 5  # force re-auth after this many failures
_REST_METADATA_INTERVAL = 600  # 10 minutes between full REST metadata refreshes
_RESUBSCRIBE_INTERVAL = 600  # 10 minutes — only resubscribe periodically, not every poll

# Fuel consumption tracking
_FUEL_REFUEL_THRESHOLD_PCT = 5  # fuel increase > 5% = refueling detected
_FUEL_MIN_DISTANCE_KM = 5  # minimum distance before computing consumption


class HymerConnectCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching HYMER Connect data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: HymerConnectApi,
        session: aiohttp.ClientSession,
        entry: ConfigEntry,
        vehicle_urn: str = "",
        scu_urn: str = "",
        ehg_refresh_token: str = "",
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self._session = session
        self._vehicle_urn = vehicle_urn  # urn:ehg:vehicle:hy-XXXXXXXXXX
        self._scu_urn = scu_urn  # urn:ehg:scu:sXXX.XX.XX.XXX.XXX
        self._ehg_refresh_token = ehg_refresh_token  # BLE-derived refresh token
        self._signalr: HymerSignalRClient | None = None
        self._signalr_data: dict[str, Any] = {}
        self._reconnect_backoff: int = _INITIAL_BACKOFF
        self._last_reconnect_attempt: float = 0.0
        self._consecutive_failures: int = 0
        self._last_rest_metadata_refresh: float = 0.0
        self._last_resubscribe: float = 0.0
        self._cached_rest_data: dict[str, Any] = {}
        self._signalr_lock = asyncio.Lock()  # prevent concurrent reconnect attempts
        # Fuel consumption tracking — reference point for trip calculation
        self._fuel_ref_odo: float | None = None  # odometer at trip start (km)
        self._fuel_ref_level: float | None = None  # fuel level at trip start (%)
        self._fuel_consumption_l100: float | None = None  # current L/100km
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )

    @property
    def signalr_client(self) -> HymerSignalRClient | None:
        """Return the active SignalR client for sending commands."""
        return self._signalr

    def _on_signalr_update(self, sensor_data: dict[str, Any]) -> None:
        """Handle incoming SignalR sensor data."""
        self._signalr_data.update(sensor_data)
        self._compute_fuel_metrics()
        _LOGGER.debug(
            "SignalR push: %d total sensors", len(self._signalr_data)
        )
        # Trigger HA entity updates immediately
        self.async_set_updated_data({
            **(self.data or {}),
            "signalr_sensors": self._signalr_data,
        })

    def _compute_fuel_metrics(self) -> None:
        """Compute fuel consumption (L/100km) and range from odometer + fuel level.

        Uses a trip reference point (odo + fuel level at start).  When the fuel
        level increases by more than the refuel threshold, the reference resets
        (tank was filled up).  Consumption is only computed after at least
        _FUEL_MIN_DISTANCE_KM have been driven to avoid noisy readings.
        """
        odo = self._signalr_data.get("odometer")
        fuel_pct = self._signalr_data.get("fuel_level")

        if not isinstance(odo, (int, float)) or not isinstance(fuel_pct, (int, float)):
            return
        if odo <= 0 or fuel_pct < 0 or fuel_pct > 100:
            return

        fuel_liters = fuel_pct / 100.0 * TANK_CAPACITY_LITERS
        self._signalr_data["fuel_level_liters"] = round(fuel_liters, 1)

        # Initialize reference point on first valid reading
        if self._fuel_ref_odo is None or self._fuel_ref_level is None:
            self._fuel_ref_odo = odo
            self._fuel_ref_level = fuel_pct
            _LOGGER.debug("Fuel tracking initialized: odo=%.1f km, level=%.1f%%", odo, fuel_pct)
            return

        # Detect refueling: fuel level jumped up significantly
        if fuel_pct > self._fuel_ref_level + _FUEL_REFUEL_THRESHOLD_PCT:
            _LOGGER.info(
                "Refueling detected: %.1f%% → %.1f%% — resetting trip reference",
                self._fuel_ref_level, fuel_pct,
            )
            self._fuel_ref_odo = odo
            self._fuel_ref_level = fuel_pct
            return

        # Compute consumption when enough distance has been driven
        delta_km = odo - self._fuel_ref_odo
        delta_fuel_pct = self._fuel_ref_level - fuel_pct  # positive = fuel used

        if delta_km >= _FUEL_MIN_DISTANCE_KM and delta_fuel_pct > 0:
            fuel_used_liters = delta_fuel_pct / 100.0 * TANK_CAPACITY_LITERS
            consumption = fuel_used_liters / delta_km * 100.0
            # Sanity check: realistic diesel consumption is 5–40 L/100km for a Sprinter
            if 2.0 <= consumption <= 60.0:
                self._fuel_consumption_l100 = round(consumption, 1)
                self._signalr_data["fuel_consumption"] = self._fuel_consumption_l100
                _LOGGER.debug(
                    "Fuel consumption: %.1f L/100km (%.1f L over %.1f km)",
                    consumption, fuel_used_liters, delta_km,
                )

        # Compute estimated range
        if self._fuel_consumption_l100 and self._fuel_consumption_l100 > 0:
            est_range = fuel_liters / self._fuel_consumption_l100 * 100.0
            self._signalr_data["fuel_range_estimated"] = round(est_range, 0)


    def _on_signalr_connection_lost(self) -> None:
        """Handle SignalR connection loss — schedule immediate reconnect.

        Called from the listen loop's finally block when the WebSocket
        closes unexpectedly.  Resets backoff and triggers a coordinator
        refresh so `_async_update_data` reconnects within seconds instead
        of waiting for the next poll interval + exponential backoff.
        """
        _LOGGER.info("SignalR connection lost — scheduling immediate reconnect")
        self._reconnect_backoff = _INITIAL_BACKOFF
        self._last_reconnect_attempt = 0.0
        # Schedule an async coordinator refresh — listen loop runs on the
        # HA event loop (asyncio.ensure_future), so async_create_task is safe.
        self.hass.async_create_task(self.async_request_refresh())

    async def start_signalr(self) -> None:
        """Start the SignalR WebSocket connection.

        Uses an asyncio.Lock to prevent the race condition where both
        the connection-lost callback and the coordinator poll trigger
        concurrent reconnects, creating duplicate WebSocket connections
        with double the traffic (which Azure then throttles/drops).
        """
        if not self._scu_urn:
            _LOGGER.warning("No SCU URN — skipping SignalR")
            return

        if self._signalr_lock.locked():
            _LOGGER.debug("SignalR reconnect already in progress — skipping")
            return

        async with self._signalr_lock:
            # Re-check after acquiring the lock — another task may have
            # reconnected while we were waiting.
            if self._signalr and self._signalr.connected and not self._signalr.needs_reconnect:
                _LOGGER.debug("SignalR already connected (checked under lock)")
                return

            # Stop any existing dead/stale connection first
            if self._signalr:
                _LOGGER.info("Stopping stale SignalR client before reconnect")
                await self.stop_signalr()

            self._signalr = HymerSignalRClient(
                api=self.api,
                session=self._session,
                vehicle_urn=self._vehicle_urn,
                scu_urn=self._scu_urn,
                ehg_refresh_token=self._ehg_refresh_token,
                on_sensor_update=self._on_signalr_update,
                on_connection_lost=self._on_signalr_connection_lost,
            )

            try:
                await self._signalr.start()
                _LOGGER.info("SignalR connected for %s", self._vehicle_urn)
                # Reset backoff and failure counter on successful connection
                self._reconnect_backoff = _INITIAL_BACKOFF
                self._consecutive_failures = 0
            except HymerConnectApiError as err:
                self._consecutive_failures += 1
                _LOGGER.warning(
                    "SignalR connection failed (%d/%d): %s",
                    self._consecutive_failures, _MAX_CONSECUTIVE_FAILURES, err,
                )
                self._signalr = None

                # After too many consecutive failures, force OAuth2 token refresh
                if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    _LOGGER.warning(
                        "SignalR failed %d times in a row — forcing OAuth2 token refresh",
                        self._consecutive_failures,
                    )
                    try:
                        await self.api._refresh_access_token()
                        _LOGGER.info("OAuth2 token refreshed after consecutive failures")
                    except Exception:
                        _LOGGER.error("OAuth2 token refresh failed", exc_info=True)
                    self._consecutive_failures = 0
                    self._reconnect_backoff = _INITIAL_BACKOFF
                else:
                    # Increase backoff (exponential, capped)
                    self._reconnect_backoff = min(
                        self._reconnect_backoff * 2, _MAX_BACKOFF
                    )
                _LOGGER.info(
                    "Next SignalR reconnect attempt in %ds", self._reconnect_backoff
                )

    async def stop_signalr(self) -> None:
        """Stop the SignalR WebSocket connection."""
        if self._signalr:
            await self._signalr.stop()
            self._signalr = None

    async def async_ensure_signalr_healthy(self) -> None:
        """Ensure SignalR is connected and healthy, reconnecting if needed.

        Checks both the WebSocket connection state and whether the connection
        is stale (needs_reconnect).  If unhealthy, attempts to reconnect.
        Raises HomeAssistantError if reconnection fails.
        """
        client = self._signalr
        if client and client.connected and not client.needs_reconnect:
            return
        reason = "stale" if (client and client.connected) else "disconnected"
        _LOGGER.info("SignalR %s — reconnecting before command", reason)
        await self.start_signalr()
        if not self._signalr or not self._signalr.connected:
            raise HomeAssistantError(
                "Cannot send command — SignalR not connected. "
                "Try reloading the integration."
            )

    async def _send_with_retry(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> None:
        """Send a command with automatic reconnect + single retry.

        Args:
            method_name: Name of the method on HymerSignalRClient
                         (e.g. 'send_light_command').
            *args, **kwargs: Forwarded to the client method.

        Raises HomeAssistantError if both attempts fail.
        """
        for attempt in range(2):
            await self.async_ensure_signalr_healthy()
            method = getattr(self._signalr, method_name)
            ok = await method(*args, **kwargs)
            if ok:
                return
            if attempt == 0:
                _LOGGER.warning(
                    "%s send failed — reconnecting for retry", method_name
                )
                # Force disconnected state so ensure_healthy reconnects
                if self._signalr:
                    self._signalr._connected = False
        raise HomeAssistantError(
            "Command failed after reconnect+retry. "
            "Try reloading the integration."
        )

    async def async_send_light_command(
        self,
        bus_id: int,
        sensor_id: int,
        **kwargs: Any,
    ) -> None:
        """Send a light/switch command with reconnect + retry."""
        await self._send_with_retry(
            "send_light_command", bus_id, sensor_id, **kwargs
        )

    async def async_send_multi_sensor_command(
        self, sensors: list[dict]
    ) -> None:
        """Send a multi-sensor command with reconnect + retry."""
        await self._send_with_retry("send_multi_sensor_command", sensors)

    async def async_send_pia_request(
        self, payload: str
    ) -> None:
        """Send a raw PIA request with reconnect + retry."""
        await self._send_with_retry("send_pia_request", payload)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the REST API and merge with SignalR data."""
        now = time.monotonic()

        # Only refresh full REST metadata periodically (URNs, VIN, model are static)
        needs_metadata_refresh = (
            not self._cached_rest_data
            or (now - self._last_rest_metadata_refresh) > _REST_METADATA_INTERVAL
        )

        if needs_metadata_refresh:
            try:
                rest_data = await self.api.get_vehicle_status()
                self._cached_rest_data = rest_data
                self._last_rest_metadata_refresh = now
            except HymerConnectAuthError as err:
                raise ConfigEntryAuthFailed(
                    f"Authentication error: {err}"
                ) from err
            except HymerConnectApiError as err:
                raise UpdateFailed(
                    f"Error communicating with API: {err}"
                ) from err
        else:
            rest_data = dict(self._cached_rest_data)

        # Store URNs from REST data if not set yet
        if not self._scu_urn and rest_data.get("vehicle"):
            vehicle = rest_data["vehicle"]
            self._scu_urn = vehicle.get("smartUnitUrn", "")
            vin = vehicle.get("vin", "")
            _LOGGER.info("Discovered VIN=%s SCU=%s", vin, self._scu_urn)

        # Get vehicle URN (urn:ehg:vehicle:hy-...) from EHG API
        if not self._vehicle_urn and rest_data.get("vehicle_urn"):
            self._vehicle_urn = rest_data["vehicle_urn"]
            _LOGGER.info(
                "Discovered vehicle_urn=%s, scu_urn=%s",
                self._vehicle_urn,
                self._scu_urn,
            )

            # Persist URNs in config entry for next restart
            if self._vehicle_urn and self._scu_urn:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        "vehicle_urn": self._vehicle_urn,
                        "scu_urn": self._scu_urn,
                    },
                )

        if not self._scu_urn and self._vehicle_urn:
            self._scu_urn = self._vehicle_urn

        # --- SignalR connection management ---
        signalr_connected = (
            self._signalr is not None and self._signalr.connected
        )
        needs_reconnect = (
            self._signalr is not None and self._signalr.needs_reconnect
        )

        if not signalr_connected or needs_reconnect:
            # Apply exponential backoff between reconnection attempts
            since_last_attempt = now - self._last_reconnect_attempt
            if since_last_attempt >= self._reconnect_backoff:
                _LOGGER.info(
                    "SignalR %s (obj=%s, connected=%s, needs_reconnect=%s), attempting start",
                    "needs reconnect" if needs_reconnect else "not connected",
                    self._signalr is not None,
                    self._signalr.connected if self._signalr else "N/A",
                    needs_reconnect,
                )
                self._last_reconnect_attempt = now
                try:
                    await self.start_signalr()
                except Exception:
                    _LOGGER.warning("SignalR connect attempt failed", exc_info=True)
            else:
                remaining = self._reconnect_backoff - since_last_attempt
                _LOGGER.warning(
                    "SignalR reconnect backoff: %.0fs remaining (attempt %d/%d)",
                    remaining, self._consecutive_failures, _MAX_CONSECUTIVE_FAILURES,
                )
        else:
            # Send lightweight refresh every poll to keep SCU data flowing.
            # The SCU stops pushing data after ~2-3 min of silence.
            # This sends 1 message per poll (vs 8 for full resubscribe).
            try:
                await self._signalr.send_refresh()
            except Exception:
                _LOGGER.debug("PIA refresh failed", exc_info=True)

            # Full resubscribe less frequently — reinitialises all sensor
            # groups to pick up any missed subscriptions after reconnects.
            since_last_resub = now - self._last_resubscribe
            if since_last_resub >= _RESUBSCRIBE_INTERVAL:
                try:
                    await self._signalr.resubscribe()
                    self._last_resubscribe = now
                    _LOGGER.debug(
                        "Full PIA re-subscription sent (interval=%.0fs)",
                        since_last_resub,
                    )
                except Exception:
                    _LOGGER.debug("PIA re-subscription failed", exc_info=True)

        # Merge REST + SignalR data
        signalr_ok = self._signalr.connected if self._signalr else False
        _LOGGER.debug(
            "Data update: signalr_sensors=%d, signalr_connected=%s",
            len(self._signalr_data),
            signalr_ok,
        )
        rest_data["signalr_sensors"] = self._signalr_data
        return rest_data
