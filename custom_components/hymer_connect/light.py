"""Light platform for HYMER Connect — controllable interior lights."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
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

# Color temperature range (Kelvin) for lights with color_temp_path
MIN_COLOR_TEMP_KELVIN = 2700  # warm white
MAX_COLOR_TEMP_KELVIN = 6500  # daylight


@dataclass(frozen=True, kw_only=True)
class HymerLightEntityDescription(LightEntityDescription):
    bus_id: int
    on_off_path: str
    brightness_path: str | None = None
    color_temp_path: str | None = None
    use_brightness_for_on_off: bool = False  # True = sid 1 is a group switch, use brightness to toggle


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
        brightness_path="signalr_sensors.light_bedroom_ambient_brightness",
        color_temp_path="signalr_sensors.light_bedroom_ambient_color_temp",
        use_brightness_for_on_off=True,  # sid=1 is group switch — skip it
        icon="mdi:wall-sconce-flat",
    ),
    HymerLightEntityDescription(
        key="light_nightlight",
        translation_key="light_nightlight",
        bus_id=16,
        on_off_path="signalr_sensors.light_nightlight",
        brightness_path="signalr_sensors.light_nightlight_brightness",
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
    HymerLightEntityDescription(
        key="light_privat_group",
        translation_key="light_privat_group",
        bus_id=15,
        on_off_path="signalr_sensors.light_bedroom_ambient",
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
        if description.color_temp_path:
            modes.add(ColorMode.COLOR_TEMP)
        elif description.brightness_path:
            modes.add(ColorMode.BRIGHTNESS)
        else:
            modes.add(ColorMode.ONOFF)
        self._attr_supported_color_modes = modes
        self._attr_color_mode = next(iter(modes))
        if description.color_temp_path:
            self._attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
            self._attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN
        self._optimistic_on: bool | None = None
        self._optimistic_brightness: int | None = None
        self._optimistic_color_temp: int | None = None

    @property
    def is_on(self) -> bool | None:
        if self._optimistic_on is not None:
            return self._optimistic_on
        if self.coordinator.data is None:
            return None
        if self.entity_description.use_brightness_for_on_off:
            # Bus 15: sid=1 is group switch, check brightness for individual state
            val = _resolve_path(
                self.coordinator.data, self.entity_description.brightness_path
            )
            if val is not None and isinstance(val, (int, float)):
                return val > 0
            # Fallback: check on_off_path
        val = _resolve_path(self.coordinator.data, self.entity_description.on_off_path)
        if val is None:
            return None
        return bool(val)

    @property
    def brightness(self) -> int | None:
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness
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

    @property
    def color_temp_kelvin(self) -> int | None:
        if self._optimistic_color_temp is not None:
            return self._optimistic_color_temp
        if not self.entity_description.color_temp_path:
            return None
        if self.coordinator.data is None:
            return None
        val = _resolve_path(
            self.coordinator.data, self.entity_description.color_temp_path
        )
        if val is None or not isinstance(val, (int, float)):
            return None
        return int(
            MIN_COLOR_TEMP_KELVIN
            + val * (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN) / 100
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control light - SignalR not connected")
            return
        bus = self.entity_description.bus_id
        if self.entity_description.use_brightness_for_on_off:
            # Don't send sid=1 (group switch) — use brightness to turn on
            if ATTR_BRIGHTNESS in kwargs:
                pct = min(100, max(0, int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
            else:
                pct = int((self.brightness or 255) * 100 / 255)
                if pct == 0:
                    pct = 100
                self._optimistic_on = True  # only for pure toggle
            await client.send_light_command(bus, 2, uint_value=pct)
            self._optimistic_brightness = min(255, max(1, int(pct * 255 / 100)))
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                ct_pct = min(100, max(0, int((kelvin - MIN_COLOR_TEMP_KELVIN) * 100 / (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN))))
                await client.send_light_command(bus, 3, uint_value=ct_pct)
                self._optimistic_color_temp = kelvin
            self.async_write_ha_state()
            # Don't schedule clear — keep optimistic state until next toggle
        else:
            # Normal lights: always send on (sid=1)
            await client.send_light_command(bus, 1, bool_value=True)
            self._optimistic_on = True
            if ATTR_BRIGHTNESS in kwargs and self.entity_description.brightness_path:
                pct = min(100, max(0, int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
                await client.send_light_command(bus, 2, uint_value=pct)
                self._optimistic_brightness = kwargs[ATTR_BRIGHTNESS]
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                pct = min(100, max(0, int((kelvin - MIN_COLOR_TEMP_KELVIN) * 100 / (MAX_COLOR_TEMP_KELVIN - MIN_COLOR_TEMP_KELVIN))))
                await client.send_light_command(bus, 3, uint_value=pct)
                self._optimistic_color_temp = kelvin
            self.async_write_ha_state()
            self._schedule_clear_optimistic()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control light - SignalR not connected")
            return
        bus = self.entity_description.bus_id
        if self.entity_description.use_brightness_for_on_off:
            # Turn off via brightness=0 instead of sid=1 group switch
            await client.send_light_command(bus, 2, uint_value=0)
            self._optimistic_brightness = 0
            self._optimistic_on = False
            self.async_write_ha_state()
            # Don't schedule clear — keep optimistic state until next toggle
        else:
            await client.send_light_command(bus, 1, bool_value=False)
            self._optimistic_on = False
            self.async_write_ha_state()
            self._schedule_clear_optimistic()

    def _schedule_clear_optimistic(self) -> None:
        """Clear optimistic state after delay and refresh from SCU."""
        async def _clear() -> None:
            await asyncio.sleep(5)
            self._optimistic_on = None
            self._optimistic_brightness = None
            self._optimistic_color_temp = None
            await self.coordinator.async_request_refresh()

        asyncio.ensure_future(_clear())
