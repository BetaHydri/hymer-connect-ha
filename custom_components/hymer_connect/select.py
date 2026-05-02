"""Select platform for HYMER Connect — fridge mode, boiler mode, heater energy.

Bus/slot IDs are loaded from the JSON ``"climate"`` section in the brand
overlay file.  If a ``"fridge"`` or ``"truma_heater"`` definition is missing,
the corresponding select entity is not created.
"""

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

# Heater energy source modes matching Truma panel display
HEATER_ENERGY_OPTIONS = ["Diesel", "Mix 900W", "Mix 1800W", "Electric 900W", "Electric 1800W"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect select entities from a config entry."""
    from .pia_decoder import CLIMATE_DEFS

    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []

    fridge_def = CLIMATE_DEFS.get("fridge")
    heater_def = CLIMATE_DEFS.get("truma_heater")

    if fridge_def:
        entities.append(HymerFridgeSelect(coordinator, entry, fridge_def))
        _LOGGER.debug("Select platform: fridge on bus %d", fridge_def.get("control_bus", 34))
    if heater_def:
        entities.append(HymerBoilerSelect(coordinator, entry, heater_def))
        entities.append(HymerHeaterEnergySelect(coordinator, entry, heater_def))
        _LOGGER.debug("Select platform: boiler+energy on bus %d", heater_def.get("heater_bus", 58))

    if entities:
        async_add_entities(entities)
    else:
        _LOGGER.debug("Select platform: no fridge or heater definitions — skipping")


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
        fridge_def: dict[str, Any],
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
        # Bus/slot IDs from JSON
        self._bus = fridge_def.get("control_bus", 34)
        self._power_sid = fridge_def.get("power_sid", 1)
        self._step_sid = fridge_def.get("cooling_step_sid", 3)
        self._power_sensor = fridge_def.get("power_sensor", "fridge_power")
        self._step_sensor = fridge_def.get("cooling_step_sensor", "fridge_cooling_step")
        self._mode_sensor = fridge_def.get("mode_sensor", "fridge_mode")

    @property
    def current_option(self) -> str | None:
        """Return the current fridge mode."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None

        # Check fridge power — if False → Off
        power = _resolve_path(self.coordinator.data, f"signalr_sensors.{self._power_sensor}")
        if power is False:
            return "Off"

        # Check cooling step
        step = _resolve_path(self.coordinator.data, f"signalr_sensors.{self._step_sensor}")
        if step is not None:
            try:
                s = int(step)
                if 1 <= s <= 5:
                    return str(s)
            except (ValueError, TypeError):
                pass

        # Fallback: check old fridge_mode sensor
        mode = _resolve_path(self.coordinator.data, f"signalr_sensors.{self._mode_sensor}")
        if mode is not None:
            mode_str = str(mode)
            if mode_str in ("Off", "0"):
                return "Off"

        return None

    async def async_select_option(self, option: str) -> None:
        """Set the fridge mode."""
        import asyncio

        if option == "Off":
            await self.coordinator.async_send_light_command(self._bus, self._power_sid, bool_value=False)
        elif option in ("1", "2", "3", "4", "5"):
            # Power on first, wait, then set cooling step
            await self.coordinator.async_send_light_command(self._bus, self._power_sid, bool_value=True)
            await asyncio.sleep(0.5)
            await self.coordinator.async_send_light_command(self._bus, self._step_sid, uint_value=int(option))
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
        heater_def: dict[str, Any],
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
        self._bus = heater_def.get("heater_bus", 58)
        self._boiler_sid = heater_def.get("boiler_sid", 5)
        self._fuel_type_sid = heater_def.get("fuel_type_sid", 4)
        self._boiler_sensor = heater_def.get("boiler_sensor", "heater_fan_speed")
        self._fuel_type_sensor = heater_def.get("fuel_type_sensor", "heater_fuel_type")

    def _get_fuel_type(self) -> str:
        """Get current fuel type from coordinator data."""
        if self.coordinator.data:
            val = _resolve_path(self.coordinator.data, f"signalr_sensors.{self._fuel_type_sensor}")
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

        # Boiler mode is heater_fan_speed (bus N, sid M)
        fan = _resolve_path(self.coordinator.data, f"signalr_sensors.{self._boiler_sensor}")
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
            {"bus_id": self._bus, "sensor_id": self._boiler_sid, "str_value": mode_str},
            {"bus_id": self._bus, "sensor_id": self._fuel_type_sid, "str_value": fuel},
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
        heater_def: dict[str, Any],
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
        self._bus = heater_def.get("heater_bus", 58)
        self._fuel_type_sid = heater_def.get("fuel_type_sid", 4)
        self._fuel_type_2_sid = heater_def.get("fuel_type_2_sid", 6)
        self._electric_power_sid = heater_def.get("electric_power_sid", 9)
        self._fuel_type_sensor = heater_def.get("fuel_type_sensor", "heater_fuel_type")
        self._electric_power_sensor = heater_def.get("electric_power_sensor", "heater_electric_power")

    @property
    def current_option(self) -> str | None:
        """Return the current heater energy source."""
        if self._optimistic is not None:
            return self._optimistic
        if self.coordinator.data is None:
            return None

        fuel = _resolve_path(
            self.coordinator.data, f"signalr_sensors.{self._fuel_type_sensor}"
        )
        if fuel is None:
            return None

        fuel_str = str(fuel)
        if fuel_str == "Diesel":
            return "Diesel"
        if fuel_str == "Electric":
            watt = _resolve_path(
                self.coordinator.data, f"signalr_sensors.{self._electric_power_sensor}"
            )
            try:
                w = int(watt) if watt is not None else 900
            except (ValueError, TypeError):
                w = 900
            return f"Electric {w}W"
        if fuel_str == "Both":
            watt = _resolve_path(
                self.coordinator.data, f"signalr_sensors.{self._electric_power_sensor}"
            )
            try:
                w = int(watt) if watt is not None else 900
            except (ValueError, TypeError):
                w = 900
            return f"Mix {w}W"
        return "Diesel"

    async def async_select_option(self, option: str) -> None:
        """Set the heater energy source."""
        b = self._bus
        ft = self._fuel_type_sid
        ft2 = self._fuel_type_2_sid
        ep = self._electric_power_sid

        if option == "Diesel":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": b, "sensor_id": ft, "str_value": "Diesel"},
                {"bus_id": b, "sensor_id": ft2, "str_value": "Diesel"},
            ])
        elif option == "Electric 900W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": b, "sensor_id": ft, "str_value": "Electric"},
                {"bus_id": b, "sensor_id": ft2, "str_value": "Electric"},
                {"bus_id": b, "sensor_id": ep, "uint_value": 900},
            ])
        elif option == "Electric 1800W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": b, "sensor_id": ft, "str_value": "Electric"},
                {"bus_id": b, "sensor_id": ft2, "str_value": "Electric"},
                {"bus_id": b, "sensor_id": ep, "uint_value": 1800},
            ])
        elif option == "Mix 900W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": b, "sensor_id": ft, "str_value": "Both"},
                {"bus_id": b, "sensor_id": ft2, "str_value": "Both"},
                {"bus_id": b, "sensor_id": ep, "uint_value": 900},
            ])
        elif option == "Mix 1800W":
            await self.coordinator.async_send_multi_sensor_command([
                {"bus_id": b, "sensor_id": ft, "str_value": "Both"},
                {"bus_id": b, "sensor_id": ft2, "str_value": "Both"},
                {"bus_id": b, "sensor_id": ep, "uint_value": 1800},
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


# Note: a HymerHeaterAirModeSelect for slot 58:11 (heater_air_mode) was
# removed in v2.36.3. The EHG metadata flag claimed the slot was writable
# with values OFF/Normal/Automatic, but inspection of the official EHG app
# (Klima tab) shows no such control exists, and captured SignalR traffic
# never contained a write to 58:11. The Truma SCU silently reverts any
# write back to "Normal", so the slot is effectively read-only for this
# Combi configuration. The reading is still available via
# sensor.hymer_heater_operating_mode.
