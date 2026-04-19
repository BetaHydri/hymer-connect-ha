"""Number platform for HYMER Connect — numeric-valued SCU controls.

At present this exposes the Truma heater's target air temperature as a
HA NumberEntity. The SCU accepts a float °C value on (58, 8); writing
-273.0 turns the heater off (observed in traffic captures — the app
uses it as an 'off' sentinel). To avoid users accidentally writing
-273 through the slider, the entity range is constrained to a normal
thermostat band.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .pia_decoder import build_sensor_write
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HymerNumberEntityDescription(NumberEntityDescription):
    """Describe a HYMER Connect number control."""

    bus_id: int
    sensor_id: int
    value_path: str
    # If a "float off sentinel" is set, read-back of that value will be
    # exposed as None (unknown) instead of the literal sentinel.
    off_sentinel: float | None = None


NUMBER_DESCRIPTIONS: tuple[HymerNumberEntityDescription, ...] = (
    HymerNumberEntityDescription(
        key="heater_target_temperature_ctrl",
        translation_key="heater_target_temperature_ctrl",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=30,
        native_step=0.5,
        mode=NumberMode.SLIDER,
        bus_id=58,
        sensor_id=8,
        value_path="signalr_sensors.heater_setpoint",
        off_sentinel=-273.0,
        icon="mdi:thermostat",
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
        """Initialize the number entity."""
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
        """Return the target value currently known for this entity."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        if self.coordinator.data is None:
            return None
        raw = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        sentinel = self.entity_description.off_sentinel
        if sentinel is not None and value == sentinel:
            return None
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the SCU."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning(
                "Cannot set %s — SignalR not connected",
                self.entity_description.key,
            )
            return
        payload = build_sensor_write(
            self.entity_description.bus_id,
            self.entity_description.sensor_id,
            float(value),
        )
        await client.send_pia_request(payload)
        self._optimistic_value = float(value)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once the SCU confirms the commanded value."""
        if self._optimistic_value is not None and self.coordinator.data:
            raw = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            if raw is not None:
                try:
                    actual = float(raw)
                except (TypeError, ValueError):
                    actual = None
                if actual is not None and abs(actual - self._optimistic_value) < 0.1:
                    self._optimistic_value = None
        super()._handle_coordinator_update()
