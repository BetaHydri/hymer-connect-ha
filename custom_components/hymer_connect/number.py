"""Number platform for HYMER Connect — integer-valued SCU controls."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HymerNumberEntityDescription(NumberEntityDescription):
    """Describe a HYMER Connect number control."""

    bus_id: int
    sensor_id: int
    value_path: str


NUMBER_DESCRIPTIONS: tuple[HymerNumberEntityDescription, ...] = (
    # Fridge cooling level (1..5). The SCU encodes this as a uint step value
    # and the app's picker only exposes the integer steps, so restrict the
    # HA entity to that range with step=1.
    HymerNumberEntityDescription(
        key="fridge_level_ctrl",
        translation_key="fridge_level_ctrl",
        bus_id=34,
        sensor_id=3,
        value_path="signalr_sensors.fridge_level",
        native_min_value=1,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:fridge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect number entities from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectNumber(coordinator, desc, entry)
        for desc in NUMBER_DESCRIPTIONS
    )


class HymerConnectNumber(
    CoordinatorEntity[HymerConnectCoordinator], NumberEntity
):
    """Representation of a HYMER Connect numeric control."""

    entity_description: HymerNumberEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerNumberEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"HYMER {entry.title}",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic_value: float | None = None

    @property
    def native_value(self) -> float | None:
        """Return the current value, optimistic or from the coordinator."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        if self.coordinator.data is None:
            return None
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the SCU."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning(
                "Cannot set %s — SignalR not connected",
                self.entity_description.key,
            )
            return
        int_value = int(round(value))
        await client.send_light_command(
            self.entity_description.bus_id,
            self.entity_description.sensor_id,
            uint_value=int_value,
        )
        self._optimistic_value = float(int_value)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once the SCU confirms the commanded value."""
        if self._optimistic_value is not None and self.coordinator.data:
            value = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            if value is not None:
                try:
                    actual = float(value)
                except (TypeError, ValueError):
                    actual = None
                if actual is not None and actual == self._optimistic_value:
                    self._optimistic_value = None
        super()._handle_coordinator_update()
