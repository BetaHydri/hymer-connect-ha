"""Light platform for HYMER Connect — controllable interior lights."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityDescription,
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
class HymerLightEntityDescription(LightEntityDescription):
    bus_id: int
    on_off_path: str
    brightness_path: str | None = None
    color_temp_path: str | None = None


LIGHT_DESCRIPTIONS: tuple[HymerLightEntityDescription, ...] = (
    HymerLightEntityDescription(
        key="light_living_ceiling",
        translation_key="light_living_ceiling",
        bus_id=11,
        on_off_path="signalr_sensors.light_living_ceiling",
        brightness_path="signalr_sensors.light_living_ceiling_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerLightEntityDescription(
        key="light_living_ambient",
        translation_key="light_living_ambient",
        bus_id=12,
        on_off_path="signalr_sensors.light_living_ambient",
        brightness_path="signalr_sensors.light_living_ambient_brightness",
        color_temp_path="signalr_sensors.light_living_ambient_color_temp",
        icon="mdi:wall-sconce-flat",
    ),
    HymerLightEntityDescription(
        key="light_kitchen",
        translation_key="light_kitchen",
        bus_id=21,
        on_off_path="signalr_sensors.light_kitchen",
        brightness_path="signalr_sensors.light_kitchen_brightness",
        color_temp_path="signalr_sensors.light_kitchen_color_temp",
        icon="mdi:ceiling-light",
    ),
    HymerLightEntityDescription(
        key="light_seating_overhead",
        translation_key="light_seating_overhead",
        bus_id=43,
        on_off_path="signalr_sensors.light_seating_overhead",
        brightness_path="signalr_sensors.light_seating_overhead_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerLightEntityDescription(
        key="light_bedroom_ambient",
        translation_key="light_bedroom_ambient",
        bus_id=15,
        on_off_path="signalr_sensors.light_bedroom_ambient",
        icon="mdi:wall-sconce-flat",
    ),
    HymerLightEntityDescription(
        key="light_nightlight",
        translation_key="light_nightlight",
        bus_id=16,
        on_off_path="signalr_sensors.light_nightlight",
        icon="mdi:lightbulb-night",
    ),
    HymerLightEntityDescription(
        key="light_bathroom_ceiling",
        translation_key="light_bathroom_ceiling",
        bus_id=19,
        on_off_path="signalr_sensors.light_bathroom_ceiling",
        brightness_path="signalr_sensors.light_bathroom_ceiling_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerLightEntityDescription(
        key="light_bedroom_overhead",
        translation_key="light_bedroom_overhead",
        bus_id=44,
        on_off_path="signalr_sensors.light_bedroom_overhead",
        brightness_path="signalr_sensors.light_bedroom_overhead_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerLightEntityDescription(
        key="light_wohnen_group",
        translation_key="light_wohnen_group",
        bus_id=24,
        on_off_path="signalr_sensors.light_outside",
        icon="mdi:lightbulb-group",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectLight(coordinator, desc, entry)
        for desc in LIGHT_DESCRIPTIONS
    )


class HymerConnectLight(
    CoordinatorEntity[HymerConnectCoordinator], LightEntity
):
    entity_description: HymerLightEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerLightEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"HYMER {entry.title}",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        modes = set()
        if description.brightness_path:
            modes.add(ColorMode.BRIGHTNESS)
        else:
            modes.add(ColorMode.ONOFF)
        self._attr_supported_color_modes = modes
        self._attr_color_mode = ColorMode.BRIGHTNESS if ColorMode.BRIGHTNESS in modes else ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        val = _resolve_path(self.coordinator.data, self.entity_description.on_off_path)
        if val is None:
            return None
        return bool(val)

    @property
    def brightness(self) -> int | None:
        if not self.entity_description.brightness_path:
            return None
        if self.coordinator.data is None:
            return None
        val = _resolve_path(
            self.coordinator.data, self.entity_description.brightness_path
        )
        if val is None or not isinstance(val, (int, float)):
            return None
        return min(255, max(0, int(val * 255 / 100)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control light - SignalR not connected")
            return
        bus = self.entity_description.bus_id
        if ATTR_BRIGHTNESS in kwargs:
            pct = min(100, max(0, int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
            await client.send_light_command(bus, 2, uint_value=pct)
        await client.send_light_command(bus, 1, bool_value=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control light - SignalR not connected")
            return
        bus = self.entity_description.bus_id
        await client.send_light_command(bus, 1, bool_value=False)
        await self.coordinator.async_request_refresh()
