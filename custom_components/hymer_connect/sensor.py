"""Sensor platform for HYMER Connect."""

from __future__ import annotations

import logging
import re
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
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator

_LOGGER = logging.getLogger(__name__)

# Pattern matching unmapped slot fallback keys produced by pia_decoder when a
# (bus_id, sensor_id) pair is NOT present in SENSOR_MAP, e.g. "bus47_s3".
_DISCOVERED_KEY_RE = re.compile(r"^bus(\d+)_s(\d+)$")


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
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_level",
        icon="mdi:fuel",
    ),
    # --- Computed fuel metrics (93 L tank) ---
    HymerSensorEntityDescription(
        key="fuel_level_liters",
        translation_key="fuel_level_liters",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_level_liters",
        icon="mdi:fuel",
    ),
    HymerSensorEntityDescription(
        key="fuel_consumption",
        translation_key="fuel_consumption",
        native_unit_of_measurement="L/100km",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_consumption",
        icon="mdi:gas-station-outline",
    ),
    HymerSensorEntityDescription(
        key="fuel_range_estimated",
        translation_key="fuel_range_estimated",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fuel_range_estimated",
        icon="mdi:map-marker-distance",
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
    # --- Solar (Voltronic MPP260CI via lin2 bus 8) ---
    HymerSensorEntityDescription(
        key="solar_voltage",
        translation_key="solar_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_voltage",
        icon="mdi:solar-power-variant",
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
    # NOTE: `heater_fan_speed` is a legacy misnomer — it reads slot 58:5
    # which is `water_heater_mode` (the boiler), already exposed (and
    # writable) via `select.hymer_boiler_mode_ctrl`. The entity is kept
    # for backwards-compat with existing dashboards/history but is
    # disabled by default so new installs don't see a confusing duplicate.
    HymerSensorEntityDescription(
        key="heater_fan_speed",
        translation_key="heater_fan_speed",
        value_path="signalr_sensors.heater_fan_speed",
        icon="mdi:fan",
        entity_registry_enabled_default=False,
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
    # --- Vehicle service (can0) ---
    HymerSensorEntityDescription(
        key="distance_to_service",
        translation_key="distance_to_service",
        native_unit_of_measurement="km",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.distance_to_service",
        icon="mdi:wrench-clock",
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
    # --- BOS LUX BMS (bus 99) ---
    HymerSensorEntityDescription(
        key="bms_voltage",
        translation_key="bms_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_voltage",
        icon="mdi:battery-charging",
    ),
    HymerSensorEntityDescription(
        key="bms_current",
        translation_key="bms_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_current",
        icon="mdi:current-dc",
    ),
    HymerSensorEntityDescription(
        key="bms_temperature",
        translation_key="bms_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_temperature",
        icon="mdi:thermometer",
    ),
    HymerSensorEntityDescription(
        key="bms_time_remaining",
        translation_key="bms_time_remaining",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_time_remaining",
        icon="mdi:clock-outline",
    ),
    HymerSensorEntityDescription(
        key="bms_state_of_health",
        translation_key="bms_state_of_health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_state_of_health",
        icon="mdi:battery-heart",
    ),
    HymerSensorEntityDescription(
        key="bms_capacity_remaining",
        translation_key="bms_capacity_remaining",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.bms_capacity_remaining",
        icon="mdi:battery",
    ),
    # --- Habitation electrics (lin1) ---
    HymerSensorEntityDescription(
        key="solar_charger_status",
        translation_key="solar_charger_status",
        value_path="signalr_sensors.solar_charger_status",
        icon="mdi:solar-power-variant",
    ),
    # Solar current from the Voltronic MPP260CI MPPT charger (bus 8, sid 3)
    HymerSensorEntityDescription(
        key="solar_current",
        translation_key="solar_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.solar_current",
        icon="mdi:solar-power",
    ),
    # Solar power computed from voltage × current
    HymerSensorEntityDescription(
        key="solar_power",
        translation_key="solar_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="computed.solar_power",
        icon="mdi:solar-power",
    ),
    # --- LED bar 2 brightness (bus 22) ---
    # Confirmed at vehicle 2026-04-23: NOT fresh water (tanks empty, shows 88%).
    # Same LED bar as bus 25 — secondary SCU component ID.
    HymerSensorEntityDescription(
        key="light_led_bar_2_brightness",
        translation_key="light_led_bar_2_brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.light_led_bar_2_brightness",
        entity_registry_enabled_default=False,
        icon="mdi:led-strip",
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
    # --- Water levels from EBL402 (bus 3, slots 8/9) ---
    HymerSensorEntityDescription(
        key="fresh_water_level_ebl",
        translation_key="fresh_water_level_ebl",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.fresh_water_level_ebl",
        icon="mdi:water",
    ),
    HymerSensorEntityDescription(
        key="grey_water_level_ebl",
        translation_key="grey_water_level_ebl",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.grey_water_level_ebl",
        icon="mdi:water-opacity",
    ),
    # --- Living ceiling brightness (was alarm_battery) ---
    # Bus 11 sid 2 is living room ceiling brightness, not alarm battery
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
        key="gps_utc_time",
        translation_key="gps_utc_time",
        value_path="signalr_sensors.gps_utc_time",
        icon="mdi:clock-outline",
    ),
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
    # --- SCU/LTE/BT telemetry (bus 30, slots 8-14) ---
    # Best-guess names from S700 mapping + observed S600 values. Unconfirmed.
    HymerSensorEntityDescription(
        key="scu_flag_1",
        translation_key="scu_flag_1",
        value_path="signalr_sensors.scu_flag_1",
        entity_registry_enabled_default=False,
        icon="mdi:help-circle-outline",
    ),
    HymerSensorEntityDescription(
        key="lte_connected",
        translation_key="lte_connected",
        value_path="signalr_sensors.lte_connected",
        entity_registry_enabled_default=False,
        icon="mdi:signal-4g",
    ),
    HymerSensorEntityDescription(
        key="scu_flag_2",
        translation_key="scu_flag_2",
        value_path="signalr_sensors.scu_flag_2",
        entity_registry_enabled_default=False,
        icon="mdi:help-circle-outline",
    ),
    HymerSensorEntityDescription(
        key="paired_bt_devices",
        translation_key="paired_bt_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.paired_bt_devices",
        entity_registry_enabled_default=False,
        icon="mdi:bluetooth-connect",
    ),
    HymerSensorEntityDescription(
        key="scu_flag_5",
        translation_key="scu_flag_5",
        value_path="signalr_sensors.scu_flag_5",
        entity_registry_enabled_default=False,
        icon="mdi:help-circle-outline",
    ),
    HymerSensorEntityDescription(
        key="scu_flag_3",
        translation_key="scu_flag_3",
        value_path="signalr_sensors.scu_flag_3",
        entity_registry_enabled_default=False,
        icon="mdi:help-circle-outline",
    ),
    HymerSensorEntityDescription(
        key="scu_flag_4",
        translation_key="scu_flag_4",
        value_path="signalr_sensors.scu_flag_4",
        entity_registry_enabled_default=False,
        icon="mdi:help-circle-outline",
    ),
    # --- Victron MultiPlus 12/1600/70 (bus 121) ---
    # From EHG app metadata (Dan's extraction). Not yet confirmed on S600.
    # Disabled by default until Victron physical switch is ON and bus 121 appears.
    HymerSensorEntityDescription(
        key="victron_inverter_state",
        translation_key="victron_inverter_state",
        value_path="signalr_sensors.victron_inverter_state",
        entity_registry_enabled_default=False,
        icon="mdi:power-plug",
    ),
    HymerSensorEntityDescription(
        key="victron_inverter_l1_voltage",
        translation_key="victron_inverter_l1_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_inverter_l1_voltage",
        entity_registry_enabled_default=False,
        icon="mdi:flash",
    ),
    HymerSensorEntityDescription(
        key="victron_inverter_l1_current",
        translation_key="victron_inverter_l1_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_inverter_l1_current",
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    HymerSensorEntityDescription(
        key="victron_inverter_l1_frequency",
        translation_key="victron_inverter_l1_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_inverter_l1_frequency",
        entity_registry_enabled_default=False,
        icon="mdi:sine-wave",
    ),
    HymerSensorEntityDescription(
        key="victron_charger_state",
        translation_key="victron_charger_state",
        value_path="signalr_sensors.victron_charger_state",
        entity_registry_enabled_default=False,
        icon="mdi:battery-charging",
    ),
    HymerSensorEntityDescription(
        key="victron_charge_voltage",
        translation_key="victron_charge_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_charge_voltage",
        entity_registry_enabled_default=False,
        icon="mdi:flash",
    ),
    HymerSensorEntityDescription(
        key="victron_charge_current",
        translation_key="victron_charge_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_charge_current",
        entity_registry_enabled_default=False,
        icon="mdi:current-dc",
    ),
    HymerSensorEntityDescription(
        key="victron_input_voltage",
        translation_key="victron_input_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_input_voltage",
        entity_registry_enabled_default=False,
        icon="mdi:power-plug",
    ),
    HymerSensorEntityDescription(
        key="victron_input_current",
        translation_key="victron_input_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_input_current",
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    HymerSensorEntityDescription(
        key="victron_input_frequency",
        translation_key="victron_input_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.victron_input_frequency",
        entity_registry_enabled_default=False,
        icon="mdi:sine-wave",
    ),
    HymerSensorEntityDescription(
        key="victron_device_failure",
        translation_key="victron_device_failure",
        value_path="signalr_sensors.victron_device_failure",
        entity_registry_enabled_default=False,
        icon="mdi:alert-circle",
    ),
    HymerSensorEntityDescription(
        key="victron_firmware",
        translation_key="victron_firmware",
        value_path="signalr_sensors.victron_firmware",
        entity_registry_enabled_default=False,
        icon="mdi:chip",
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

    # --- Dynamic slot discovery ---
    # The PIA decoder stores any (bus_id, sensor_id) pair NOT in SENSOR_MAP
    # under a fallback key "bus{B}_s{S}".  Watch the coordinator for new such
    # keys and create a generic, disabled-by-default diagnostic sensor for
    # each one so users can opt-in to inspect raw values from the SCU.
    discovered: set[str] = set()

    @callback
    def _async_discover_slots() -> None:
        if not coordinator.data:
            return
        sensors = coordinator.data.get("signalr_sensors")
        if not isinstance(sensors, dict):
            return
        new_entities: list[HymerDiscoveredSensor] = []
        for key in sensors:
            if key in discovered:
                continue
            match = _DISCOVERED_KEY_RE.match(key)
            if not match:
                continue
            discovered.add(key)
            bus_id = int(match.group(1))
            sensor_id = int(match.group(2))
            new_entities.append(
                HymerDiscoveredSensor(coordinator, entry, bus_id, sensor_id)
            )
            _LOGGER.info(
                "Discovered unmapped slot (%d,%d) — creating diagnostic entity %s",
                bus_id, sensor_id, key,
            )
        if new_entities:
            async_add_entities(new_entities)

    # Run once for any data already present, then on every coordinator update.
    _async_discover_slots()
    entry.async_on_unload(coordinator.async_add_listener(_async_discover_slots))


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

        # Computed solar power = voltage × current
        if path == "computed.solar_power":
            sensors = self.coordinator.data.get("signalr_sensors", {})
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
            charger_active = sensors.get("charger_active")
            solar_charging = isinstance(solar_current, (int, float)) and solar_current > 0
            mains_charging = charger_active is True or charger_active == 1
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


class HymerDiscoveredSensor(
    CoordinatorEntity[HymerConnectCoordinator], SensorEntity
):
    """Generic diagnostic sensor for an unmapped PIA (bus, slot) pair.

    Created dynamically when the SCU reports a sensor whose (bus_id,
    sensor_id) is not present in :data:`pia_decoder.SENSOR_MAP`.  These
    entities are disabled by default so they never appear in the UI unless
    the user explicitly enables them via the entity registry.

    Their primary purpose is to make discovery (previously only available
    via ``tools/discover_sensors.py``) accessible from inside Home
    Assistant — users can enable a slot, observe how its value reacts to
    physical actions, and propose a mapping for ``SENSOR_MAP``.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:help-circle-outline"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
        bus_id: int,
        sensor_id: int,
    ) -> None:
        """Initialize a discovered slot sensor."""
        super().__init__(coordinator)
        self._bus_id = bus_id
        self._sensor_id = sensor_id
        self._key = f"bus{bus_id}_s{sensor_id}"
        self._attr_unique_id = f"{entry.entry_id}_discovered_{self._key}"
        self._attr_name = f"Discovered bus {bus_id} slot {sensor_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    @property
    def native_value(self) -> Any | None:
        """Return the raw value reported by the SCU for this slot."""
        if self.coordinator.data is None:
            return None
        sensors = self.coordinator.data.get("signalr_sensors")
        if not isinstance(sensors, dict):
            return None
        value = sensors.get(self._key)
        # Coerce non-primitive types so HA's state machine can store them.
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value
