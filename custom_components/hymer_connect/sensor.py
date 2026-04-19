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

# SignalR sensors (real-time from PIA Protobuf).
# NOTE: Several v2.9.7 entities were backed by bus/sensor_id slots that
# don't actually carry the data the label implies on the S700 (and per
# the decompiled app registry — see RELEASE_NOTES.md).  They have been
# removed and replaced with correctly-labelled entries.
# Removed: speed, coolant_temp, battery_voltage, battery_current,
# chassis_battery_voltage, ambient_temp, current_gear, rpm, engine_hours,
# fuel_range, total_fuel_used, engine_torque, adblue_temp, dpf_status,
# solar_charger_status, tire_pressure, gps_signal_quality, gps_altitude,
# gps_satellites, gps_heading, fridge_mode.
# fridge_status is kept — v2.9.7 correctly identifies it as the fridge-door
# Open/Closed sensor (bus 37 slot 2 on this vehicle's Thetford).
SIGNALR_SENSORS: tuple[HymerSensorEntityDescription, ...] = (
    # --- Bus 1 — VehicleSignal (Mercedes Sprinter chassis CAN) ---
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
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_level",
        icon="mdi:fuel",
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
        key="adblue_remaining_distance",
        translation_key="adblue_remaining_distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.adblue_remaining_distance",
        icon="mdi:road-variant",
    ),
    HymerSensorEntityDescription(
        key="distance_to_service",
        translation_key="distance_to_service",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.distance_to_service",
        icon="mdi:wrench-clock",
    ),
    HymerSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.outside_temperature",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="ignition_state",
        translation_key="ignition_state",
        value_path="signalr_sensors.ignition_state",
        icon="mdi:key",
    ),
    # --- Bus 3 — CBE EBL402 habitation electrics ---
    HymerSensorEntityDescription(
        key="living_battery_voltage",
        translation_key="living_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.living_battery_voltage",
        icon="mdi:battery",
    ),
    HymerSensorEntityDescription(
        key="living_battery_current",
        translation_key="living_battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.living_battery_current",
        icon="mdi:current-dc",
    ),
    HymerSensorEntityDescription(
        key="starter_battery_voltage",
        translation_key="starter_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.starter_battery_voltage",
        icon="mdi:car-battery",
    ),
    HymerSensorEntityDescription(
        key="living_battery_capacity",
        translation_key="living_battery_capacity",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.living_battery_capacity",
        icon="mdi:battery-high",
    ),
    HymerSensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.lithium_soc",
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
    HymerSensorEntityDescription(
        key="ebl_outdoor_temp_sensor",
        translation_key="ebl_outdoor_temp_sensor",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.ebl_outdoor_temp_sensor",
        icon="mdi:thermometer",
    ),
    # --- Water tanks (author: bus 22/25 with invert100, kept from v2.9.7) ---
    HymerSensorEntityDescription(
        key="fresh_water_level",
        translation_key="fresh_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fresh_water_level",
        icon="mdi:water",
    ),
    HymerSensorEntityDescription(
        key="gray_water_level",
        translation_key="gray_water_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.gray_water_level",
        icon="mdi:water-off",
    ),
    # --- Bus 8 — Votronic MPP250Duo solar charger ---
    HymerSensorEntityDescription(
        key="solar_voltage",
        translation_key="solar_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_voltage",
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
    # Solar panel power: prefer direct W reading from (8,7); fall back to V × A.
    HymerSensorEntityDescription(
        key="solar_power",
        translation_key="solar_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="computed.solar_power",
        icon="mdi:solar-power",
    ),
    # --- Bus 30 — ScuSignals (GPS, LTE, Bluetooth) ---
    HymerSensorEntityDescription(
        key="gps_coordinates",
        translation_key="gps_coordinates",
        value_path="signalr_sensors.gps_coordinates",
        icon="mdi:map-marker",
    ),
    HymerSensorEntityDescription(
        key="lte_connection_quality",
        translation_key="lte_connection_quality",
        value_path="signalr_sensors.lte_connection_quality",
        icon="mdi:signal",
    ),
    HymerSensorEntityDescription(
        key="lte_connection_state",
        translation_key="lte_connection_state",
        value_path="signalr_sensors.lte_connection_state",
        icon="mdi:signal-cellular-3",
    ),
    HymerSensorEntityDescription(
        key="scu_voltage",
        translation_key="scu_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.scu_voltage",
        icon="mdi:chip",
    ),
    HymerSensorEntityDescription(
        key="paired_bt_devices",
        translation_key="paired_bt_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.paired_bt_devices",
        icon="mdi:bluetooth",
    ),
    HymerSensorEntityDescription(
        key="connected_bt_devices",
        translation_key="connected_bt_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.connected_bt_devices",
        icon="mdi:bluetooth-connect",
    ),
    # --- Bus 58 — Truma Combi heater (labels as author has them) ---
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
    # --- Bus 37 — fridge door (v2.9.7 relabelled fridge_status as Open/Closed) ---
    HymerSensorEntityDescription(
        key="fridge_status",
        translation_key="fridge_status",
        value_path="signalr_sensors.fridge_status",
        icon="mdi:fridge-outline",
    ),
    # --- Bus 99 — Lithium battery BMS ---
    HymerSensorEntityDescription(
        key="bms_battery_voltage",
        translation_key="bms_battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_battery_voltage",
        icon="mdi:battery",
    ),
    HymerSensorEntityDescription(
        key="bms_battery_current",
        translation_key="bms_battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_battery_current",
        icon="mdi:current-dc",
    ),
    HymerSensorEntityDescription(
        key="bms_battery_temperature",
        translation_key="bms_battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_battery_temperature",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="bms_time_remaining",
        translation_key="bms_time_remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_time_remaining",
        icon="mdi:timer-outline",
    ),
    HymerSensorEntityDescription(
        key="bms_state_of_health",
        translation_key="bms_state_of_health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_state_of_health",
        icon="mdi:battery-heart-variant",
    ),
    HymerSensorEntityDescription(
        key="bms_capacity_remaining",
        translation_key="bms_capacity_remaining",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_capacity_remaining",
        icon="mdi:battery-high",
    ),
    HymerSensorEntityDescription(
        key="bms_relative_capacity",
        translation_key="bms_relative_capacity",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_relative_capacity",
        icon="mdi:battery-50",
    ),
    # --- Firmware versions (informational) ---
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
    # --- Interior light brightness levels ---
    HymerSensorEntityDescription(
        key="light_living_ceiling_brightness",
        translation_key="light_living_ceiling_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_living_ceiling_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerSensorEntityDescription(
        key="light_living_ambient_brightness",
        translation_key="light_living_ambient_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_living_ambient_brightness",
        icon="mdi:wall-sconce-flat",
    ),
    HymerSensorEntityDescription(
        key="light_kitchen_brightness",
        translation_key="light_kitchen_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_kitchen_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerSensorEntityDescription(
        key="light_seating_overhead_brightness",
        translation_key="light_seating_overhead_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_seating_overhead_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerSensorEntityDescription(
        key="light_bathroom_ceiling_brightness",
        translation_key="light_bathroom_ceiling_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_bathroom_ceiling_brightness",
        icon="mdi:ceiling-light",
    ),
    HymerSensorEntityDescription(
        key="light_bedroom_overhead_brightness",
        translation_key="light_bedroom_overhead_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_bedroom_overhead_brightness",
        icon="mdi:ceiling-light",
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
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    @property
    def native_value(self) -> Any | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        path = self.entity_description.value_path

        # Solar power: prefer the direct reading from (8,7) SolarPanelPower
        # if present, else compute from voltage × current.
        if path == "computed.solar_power":
            sensors = self.coordinator.data.get("signalr_sensors", {})
            direct = sensors.get("solar_power")
            if isinstance(direct, (int, float)) and direct not in (
                3276.8, 32768.0, 65535.0, 6553.5,
            ):
                return round(float(direct), 1)
            voltage = sensors.get("solar_voltage")
            current = sensors.get("solar_current")
            if isinstance(voltage, (int, float)) and isinstance(current, (int, float)):
                return round(voltage * current, 1)
            return None

        # The EBL always reports its last charge phase (typically "Bulk")
        # even when no charging is happening.  Override to "Idle" when
        # neither solar nor mains charger is active.
        if path == "signalr_sensors.charge_phase":
            sensors = self.coordinator.data.get("signalr_sensors", {})
            solar_current = sensors.get("solar_current")
            battery_current = sensors.get("living_battery_current")
            solar_charging = isinstance(solar_current, (int, float)) and solar_current > 0
            mains_charging = (
                isinstance(battery_current, (int, float))
                and battery_current > 0
                and not solar_charging
            )
            if not solar_charging and not mains_charging:
                return "Idle"
            # Fall through to return the real phase value (Bulk/Absorption/Float)

        value = _resolve_path(
            self.coordinator.data, path
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
