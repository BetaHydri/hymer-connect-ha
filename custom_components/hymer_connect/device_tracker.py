"""Device tracker platform for HYMER Connect."""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect device tracker from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HymerDeviceTracker(coordinator, entry)])


class HymerDeviceTracker(
    CoordinatorEntity[HymerConnectCoordinator], TrackerEntity
):
    """Representation of the HYMER vehicle location."""

    _attr_has_entity_name = True
    _attr_name = "Location"
    _attr_icon = "mdi:rv-truck"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_device_tracker"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    @property
    def source_type(self) -> SourceType:
        """Return the source type (GPS)."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        return self._parse_coordinates()[0]

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        return self._parse_coordinates()[1]

    @property
    def extra_state_attributes(self) -> dict[str, str | float | None]:
        """Return extra attributes."""
        signalr = self._signalr_data()
        return {
            "altitude": signalr.get("gps_altitude"),
            "heading": signalr.get("gps_heading"),
            "satellites": signalr.get("gps_satellites"),
            "signal_quality": signalr.get("gps_signal_quality"),
        }

    def _signalr_data(self) -> dict:
        """Return the signalr_sensors dict safely."""
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get("signalr_sensors", {})

    def _parse_coordinates(self) -> tuple[float | None, float | None]:
        """Parse lat/lon from the gps_coordinates string 'lat,lon'."""
        gps_str = self._signalr_data().get("gps_coordinates")
        if not gps_str or not isinstance(gps_str, str):
            return (None, None)
        try:
            parts = gps_str.split(",")
            if len(parts) == 2:
                return (float(parts[0]), float(parts[1]))
        except (ValueError, IndexError):
            _LOGGER.debug("Could not parse GPS coordinates: %s", gps_str)
        return (None, None)
