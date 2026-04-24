"""Select platform for HYMER Connect — fridge mode and boiler mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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

# Heater air mode (slot 58:11 heater_air_mode per EHG metadata)
HEATER_AIR_MODE_OPTIONS = ["Off", "Normal", "Automatic"]

# Heater energy source modes matching Truma panel display:
#   FUEL  = Diesel only
#   MIX 1 = Diesel + Electric 900W
#   MIX 2 = Diesel + Electric 1800W
#   EL 1  = Electric only 900W
#   EL 2  = Electric only 1800W
# Electric modes require shore power — SCU rejects them otherwise
HEATER_ENERGY_OPTIONS = ["Diesel", "Mix 900W", "Mix 1800W", "Electric 900W", "Electric 1800W"]


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
        HymerHeaterAirModeSelect(coordinator, entry),
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
        import asyncio

        if option == "Off":
            await self.coordinator.async_send_light_command(34, 1, bool_value=False)
        elif option in ("1", "2", "3", "4", "5"):
            # Power on first, wait, then set cooling step
            await self.coordinator.async_send_light_command(34, 1, bool_value=True)
            await asyncio.sleep(0.5)
            await self.coordinator.async_send_light_command(34, 3, uint_value=int(option))
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
        mode_map = {"Off": "OFF", "ECO": "ECO", "Turbo": "HOT"}
        mode_str = mode_map.get(option)
        if mode_str is None:
            _LOGGER.warning("Unknown boiler option: %s", option)
            return

        fuel = self._get_fuel_type()
        await self.coordinator.async_send_multi_sensor_command([
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
    """Heater energy source select matching Truma Combi panel modes.

    Panel labels → SCU wire values:
      FUEL  → (58,4)="Diesel", (58,6)="Diesel"
      MIX 1 → (58,4)="Both",  (58,6)="Both",  (58,9)=uint 900
      MIX 2 → (58,4)="Both",  (58,6)="Both",  (58,9)=uint 1800
      EL 1  → (58,4)="Electric", (58,6)="Electric", (58,9)=uint 900
      EL 2  → (58,4)="Electric", (58,6)="Electric", (58,9)=uint 1800

    Protocol (captured 2026-04-19 via mitmproxy):
      - (58,4) heater_fuel_type and (58,6) heater_fuel_type_2 are always sent
        as a pair with the same string value: "Diesel", "Both", or "Electric".
      - (58,9) heater_electric_power is sent as uint 900 or 1800 when mode
        involves electric power (Both or Electric).
      - Electric modes require shore power — SCU rejects otherwise.
      - NOTE: "Both" and "Diesel" were captured via mitmproxy.  "Electric"
        with wattage and VENT fan mode are extrapolated from the same
        protocol pattern + Truma panel labels.  Not yet verified on wire.
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
            watt = _resolve_path(
                self.coordinator.data, "signalr_sensors.heater_electric_power"
            )
            try:
                w = int(watt) if watt is not None else 900
            except (ValueError, TypeError):
                w = 900
            return f"Electric {w}W"
        if fuel_str == "Both":
            watt = _resolve_path(
                self.coordinator.data, "signalr_sensors.heater_electric_power"
            )
            try:
                w = int(watt) if watt is not None else 900
            except (ValueError, TypeError):
                w = 900
            return f"Mix {w}W"
        return "Diesel"

    async def async_select_option(self, option: str) -> None:
        """Set the heater energy source."""
        if option == "Diesel":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Diesel"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Diesel"},
            ])
        elif option == "Electric 900W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Electric"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Electric"},
                {"bus_id": 58, "sensor_id": 9, "uint_value": 900},
            ])
        elif option == "Electric 1800W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Electric"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Electric"},
                {"bus_id": 58, "sensor_id": 9, "uint_value": 1800},
            ])
        elif option == "Mix 900W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 4, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 6, "str_value": "Both"},
                {"bus_id": 58, "sensor_id": 9, "uint_value": 900},
            ])
        elif option == "Mix 1800W":
            await self.coordinator.async_send_multi_sensor_command([
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


class HymerHeaterAirModeSelect(
    CoordinatorEntity[HymerConnectCoordinator], SelectEntity
):
    """Truma heater air mode select — Off / Normal / Automatic.

    Per EHG metadata, slot 58:11 (heater_air_mode) accepts the strings
    'OFF', 'Normal', 'Automatic'. This is the actual heater mode toggle
    on the SCU bus (NOT slot 58:5 which is the water boiler mode).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "heater_air_mode_ctrl"
    _attr_options = HEATER_AIR_MODE_OPTIONS
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the heater air mode select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_heater_air_mode_ctrl"
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
            val = _resolve_path(
                self.coordinator.data, "signalr_sensors.heater_fuel_type"
            )
            if val and isinstance(val, str) and val not in ("unknown", "unavailable"):
                return val
        return "Diesel"

    @property
    def current_option(self) -> str | None:
        """Return the current heater air mode."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None
        # heater_operating_mode is the existing translation_key for slot 58:11
        val = _resolve_path(
            self.coordinator.data, "signalr_sensors.heater_operating_mode"
        )
        if val is None:
            return None
        val_str = str(val).strip()
        if val_str.upper() in ("OFF", "0"):
            return "Off"
        if val_str.lower() == "normal":
            return "Normal"
        if val_str.lower() in ("automatic", "auto"):
            return "Automatic"
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the heater air mode.

        Sent as a multi-sensor command paired with the fuel slot, matching
        the pattern used by every other writable 58:* slot (setpoint, boiler
        mode, energy source). Captured EHG traffic always pairs slot writes
        on bus 58 this way; a standalone set_value on 58:11 was observed to
        be silently reverted by the SCU back to Normal.
        """
        mode_map = {"Off": "OFF", "Normal": "Normal", "Automatic": "Automatic"}
        mode_str = mode_map.get(option)
        if mode_str is None:
            _LOGGER.warning("Unknown heater air mode option: %s", option)
            return

        fuel = self._get_fuel_type()
        await self.coordinator.async_send_multi_sensor_command([
            {"bus_id": 58, "sensor_id": 11, "str_value": mode_str},
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
