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
        key="handbrake",
        translation_key="handbrake",
        value_path="signalr_sensors.handbrake",
        on_value=1,
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
        key="door_passenger",
        translation_key="door_passenger",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.door_passenger",
        on_value="Open",
        icon="mdi:car-door",
    ),
    HymerBinarySensorEntityDescription(
        key="door_sliding",
        translation_key="door_sliding",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.door_sliding",
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
    # --- Rear door ---
    HymerBinarySensorEntityDescription(
        key="door_rear",
        translation_key="door_rear",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.door_rear",
        on_value="Open",
        icon="mdi:car-door",
    ),
    # --- Vehicle lights ---
    HymerBinarySensorEntityDescription(
        key="headlamp",
        translation_key="headlamp",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.headlamp",
        on_value="On",
        icon="mdi:car-light-high",
    ),
    HymerBinarySensorEntityDescription(
        key="high_beam",
        translation_key="high_beam",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.high_beam",
        on_value="On",
        icon="mdi:car-light-high",
    ),
    HymerBinarySensorEntityDescription(
        key="parking_light",
        translation_key="parking_light",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.parking_light",
        on_value="On",
        icon="mdi:car-parking-lights",
    ),
    HymerBinarySensorEntityDescription(
        key="fog_front",
        translation_key="fog_front",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.fog_front",
        on_value="On",
        icon="mdi:car-light-fog",
    ),
    HymerBinarySensorEntityDescription(
        key="fog_rear",
        translation_key="fog_rear",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_path="signalr_sensors.fog_rear",
        on_value="On",
        icon="mdi:car-light-fog",
    ),
    HymerBinarySensorEntityDescription(
        key="turn_signal",
        translation_key="turn_signal",
        value_path="signalr_sensors.turn_signal",
        on_value="On",
        icon="mdi:car-turn-signal",
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
