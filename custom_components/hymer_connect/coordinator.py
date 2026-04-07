"""Data update coordinator for HYMER Connect.

Uses the SCC REST API for vehicle metadata and SignalR for real-time sensor data.
The coordinator polls REST periodically and merges SignalR push data on arrival.
"""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HymerConnectApi, HymerConnectApiError, HymerConnectAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .signalr_client import HymerSignalRClient

_LOGGER = logging.getLogger(__name__)

# Reconnection backoff constants
_INITIAL_BACKOFF = 60  # 1 minute
_MAX_BACKOFF = 900  # 15 minutes
_REST_METADATA_INTERVAL = 600  # 10 minutes between full REST metadata refreshes


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
        self._last_rest_metadata_refresh: float = 0.0
        self._cached_rest_data: dict[str, Any] = {}
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
        _LOGGER.debug(
            "SignalR push: %d total sensors", len(self._signalr_data)
        )
        # Trigger HA entity updates immediately
        self.async_set_updated_data({
            **(self.data or {}),
            "signalr_sensors": self._signalr_data,
        })

    async def start_signalr(self) -> None:
        """Start the SignalR WebSocket connection."""
        if not self._scu_urn:
            _LOGGER.warning("No SCU URN — skipping SignalR")
            return

        if self._signalr and self._signalr.connected and not self._signalr.needs_reconnect:
            _LOGGER.debug("SignalR already connected")
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
        )

        try:
            await self._signalr.start()
            _LOGGER.info("SignalR connected for %s", self._vehicle_urn)
            # Reset backoff on successful connection
            self._reconnect_backoff = _INITIAL_BACKOFF
        except HymerConnectApiError as err:
            _LOGGER.warning("SignalR connection failed: %s", err)
            self._signalr = None
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
                _LOGGER.debug(
                    "SignalR reconnect backoff: %.0fs remaining", remaining
                )
        else:
            # Re-send PIA subscriptions on every poll to get fresh sensor data.
            # The SCU only pushes updated values in response to subscription
            # requests — without re-subscribing, data goes stale.
            try:
                await self._signalr.resubscribe()
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
