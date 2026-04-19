"""Switch platform for HYMER Connect — controllable switches."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
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
class HymerSwitchEntityDescription(SwitchEntityDescription):
    """Describe a HYMER Connect switch."""

    bus_id: int
    sensor_id: int
    value_path: str
    on_value: Any = True


SWITCH_DESCRIPTIONS: tuple[HymerSwitchEntityDescription, ...] = (
    HymerSwitchEntityDescription(
        key="main_switch_ctrl",
        translation_key="main_switch_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=3,
        sensor_id=1,
        value_path="signalr_sensors.main_switch",
        on_value="On",
        icon="mdi:power",
    ),
    HymerSwitchEntityDescription(
        key="water_pump_ctrl",
        translation_key="water_pump_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=3,
        sensor_id=3,
        value_path="signalr_sensors.charger_active",
        on_value=True,
        icon="mdi:water-pump",
    ),
    HymerSwitchEntityDescription(
        key="fridge_eco_ctrl",
        translation_key="fridge_eco_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=34,
        sensor_id=2,
        value_path="signalr_sensors.fridge_eco",
        on_value=True,
        icon="mdi:leaf",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect switches from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectSwitch(coordinator, desc, entry)
        for desc in SWITCH_DESCRIPTIONS
    )


class HymerConnectSwitch(
    CoordinatorEntity[HymerConnectCoordinator], SwitchEntity
):
    """Representation of a HYMER Connect switch."""

    entity_description: HymerSwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerSwitchEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        if self._optimistic_on is not None:
            return self._optimistic_on
        if self.coordinator.data is None:
            return None
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return None
        return value == self.entity_description.on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control switch - SignalR not connected")
            return
        await client.send_light_command(
            self.entity_description.bus_id,
            self.entity_description.sensor_id,
            bool_value=True,
        )
        self._optimistic_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control switch - SignalR not connected")
            return
        await client.send_light_command(
            self.entity_description.bus_id,
            self.entity_description.sensor_id,
            bool_value=False,
        )
        self._optimistic_on = False
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when SCU confirms the commanded value."""
        if self._optimistic_on is not None and self.coordinator.data:
            value = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            if value is not None:
                actual = value == self.entity_description.on_value
                if actual == self._optimistic_on:
                    self._optimistic_on = None
        super()._handle_coordinator_update()
