"""Binary sensor platform for HYMER Connect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path


@dataclass(frozen=True, kw_only=True)
class HymerBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a HYMER Connect binary sensor."""

    value_path: str
    """Dot-separated path into the coordinator data dict."""

    on_value: Any = True
    """Value that represents the 'on' state."""


BINARY_SENSOR_DESCRIPTIONS: tuple[HymerBinarySensorEntityDescription, ...] = (
    HymerBinarySensorEntityDescription(
        key="siu_online",
        translation_key="siu_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="sensors.siu.online",
        icon="mdi:access-point",
    ),
    HymerBinarySensorEntityDescription(
        key="mains_power",
        translation_key="mains_power",
        device_class=BinarySensorDeviceClass.PLUG,
        value_path="sensors.mainsPower.connected",
        icon="mdi:power-plug",
    ),
    HymerBinarySensorEntityDescription(
        key="door_open",
        translation_key="door_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="sensors.door.open",
        icon="mdi:door",
    ),
    HymerBinarySensorEntityDescription(
        key="window_open",
        translation_key="window_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_path="sensors.window.open",
        icon="mdi:window-open",
    ),
    HymerBinarySensorEntityDescription(
        key="alarm_active",
        translation_key="alarm_active",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_path="sensors.alarm.active",
        icon="mdi:alarm-light",
    ),
    HymerBinarySensorEntityDescription(
        key="heater_running",
        translation_key="heater_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_path="sensors.heater.running",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="fridge_running",
        translation_key="fridge_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_path="sensors.fridge.running",
        icon="mdi:fridge",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect binary sensors from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[HymerConnectBinarySensor] = [
        HymerConnectBinarySensor(coordinator, description, entry)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HymerConnectBinarySensor(
    CoordinatorEntity[HymerConnectCoordinator], BinarySensorEntity
):
    """Representation of a HYMER Connect binary sensor."""

    entity_description: HymerBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerBinarySensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"HYMER {entry.title}",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        if self.coordinator.data is None:
            return None
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return None
        return value == self.entity_description.on_value
