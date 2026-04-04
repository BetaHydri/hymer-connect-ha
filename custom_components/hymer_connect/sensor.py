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
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
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


# REST-based sensors (vehicle metadata)
REST_SENSORS: tuple[HymerSensorEntityDescription, ...] = (
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
)

# SignalR sensors (real-time from PIA Protobuf)
SIGNALR_SENSORS: tuple[HymerSensorEntityDescription, ...] = (
    # --- Vehicle CAN (can0) ---
    HymerSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path="signalr_sensors.odometer",
        icon="mdi:counter",
    ),
    HymerSensorEntityDescription(
        key="speed",
        translation_key="speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.speed",
        icon="mdi:speedometer",
    ),
    HymerSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_level",
        icon="mdi:gas-station",
    ),
    HymerSensorEntityDescription(
        key="coolant_temp",
        translation_key="coolant_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.coolant_temp",
        icon="mdi:coolant-temperature",
    ),
    HymerSensorEntityDescription(
        key="ignition_state",
        translation_key="ignition_state",
        value_path="signalr_sensors.ignition_state",
        icon="mdi:key",
    ),
    # --- Habitation (lin1) ---
    HymerSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.battery_voltage",
        icon="mdi:battery",
    ),
    HymerSensorEntityDescription(
        key="battery_current",
        translation_key="battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.battery_current",
        icon="mdi:current-dc",
    ),
    HymerSensorEntityDescription(
        key="solar_voltage",
        translation_key="solar_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_voltage",
        icon="mdi:solar-power",
    ),
    HymerSensorEntityDescription(
        key="fresh_water_level",
        translation_key="fresh_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fresh_water_level",
        icon="mdi:water",
    ),
    HymerSensorEntityDescription(
        key="battery_type",
        translation_key="battery_type",
        value_path="signalr_sensors.battery_type",
        icon="mdi:battery-check",
    ),
    HymerSensorEntityDescription(
        key="charge_phase",
        translation_key="charge_phase",
        value_path="signalr_sensors.charge_phase",
        icon="mdi:battery-charging",
    ),
    HymerSensorEntityDescription(
        key="power_source",
        translation_key="power_source",
        value_path="signalr_sensors.power_source",
        icon="mdi:power-plug",
    ),
    # --- Climate (lin2) ---
    HymerSensorEntityDescription(
        key="indoor_temp",
        translation_key="indoor_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.indoor_temp",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="outdoor_temp",
        translation_key="outdoor_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.outdoor_temp",
        icon="mdi:thermometer",
    ),
    # --- Gray water (bus 12) ---
    HymerSensorEntityDescription(
        key="gray_water_level",
        translation_key="gray_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.gray_water_level",
        icon="mdi:water-off",
    ),
    # --- GPS (bus 30) ---
    HymerSensorEntityDescription(
        key="gps_coordinates",
        translation_key="gps_coordinates",
        value_path="signalr_sensors.gps_coordinates",
        icon="mdi:map-marker",
    ),
    HymerSensorEntityDescription(
        key="gps_signal_quality",
        translation_key="gps_signal_quality",
        value_path="signalr_sensors.gps_signal_quality",
        icon="mdi:signal",
    ),
    HymerSensorEntityDescription(
        key="gps_altitude",
        translation_key="gps_altitude",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.gps_altitude",
        icon="mdi:altimeter",
    ),
    # --- Truma heater (bus 58) ---
    HymerSensorEntityDescription(
        key="heater_mode",
        translation_key="heater_mode",
        value_path="signalr_sensors.heater_mode",
        icon="mdi:radiator",
    ),
    HymerSensorEntityDescription(
        key="heater_setpoint",
        translation_key="heater_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_path="signalr_sensors.heater_setpoint",
        icon="mdi:thermostat",
    ),
    HymerSensorEntityDescription(
        key="heater_fuel_type",
        translation_key="heater_fuel_type",
        value_path="signalr_sensors.heater_fuel_type",
        icon="mdi:gas-burner",
    ),
    # --- Extended CAN (can2) ---
    HymerSensorEntityDescription(
        key="ambient_temp",
        translation_key="ambient_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.ambient_temp",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="current_gear",
        translation_key="current_gear",
        value_path="signalr_sensors.current_gear",
        icon="mdi:car-shift-pattern",
    ),
)

ALL_SENSOR_DESCRIPTIONS = REST_SENSORS + SIGNALR_SENSORS


def _resolve_path(data: dict[str, Any], path: str) -> Any | None:
    """Resolve a dot-separated path into nested dicts."""
    current: Any = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
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
    async_add_entities(
        HymerConnectSensor(coordinator, desc, entry)
        for desc in ALL_SENSOR_DESCRIPTIONS
    )


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
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        # Filter out sentinel values
        if value is not None and isinstance(value, (int, float)):
            # -273°C = absolute zero = heater off / sensor unavailable
            if value <= -273:
                return None
        return value
