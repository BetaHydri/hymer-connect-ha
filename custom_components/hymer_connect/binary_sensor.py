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
        on_value="ON",
        icon="mdi:car-brake-parking",
    ),
    HymerBinarySensorEntityDescription(
        key="charger_active",
        translation_key="charger_active",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_path="signalr_sensors.charger_active",
        icon="mdi:battery-charging",
    ),
    HymerBinarySensorEntityDescription(
        key="solar_connected",
        translation_key="solar_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_path="signalr_sensors.solar_connected",
        on_value=1,
        icon="mdi:solar-power",
    ),
    HymerBinarySensorEntityDescription(
        key="gps_fix",
        translation_key="gps_fix",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.gps_fix",
        icon="mdi:crosshairs-gps",
    ),
    HymerBinarySensorEntityDescription(
        key="scu_connected",
        translation_key="scu_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.scu_connected",
        icon="mdi:access-point",
    ),
    HymerBinarySensorEntityDescription(
        key="cruise_control",
        translation_key="cruise_control",
        value_path="signalr_sensors.cruise_control",
        icon="mdi:car-cruise-control",
    ),
    HymerBinarySensorEntityDescription(
        key="light_living_ceiling",
        translation_key="light_living_ceiling",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.light_living_ceiling",
        icon="mdi:ceiling-light",
    ),
    # --- Doors ---
    # The chassis CAN (bus 1) on Sprinter-based vehicles only surfaces one
    # door state and one habitation-entrance state. Previous "passenger",
    # "sliding" and "rear" entities read slots that actually reported
    # washer-fluid, oil-warning and wiping-water flags; removed to avoid
    # misleading values. Fiat Ducato-based vehicles expose all four doors
    # on a different component (VehicleFiatChassis) that this integration
    # does not yet wire up.
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
        icon="mdi:door-sliding",
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
    # --- Chassis state (bus 1) ---
    # Slots (1, 18-22) previously exposed headlamp / high-beam / parking /
    # fog-front / fog-rear / turn-signal binary sensors. Their values on
    # a 2025 S700 don't track those functions — the same slots carry
    # ParkingBrakeEngaged / StandheizungAvailable / Standheizung /
    # CruiseControlActive / DownhillAssistActive instead. The vehicle
    # lamp-state signals likely live on a different component that this
    # integration does not yet wire up. Replacing the lamp entities with
    # the driver-assist / night-heater flags they actually report.
    HymerBinarySensorEntityDescription(
        key="standheizung_available",
        translation_key="standheizung_available",
        value_path="signalr_sensors.standheizung_available",
        on_value="ON",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="standheizung_state",
        translation_key="standheizung_state",
        device_class=BinarySensorDeviceClass.HEAT,
        value_path="signalr_sensors.standheizung_state",
        on_value="ON",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="cruise_control_active",
        translation_key="cruise_control_active",
        value_path="signalr_sensors.cruise_control_active",
        on_value="ON",
        icon="mdi:car-cruise-control",
    ),
    HymerBinarySensorEntityDescription(
        key="downhill_assist_active",
        translation_key="downhill_assist_active",
        value_path="signalr_sensors.downhill_assist_active",
        on_value="ON",
        icon="mdi:arrow-down-bold",
    ),
    HymerBinarySensorEntityDescription(
        key="wiping_water_empty",
        translation_key="wiping_water_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.wiping_water_empty",
        on_value="ON",
        icon="mdi:car-wash",
    ),
    HymerBinarySensorEntityDescription(
        key="cooling_water_empty",
        translation_key="cooling_water_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.cooling_water_empty",
        on_value="ON",
        icon="mdi:coolant-temperature",
    ),
    HymerBinarySensorEntityDescription(
        key="motor_oil_warning",
        translation_key="motor_oil_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.motor_oil_warning",
        on_value="ON",
        icon="mdi:oil-level",
    ),
    HymerBinarySensorEntityDescription(
        key="lightsense_night",
        translation_key="lightsense_night",
        value_path="signalr_sensors.lightsense_night",
        icon="mdi:weather-night",
    ),
    # --- Truma ---
    HymerBinarySensorEntityDescription(
        key="truma_connected",
        translation_key="truma_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.truma_connected",
        icon="mdi:radiator",
    ),
    # --- Interior lights ---
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
    # --- Solar ---
    # Derived from solar_current: True when solar current > 0
    HymerBinarySensorEntityDescription(
        key="solar_active",
        translation_key="solar_active",
        device_class=BinarySensorDeviceClass.POWER,
        value_path="computed.solar_active",
        icon="mdi:solar-power",
    ),
    # --- Water pump ---
    HymerBinarySensorEntityDescription(
        key="water_pump",
        translation_key="water_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_path="signalr_sensors.light_nightlight",
        icon="mdi:water-pump",
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
            "name": f"HYMER {entry.title}",
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
