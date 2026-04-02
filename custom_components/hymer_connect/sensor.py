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
    UnitOfTemperature,
    UnitOfPressure,
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


SENSOR_DESCRIPTIONS: tuple[HymerSensorEntityDescription, ...] = (
    # Battery
    HymerSensorEntityDescription(
        key="battery_level",
        translation_key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.battery.level",
        icon="mdi:battery",
    ),
    HymerSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.battery.voltage",
        icon="mdi:flash",
    ),
    HymerSensorEntityDescription(
        key="chassis_battery_voltage",
        translation_key="chassis_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.chassisBattery.voltage",
        icon="mdi:car-battery",
    ),
    # Water tanks
    HymerSensorEntityDescription(
        key="fresh_water_level",
        translation_key="fresh_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.freshWater.level",
        icon="mdi:water",
    ),
    HymerSensorEntityDescription(
        key="grey_water_level",
        translation_key="grey_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.greyWater.level",
        icon="mdi:water-off",
    ),
    # Temperatures
    HymerSensorEntityDescription(
        key="indoor_temperature",
        translation_key="indoor_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.temperature.indoor",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.temperature.outdoor",
        icon="mdi:thermometer",
    ),
    # Tire pressure
    HymerSensorEntityDescription(
        key="tire_pressure_front_left",
        translation_key="tire_pressure_front_left",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.tirePressure.frontLeft",
        icon="mdi:tire",
    ),
    HymerSensorEntityDescription(
        key="tire_pressure_front_right",
        translation_key="tire_pressure_front_right",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.tirePressure.frontRight",
        icon="mdi:tire",
    ),
    HymerSensorEntityDescription(
        key="tire_pressure_back_left",
        translation_key="tire_pressure_back_left",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.tirePressure.backLeft",
        icon="mdi:tire",
    ),
    HymerSensorEntityDescription(
        key="tire_pressure_back_right",
        translation_key="tire_pressure_back_right",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="sensors.tirePressure.backRight",
        icon="mdi:tire",
    ),
)


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
        for description in SENSOR_DESCRIPTIONS
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
