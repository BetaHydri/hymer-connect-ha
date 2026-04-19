"""Binary sensor platform for HYMER Connect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path


@dataclass(frozen=True, kw_only=True)
class HymerBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a HYMER Connect binary sensor."""

    value_path: str
    on_value: Any = True


BINARY_SENSOR_DESCRIPTIONS: tuple[HymerBinarySensorEntityDescription, ...] = (
    # --- Bus 1 — Chassis flags ---
    HymerBinarySensorEntityDescription(
        key="engine_running",
        translation_key="engine_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_path="signalr_sensors.engine_running",
        icon="mdi:engine",
    ),
    HymerBinarySensorEntityDescription(
        key="parking_brake_engaged",
        translation_key="parking_brake_engaged",
        value_path="signalr_sensors.parking_brake_engaged",
        icon="mdi:car-brake-parking",
    ),
    HymerBinarySensorEntityDescription(
        key="cruise_control_active",
        translation_key="cruise_control_active",
        value_path="signalr_sensors.cruise_control_active",
        icon="mdi:car-cruise-control",
    ),
    HymerBinarySensorEntityDescription(
        key="downhill_assist_active",
        translation_key="downhill_assist_active",
        value_path="signalr_sensors.downhill_assist_active",
        icon="mdi:arrow-down-bold",
    ),
    HymerBinarySensorEntityDescription(
        key="standheizung_available",
        translation_key="standheizung_available",
        value_path="signalr_sensors.standheizung_available",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="standheizung_state",
        translation_key="standheizung_state",
        device_class=BinarySensorDeviceClass.HEAT,
        value_path="signalr_sensors.standheizung_state",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="lightsense_night",
        translation_key="lightsense_night",
        value_path="signalr_sensors.lightsense_night",
        icon="mdi:weather-night",
    ),
    HymerBinarySensorEntityDescription(
        key="wiping_water_empty",
        translation_key="wiping_water_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.wiping_water_empty",
        icon="mdi:wiper-wash",
    ),
    HymerBinarySensorEntityDescription(
        key="motor_oil_warning",
        translation_key="motor_oil_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.motor_oil_warning",
        icon="mdi:oil",
    ),
    HymerBinarySensorEntityDescription(
        key="cooling_water_empty",
        translation_key="cooling_water_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.cooling_water_empty",
        icon="mdi:coolant-temperature",
    ),
    # --- Doors (HA auto-translates: Offen/Geschlossen) ---
    HymerBinarySensorEntityDescription(
        key="door_driver",
        translation_key="door_driver",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.door_driver",
        on_value="Open",
        icon="mdi:car-door",
    ),
    HymerBinarySensorEntityDescription(
        key="door_entrance",
        translation_key="door_entrance",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.door_entrance",
        on_value="Open",
        icon="mdi:door",
    ),
    # --- Lock (HA auto-translates: Gesperrt/Entsperrt) ---
    HymerBinarySensorEntityDescription(
        key="lock_status",
        translation_key="lock_status",
        device_class=BinarySensorDeviceClass.LOCK,
        value_path="signalr_sensors.lock_status",
        on_value="Unlocked",
        icon="mdi:lock",
    ),
    # --- Main switch ---
    HymerBinarySensorEntityDescription(
        key="main_switch",
        translation_key="main_switch",
        device_class=BinarySensorDeviceClass.POWER,
        value_path="signalr_sensors.main_switch",
        on_value="On",
        icon="mdi:power",
    ),
    # --- Bus 3 — Shore power & EBL health ---
    HymerBinarySensorEntityDescription(
        key="shoreline_connected",
        translation_key="shoreline_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_path="signalr_sensors.shoreline_connected",
        icon="mdi:power-plug",
    ),
    HymerBinarySensorEntityDescription(
        key="ebl_over_temperature",
        translation_key="ebl_over_temperature",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.ebl_over_temperature",
        icon="mdi:alert-circle",
    ),
    # --- Bus 8 — Solar ---
    # "solar_active" is computed from solar_current for reliability; the
    # direct SolarActive flag from (8,1) is also published as a diagnostic.
    HymerBinarySensorEntityDescription(
        key="solar_active",
        translation_key="solar_active",
        device_class=BinarySensorDeviceClass.POWER,
        value_path="computed.solar_active",
        icon="mdi:solar-power",
    ),
    HymerBinarySensorEntityDescription(
        key="solar_reduced_power",
        translation_key="solar_reduced_power",
        value_path="signalr_sensors.solar_reduced_power",
        icon="mdi:solar-power-variant-outline",
    ),
    HymerBinarySensorEntityDescription(
        key="solar_aes_active",
        translation_key="solar_aes_active",
        value_path="signalr_sensors.solar_aes_active",
        icon="mdi:solar-power",
    ),
    # --- Bus 30 — SCU state ---
    HymerBinarySensorEntityDescription(
        key="vehicle_movement",
        translation_key="vehicle_movement",
        device_class=BinarySensorDeviceClass.MOTION,
        value_path="signalr_sensors.vehicle_movement",
        icon="mdi:motion-sensor",
    ),
    HymerBinarySensorEntityDescription(
        key="scu_connected",
        translation_key="scu_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.scu_connected",
        icon="mdi:access-point",
    ),
    # --- Bus 49 — Truma connectivity ---
    HymerBinarySensorEntityDescription(
        key="truma_connected",
        translation_key="truma_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.truma_connected",
        icon="mdi:radiator",
    ),
    # --- Bus 99 — BMS flags ---
    HymerBinarySensorEntityDescription(
        key="bms_charge_detected",
        translation_key="bms_charge_detected",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_path="signalr_sensors.bms_charge_detected",
        icon="mdi:battery-charging",
    ),
    HymerBinarySensorEntityDescription(
        key="bms_device_failure",
        translation_key="bms_device_failure",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.bms_device_failure",
        icon="mdi:battery-alert",
    ),
    # --- Interior lights (on/off) ---
    HymerBinarySensorEntityDescription(
        key="light_living_ceiling",
        translation_key="light_living_ceiling",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_living_ceiling",
        icon="mdi:ceiling-light",
    ),
    HymerBinarySensorEntityDescription(
        key="light_living_ambient",
        translation_key="light_living_ambient",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_living_ambient",
        icon="mdi:wall-sconce-flat",
    ),
    HymerBinarySensorEntityDescription(
        key="light_kitchen",
        translation_key="light_kitchen",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_kitchen",
        icon="mdi:ceiling-light",
    ),
    HymerBinarySensorEntityDescription(
        key="light_seating_overhead",
        translation_key="light_seating_overhead",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_seating_overhead",
        icon="mdi:ceiling-light",
    ),
    HymerBinarySensorEntityDescription(
        key="light_bedroom_ambient",
        translation_key="light_bedroom_ambient",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_bedroom_ambient",
        icon="mdi:wall-sconce-flat",
    ),
    HymerBinarySensorEntityDescription(
        key="light_nightlight",
        translation_key="light_nightlight",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_nightlight",
        icon="mdi:lightbulb-night",
    ),
    HymerBinarySensorEntityDescription(
        key="light_bathroom_ceiling",
        translation_key="light_bathroom_ceiling",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_bathroom_ceiling",
        icon="mdi:ceiling-light",
    ),
    HymerBinarySensorEntityDescription(
        key="light_bedroom_overhead",
        translation_key="light_bedroom_overhead",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_bedroom_overhead",
        icon="mdi:ceiling-light",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect binary sensors from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectBinarySensor(coordinator, desc, entry)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class HymerConnectBinarySensor(
    CoordinatorEntity[HymerConnectCoordinator], BinarySensorEntity
):
    """Representation of a HYMER Connect binary sensor."""

    entity_description: HymerBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerBinarySensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        if self.coordinator.data is None:
            return None

        path = self.entity_description.value_path

        # Computed binary sensors
        if path == "computed.solar_active":
            sensors = self.coordinator.data.get("signalr_sensors", {})
            current = sensors.get("solar_current")
            if isinstance(current, (int, float)):
                return current > 0
            return None

        value = _resolve_path(self.coordinator.data, path)
        if value is None:
            return None
        return value == self.entity_description.on_value
