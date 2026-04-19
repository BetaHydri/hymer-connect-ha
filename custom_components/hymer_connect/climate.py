"""Climate platform for HYMER Connect — Truma heater control."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)

# Heater temperature range (from Truma spec)
MIN_TEMP = 5.0
MAX_TEMP = 30.0
TEMP_STEP = 1.0

# Sentinel value the SCU sends when heater is off
HEATER_OFF_SETPOINT = -273.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect climate from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HymerHeaterClimate(coordinator, entry)])


class HymerHeaterClimate(
    CoordinatorEntity[HymerConnectCoordinator], ClimateEntity
):
    """Truma heater climate entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "truma_heater"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
    )
    _attr_fan_modes = ["Eco", "High"]
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the heater climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_truma_heater"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic_mode: HVACMode | None = None
        self._optimistic_temp: float | None = None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self._optimistic_mode is not None:
            return self._optimistic_mode
        setpoint = self._get_setpoint()
        if setpoint is not None and setpoint > HEATER_OFF_SETPOINT:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        return HVACAction.OFF

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode (experimental)."""
        if self.coordinator.data is None:
            return None
        val = _resolve_path(self.coordinator.data, "signalr_sensors.heater_fan_speed")
        if val is None:
            return None
        fan_str = str(val).upper()
        if fan_str == "ECO":
            return "Eco"
        if fan_str in ("HIGH", "Hi"):
            return "High"
        # OFF means heater fan is not running
        return "Eco"

    @property
    def current_temperature(self) -> float | None:
        """Return the current indoor temperature."""
        if self.coordinator.data is None:
            return None
        # Use ambient temp from CAN bus as current temp
        val = _resolve_path(self.coordinator.data, "signalr_sensors.ambient_temp")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._optimistic_temp is not None:
            return self._optimistic_temp
        setpoint = self._get_setpoint()
        if setpoint is not None and setpoint > HEATER_OFF_SETPOINT:
            return setpoint
        return None

    def _get_setpoint(self) -> float | None:
        """Get heater setpoint from coordinator data."""
        if self.coordinator.data is None:
            return None
        val = _resolve_path(self.coordinator.data, "signalr_sensors.heater_setpoint")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _get_fuel_type(self) -> str:
        """Get current fuel type from coordinator data."""
        if self.coordinator.data:
            val = _resolve_path(self.coordinator.data, "signalr_sensors.heater_fuel_type")
            if val and isinstance(val, str) and val not in ("unknown", "unavailable"):
                return val
        return "Diesel"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (heat or off)."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control heater — SignalR not connected")
            return

        if hvac_mode == HVACMode.HEAT:
            # Turn on with default 20°C
            temp = self._optimistic_temp or self._get_setpoint() or 20.0
            if temp <= HEATER_OFF_SETPOINT:
                temp = 20.0
            fuel = self._get_fuel_type()
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 8, "float_value": temp},
                {"bus_id": 58, "sensor_id": 6, "str_value": fuel},
            ])
            self._optimistic_mode = HVACMode.HEAT
            self._optimistic_temp = temp
        else:
            fuel = self._get_fuel_type()
            await client.send_multi_sensor_command([
                {"bus_id": 58, "sensor_id": 8, "float_value": HEATER_OFF_SETPOINT},
                {"bus_id": 58, "sensor_id": 6, "str_value": fuel},
            ])
            self._optimistic_mode = HVACMode.OFF
            self._optimistic_temp = None

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control heater — SignalR not connected")
            return

        fuel = self._get_fuel_type()
        await client.send_multi_sensor_command([
            {"bus_id": 58, "sensor_id": 8, "float_value": float(temp)},
            {"bus_id": 58, "sensor_id": 6, "str_value": fuel},
        ])
        self._optimistic_mode = HVACMode.HEAT
        self._optimistic_temp = float(temp)
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode (experimental — untested via EHG app).

        Sends bus=58, sid=5 with 'ECO' or 'High' string value.
        The EHG app does NOT expose this control — use at your own risk.
        """
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning("Cannot control fan — SignalR not connected")
            return

        mode_map = {"Eco": "ECO", "High": "High"}
        mode_str = mode_map.get(fan_mode)
        if mode_str is None:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return

        fuel = self._get_fuel_type()
        _LOGGER.info("EXPERIMENTAL: Setting heater fan to %s", mode_str)
        await client.send_multi_sensor_command([
            {"bus_id": 58, "sensor_id": 5, "str_value": mode_str},
            {"bus_id": 58, "sensor_id": 4, "str_value": fuel},
        ])
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when SCU confirms."""
        if self.coordinator.data and self._optimistic_mode is not None:
            setpoint = self._get_setpoint()
            if setpoint is not None:
                if self._optimistic_mode == HVACMode.OFF and setpoint <= HEATER_OFF_SETPOINT:
                    self._optimistic_mode = None
                    self._optimistic_temp = None
                elif self._optimistic_mode == HVACMode.HEAT and setpoint > HEATER_OFF_SETPOINT:
                    if self._optimistic_temp and abs(setpoint - self._optimistic_temp) < 0.5:
                        self._optimistic_mode = None
                        self._optimistic_temp = None
        super()._handle_coordinator_update()
