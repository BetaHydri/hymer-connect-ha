"""Sensor platform for HYMER Connect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator


@dataclass(frozen=True, kw_only=True)
class HymerSensorEntityDescription(SensorEntityDescription):
    """Describe a HYMER Connect sensor."""

    value_path: str
    """Dot-separated path into the coordinator data dict."""


# REST-based sensors (vehicle metadata from rv-twin API)
REST_SENSOR_DESCRIPTIONS: tuple[HymerSensorEntityDescription, ...] = (
    HymerSensorEntityDescription(
        key="vehicle_model",
        translation_key="vehicle_model",
        value_path="model",
        icon="mdi:rv-truck",
    ),
    HymerSensorEntityDescription(
        key="vehicle_model_year",
        translation_key="vehicle_model_year",
        value_path="model_year",
        icon="mdi:calendar",
    ),
    HymerSensorEntityDescription(
        key="vehicle_vin",
        translation_key="vehicle_vin",
        value_path="vin",
        icon="mdi:identifier",
    ),
    HymerSensorEntityDescription(
        key="vehicle_type",
        translation_key="vehicle_type",
        value_path="type_id",
        icon="mdi:rv-truck",
    ),
)

# SignalR-based sensors (real-time data from PIA Protobuf via datahub)
# These use the signalr_sensors.* path which contains decoded PIA data.
# Field keys will be refined as the Protobuf schema is mapped.
SIGNALR_SENSOR_DESCRIPTIONS: tuple[HymerSensorEntityDescription, ...] = (
    HymerSensorEntityDescription(
        key="lock_status",
        translation_key="lock_status",
        value_path="signalr_sensors.lock_status",
        icon="mdi:lock",
    ),
    HymerSensorEntityDescription(
        key="ignition_status",
        translation_key="ignition_status",
        value_path="signalr_sensors.ignition_status",
        icon="mdi:key",
    ),
    HymerSensorEntityDescription(
        key="battery_type",
        translation_key="battery_type",
        value_path="signalr_sensors.battery_type",
        icon="mdi:battery-check",
    ),
    HymerSensorEntityDescription(
        key="charge_mode",
        translation_key="charge_mode",
        value_path="signalr_sensors.charge_mode",
        icon="mdi:battery-charging",
    ),
    HymerSensorEntityDescription(
        key="fuel_type",
        translation_key="fuel_type",
        value_path="signalr_sensors.fuel_type",
        icon="mdi:gas-station",
    ),
    HymerSensorEntityDescription(
        key="signal_quality",
        translation_key="signal_quality",
        value_path="signalr_sensors.signal_quality",
        icon="mdi:signal",
    ),
)

ALL_SENSOR_DESCRIPTIONS = REST_SENSOR_DESCRIPTIONS + SIGNALR_SENSOR_DESCRIPTIONS


def _resolve_path(data: dict[str, Any], path: str) -> Any | None:
    """Resolve a dot-separated path into nested dicts/lists."""
    current: Any = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect sensors from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[HymerConnectSensor] = [
        HymerConnectSensor(coordinator, description, entry)
        for description in ALL_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HymerConnectSensor(
    CoordinatorEntity[HymerConnectCoordinator], SensorEntity
):
    """Representation of a HYMER Connect sensor."""

    entity_description: HymerSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
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
    def native_value(self) -> Any | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
