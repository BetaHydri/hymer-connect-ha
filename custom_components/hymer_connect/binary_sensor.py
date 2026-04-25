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
    # Confirmed at vehicle 2026-04-20:
    #   Original: (1,11)=driver, (1,12)=passenger, (1,13)=sliding
    #   Reality:  (1,12)=driver, (1,13)=passenger
    #   (1,11) did NOT update on S600; (1,14) also no updates.
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
    # --- Vehicle warnings (slots 1,11 and 1,14 — per S700 PR #44) ---
    HymerBinarySensorEntityDescription(
        key="wiping_water_empty",
        translation_key="wiping_water_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.wiping_water_empty",
        on_value="On",
        icon="mdi:wiper-wash",
    ),
    HymerBinarySensorEntityDescription(
        key="motor_oil_warning",
        translation_key="motor_oil_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.motor_oil_warning",
        on_value="On",
        icon="mdi:oil",
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
    # --- Chassis state flags (bus 1, slots 17-22) ---
    # Previously mislabelled as vehicle lights. Confirmed via PR #44 S700
    # observations + S600 live data: (1,18) read "ON" while parked = parking
    # brake engaged, not headlamp.
    HymerBinarySensorEntityDescription(
        key="parking_brake",
        translation_key="parking_brake",
        value_path="signalr_sensors.parking_brake",
        on_value="On",
        icon="mdi:car-brake-parking",
    ),
    HymerBinarySensorEntityDescription(
        key="standheizung_available",
        translation_key="standheizung_available",
        value_path="signalr_sensors.standheizung_available",
        on_value="On",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="standheizung_state",
        translation_key="standheizung_state",
        device_class=BinarySensorDeviceClass.HEAT,
        value_path="signalr_sensors.standheizung_state",
        on_value="On",
        icon="mdi:radiator",
    ),
    HymerBinarySensorEntityDescription(
        key="cruise_control_can",
        translation_key="cruise_control_can",
        value_path="signalr_sensors.cruise_control_can",
        on_value="On",
        icon="mdi:car-cruise-control",
    ),
    HymerBinarySensorEntityDescription(
        key="downhill_assist",
        translation_key="downhill_assist",
        value_path="signalr_sensors.downhill_assist",
        on_value="On",
        icon="mdi:arrow-down-bold",
    ),
    HymerBinarySensorEntityDescription(
        key="coolant_warning",
        translation_key="coolant_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.coolant_warning",
        on_value="On",
        icon="mdi:coolant-temperature",
    ),
    HymerBinarySensorEntityDescription(
        key="shoreline_connected",
        translation_key="shoreline_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_path="signalr_sensors.shoreline_connected",
        on_value=1,
        icon="mdi:power-plug",
    ),
    # --- Truma ---
    HymerBinarySensorEntityDescription(
        key="truma_connected",
        translation_key="truma_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_path="signalr_sensors.truma_connected",
        icon="mdi:radiator",
    ),
    # --- Truma Combi (bus 58) — slot meanings from EHG app metadata ---
    # Window safety interlock: when the dinette window is open the SCU
    # cuts the diesel heater (the diesel exhaust outlet is on that side).
    # Exposing this as a binary_sensor lets users automate notifications.
    HymerBinarySensorEntityDescription(
        key="heater_window_switch_closed",
        translation_key="heater_window_switch_closed",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_path="signalr_sensors.heater_window_switch_closed",
        # Despite the EHG metadata name `window_switch_closed`, captured
        # traces (custom_components/logs/ws_capture_*.jsonl) show the slot
        # is actually a window-OPEN flag: resting state is `false` while
        # the window is closed, and it flips to `true` when the dinette
        # window is opened. So the raw value already matches HA's WINDOW
        # device class semantics (True = open) — no inversion needed.
        icon="mdi:window-closed-variant",
    ),
    HymerBinarySensorEntityDescription(
        key="heater_combi_error",
        translation_key="heater_combi_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.heater_combi_error",
        icon="mdi:alert-circle",
    ),
    HymerBinarySensorEntityDescription(
        key="heater_response_error",
        translation_key="heater_response_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_path="signalr_sensors.heater_response_error",
        icon="mdi:alert",
    ),
    HymerBinarySensorEntityDescription(
        key="heater_shoreline_connected",
        translation_key="heater_shoreline_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_path="signalr_sensors.heater_shoreline_connected",
        icon="mdi:power-plug",
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
    # --- Fridge door (bus 37, sid 2) ---
    # SCU reports int 0/1, pia_decoder maps via _INT_LABELS to "Open"/"Closed".
    # NOTE: The fridge door sensor only updates via SignalR when the SCU is
    # fully online (12V ON). With 12V off, the SCU is in standby and does not
    # push passive sensor changes to the cloud. The EHG app can still see door
    # changes in standby because it connects via BLE directly to the SCU.
    # Commands (e.g. fridge power on/off) work in standby because the SCU
    # echoes command responses, but passive sensors like door state do not.
    HymerBinarySensorEntityDescription(
        key="fridge_door",
        translation_key="fridge_door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.fridge_status",
        on_value="Open",
        icon="mdi:fridge-outline",
    ),
    # --- Victron MultiPlus (bus 121) ---
    # Disabled by default — bus 121 not yet confirmed on S600.
    HymerBinarySensorEntityDescription(
        key="victron_inverter_on",
        translation_key="victron_inverter_on",
        device_class=BinarySensorDeviceClass.POWER,
        value_path="signalr_sensors.victron_inverter_on",
        entity_registry_enabled_default=False,
        icon="mdi:power-plug",
    ),
    HymerBinarySensorEntityDescription(
        key="victron_charger_on",
        translation_key="victron_charger_on",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_path="signalr_sensors.victron_charger_on",
        entity_registry_enabled_default=False,
        icon="mdi:battery-charging",
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
        on_value = self.entity_description.on_value
        # Case-insensitive comparison for string values to handle
        # SCU casing variations (e.g. "ON"/"On"/"on", "Open"/"OPEN").
        if isinstance(value, str) and isinstance(on_value, str):
            return value.upper() == on_value.upper()
        return value == on_value
