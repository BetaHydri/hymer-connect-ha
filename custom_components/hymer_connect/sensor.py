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
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
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
        key="adblue_level",
        translation_key="adblue_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.adblue_level",
        icon="mdi:car-coolant-level",
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
        key="chassis_battery_voltage",
        translation_key="chassis_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.chassis_battery_voltage",
        icon="mdi:car-battery",
    ),
    HymerSensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.battery_soc",
        icon="mdi:battery",
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
        key="heater_fan_speed",
        translation_key="heater_fan_speed",
        value_path="signalr_sensors.heater_fan_speed",
        icon="mdi:fan",
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
    # --- Engine (can0) ---
    HymerSensorEntityDescription(
        key="rpm",
        translation_key="rpm",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.rpm",
        icon="mdi:engine",
    ),
    HymerSensorEntityDescription(
        key="engine_hours",
        translation_key="engine_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path="signalr_sensors.engine_hours",
        icon="mdi:engine-outline",
    ),
    # --- Heater (bus 58) ---
    HymerSensorEntityDescription(
        key="heater_state",
        translation_key="heater_state",
        value_path="signalr_sensors.heater_state",
        icon="mdi:radiator",
    ),
    HymerSensorEntityDescription(
        key="heater_electric_power",
        translation_key="heater_electric_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.heater_electric_power",
        icon="mdi:radiator",
    ),
    HymerSensorEntityDescription(
        key="heater_operating_mode",
        translation_key="heater_operating_mode",
        value_path="signalr_sensors.heater_operating_mode",
        icon="mdi:radiator",
    ),
    # --- Fridge (bus 37) ---
    HymerSensorEntityDescription(
        key="fridge_mode",
        translation_key="fridge_mode",
        value_path="signalr_sensors.fridge_mode",
        icon="mdi:fridge",
    ),
    HymerSensorEntityDescription(
        key="fridge_status",
        translation_key="fridge_status",
        value_path="signalr_sensors.fridge_status",
        icon="mdi:fridge-outline",
    ),
    # --- Extended CAN (can2) ---
    HymerSensorEntityDescription(
        key="fuel_range",
        translation_key="fuel_range",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_range",
        icon="mdi:gas-station",
    ),
    HymerSensorEntityDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        value_path="signalr_sensors.fuel_consumption",
        icon="mdi:fuel",
    ),
    HymerSensorEntityDescription(
        key="total_fuel_used",
        translation_key="total_fuel_used",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path="signalr_sensors.total_fuel_used",
        icon="mdi:fuel",
    ),
    HymerSensorEntityDescription(
        key="trip_distance",
        translation_key="trip_distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        value_path="signalr_sensors.trip_distance",
        icon="mdi:map-marker-distance",
    ),
    HymerSensorEntityDescription(
        key="engine_torque",
        translation_key="engine_torque",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.engine_torque",
        icon="mdi:engine",
    ),
    HymerSensorEntityDescription(
        key="adblue_temp",
        translation_key="adblue_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.adblue_temp",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="dpf_status",
        translation_key="dpf_status",
        value_path="signalr_sensors.dpf_status",
        icon="mdi:car-exhaust",
    ),
    # --- Habitation electrics (lin1) ---
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
        key="solar_charger_status",
        translation_key="solar_charger_status",
        value_path="signalr_sensors.solar_charger_status",
        icon="mdi:solar-power-variant",
    ),
    HymerSensorEntityDescription(
        key="solar_current",
        translation_key="solar_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_current",
        icon="mdi:solar-power",
    ),
    HymerSensorEntityDescription(
        key="solar_power",
        translation_key="solar_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_power",
        icon="mdi:solar-power",
    ),
    # --- Fresh water (bus 21) ---
    HymerSensorEntityDescription(
        key="fresh_water_level",
        translation_key="fresh_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fresh_water_level",
        icon="mdi:water",
    ),
    HymerSensorEntityDescription(
        key="light_1_level",
        translation_key="light_1_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_1_level",
        icon="mdi:lightbulb-on",
    ),
    HymerSensorEntityDescription(
        key="light_2_level",
        translation_key="light_2_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_2_level",
        icon="mdi:lightbulb-on",
    ),
    # --- Climate (lin2) ---
    HymerSensorEntityDescription(
        key="tire_pressure",
        translation_key="tire_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.tire_pressure",
        icon="mdi:car-tire-alert",
    ),
    # --- Alarm ---
    HymerSensorEntityDescription(
        key="alarm_battery",
        translation_key="alarm_battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.alarm_battery",
        icon="mdi:alarm-light",
    ),
    # --- SCU/Truma firmware ---
    HymerSensorEntityDescription(
        key="scu_firmware",
        translation_key="scu_firmware",
        value_path="signalr_sensors.scu_firmware",
        icon="mdi:chip",
    ),
    HymerSensorEntityDescription(
        key="truma_firmware",
        translation_key="truma_firmware",
        value_path="signalr_sensors.truma_firmware",
        icon="mdi:chip",
    ),
    HymerSensorEntityDescription(
        key="truma_status",
        translation_key="truma_status",
        value_path="signalr_sensors.truma_status",
        icon="mdi:radiator",
    ),
    # --- GPS ---
    HymerSensorEntityDescription(
        key="gps_satellites",
        translation_key="gps_satellites",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.gps_satellites",
        icon="mdi:satellite-variant",
    ),
    HymerSensorEntityDescription(
        key="gps_heading",
        translation_key="gps_heading",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.gps_heading",
        icon="mdi:compass",
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
            # 3276.8 = 32768/10 = CAN "no data" sentinel (solar voltage etc.)
            if value in (3276.8, 32768.0, 65535.0, 6553.5):
                return None
        return value
