"""Select platform for HYMER Connect — fridge mode and boiler mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)

# Fridge cooling steps (ECO is a separate switch, not a mode)
FRIDGE_OPTIONS = ["Off", "1", "2", "3", "4", "5"]

# Boiler modes: Off, ECO, Turbo (HOT)
BOILER_OPTIONS = ["Off", "ECO", "Turbo"]

# Heater energy source modes (captured via mitmproxy 2026-04-19)
# Electric only requires shore power — SCU rejects it otherwise
HEATER_ENERGY_OPTIONS = ["Diesel", "Both 900W", "Both 1800W", "Electric"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect select entities from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HymerFridgeSelect(coordinator, entry),
        HymerBoilerSelect(coordinator, entry),
        HymerHeaterEnergySelect(coordinator, entry),
    ])


class HymerFridgeSelect(
    CoordinatorEntity[HymerConnectCoordinator], SelectEntity
):
    """Fridge mode select entity — Off / 1-5 / ECO."""

    _attr_has_entity_name = True
    _attr_translation_key = "fridge_mode_ctrl"
    _attr_options = FRIDGE_OPTIONS
    _attr_icon = "mdi:fridge"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the fridge select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_fridge_mode_ctrl"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic: str | None = None

    @property
    def current_option(self) -> str | None:
        """Return the current fridge mode."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None

        # Check fridge power (bus 34, sid 1) — if False → Off
        power = _resolve_path(self.coordinator.data, "signalr_sensors.fridge_power")
        if power is False:
            return "Off"

        # Check cooling step (bus 34, sid 3)
        step = _resolve_path(self.coordinator.data, "signalr_sensors.fridge_cooling_step")
        if step is not None:
            try:
                s = int(step)
                if 1 <= s <= 5:
                    return str(s)
            except (ValueError, TypeError):
                pass

        # Fallback: check old fridge_mode sensor from bus 37
        mode = _resolve_path(self.coordinator.data, "signalr_sensors.fridge_mode")
        if mode is not None:
            mode_str = str(mode)
            if mode_str in ("Off", "0"):
                return "Off"

        return None

    async def async_select_option(self, option: str) -> None:
        """Set the fridge mode."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control fridge — SignalR not connected")
            return

        import asyncio

        if option == "Off":
            await client.send_light_command(34, 1, bool_value=False)
        elif option in ("1", "2", "3", "4", "5"):
            # Power on first, wait, then set cooling step
            await client.send_light_command(34, 1, bool_value=True)
            await asyncio.sleep(0.5)
            await client.send_light_command(34, 3, uint_value=int(option))
        else:
            _LOGGER.warning("Unknown fridge option: %s", option)
            return

        self._optimistic = option
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when confirmed."""
        if self._optimistic is not None and self.coordinator.data:
            actual = self.current_option
            if actual == self._optimistic:
                self._optimistic = None
        super()._handle_coordinator_update()


class HymerBoilerSelect(
    CoordinatorEntity[HymerConnectCoordinator], SelectEntity
):
    """Boiler mode select entity — Off / ECO / Turbo."""

    _attr_has_entity_name = True
    _attr_translation_key = "boiler_mode_ctrl"
    _attr_options = BOILER_OPTIONS
    _attr_icon = "mdi:water-boiler"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the boiler select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_boiler_mode_ctrl"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic: str | None = None

    def _get_fuel_type(self) -> str:
        """Get current fuel type from coordinator data."""
        if self.coordinator.data:
            val = _resolve_path(self.coordinator.data, "signalr_sensors.heater_fuel_type")
            if val and isinstance(val, str) and val not in ("unknown", "unavailable"):
                return val
        return "Diesel"

    @property
    def current_option(self) -> str | None:
        """Return the current boiler mode."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None

        # Boiler mode is heater_fan_speed (bus 58, sid 5)
        fan = _resolve_path(self.coordinator.data, "signalr_sensors.heater_fan_speed")
        if fan is None:
            return None

        fan_str = str(fan).upper()
        if fan_str in ("OFF", "Off"):
            return "Off"
        if fan_str == "ECO":
            return "ECO"
        if fan_str == "HOT":
            return "Turbo"
        return "Off"

    async def async_select_option(self, option: str) -> None:
        """Set the boiler mode."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control boiler — SignalR not connected")
            return

        mode_map = {"Off": "OFF", "ECO": "ECO", "Turbo": "HOT"}
        mode_str = mode_map.get(option)
        if mode_str is None:
            _LOGGER.warning("Unknown boiler option: %s", option)
            return

        fuel = self._get_fuel_type()
        await client.send_multi_sensor_command([
            {"bus_id": 58, "sensor_id": 5, "str_value": mode_str},
            {"bus_id": 58, "sensor_id": 4, "str_value": fuel},
        ])

        self._optimistic = option
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when confirmed."""
        if self._optimistic is not None and self.coordinator.data:
            actual = self.current_option
            if actual == self._optimistic:
                self._optimistic = None
        super()._handle_coordinator_update()


class HymerHeaterEnergySelect(
    CoordinatorEntity[HymerConnectCoordinator], SelectEntity
):
    """Heater energy source select — Diesel / Both 900W / Both 1800W / Electric.

    Protocol (captured 2026-04-19 via mitmproxy):
      - (58,4) heater_fuel_type and (58,6) heater_fuel_type_2 are always sent
        as a pair with the same string value: "Diesel", "Both", or "Electric".
      - (58,9) heater_electric_power is only sent when mode is "Both",
        as uint 900 or 1800.
      - "Electric" only works with shore power connected.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "heater_energy_ctrl"
    _attr_options = HEATER_ENERGY_OPTIONS
    _attr_icon = "mdi:gas-station"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the heater energy source select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_heater_energy_ctrl"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic: str | None = None

    @property
    def current_option(self) -> str | None:
        """Return the current heater energy source."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None

        fuel = _resolve_path(
            self.coordinator.data, "signalr_sensors.heater_fuel_type"
        )
        if fuel is None:
            return None

        fuel_str = str(fuel)
        if fuel_str == "Diesel":
            return "Diesel"
        if fuel_str == "Electric":
            return "Electric"
        if fuel_str == "Both":
            watt = _resolve_path(
                self.coordinator.data, "signalr_sensors.heater_electric_power"
            )
            try:
                w = int(watt) if watt is not None else 900
            except (ValueError, TypeError):
                w = 900
            return f"Both {w}W"
        return "Diesel"

    async def async_select_option(self, option: str) -> None:
        """Set the heater energy source."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control heater energy — SignalR not connected")
            return

        if option == "Diesel":
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Diesel"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Diesel"},
            ])
        elif option == "Electric":
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Electric"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Electric"},
            ])
        elif option == "Both 900W":
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 9, "uint_value": 900},
            ])
        elif option == "Both 1800W":
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 9, "uint_value": 1800},
            ])
        else:
            _LOGGER.warning("Unknown heater energy option: %s", option)
            return

        self._optimistic = option
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when confirmed."""
        if self._optimistic is not None and self.coordinator.data:
            actual = self.current_option
            if actual == self._optimistic:
                self._optimistic = None
        super()._handle_coordinator_update()
