"""Binary sensor platform for HYMER Connect.

Most binary sensor entity descriptions are generated dynamically from
JSON-defined entity metadata in ``sensor_maps/*.json``.  Only entities
with computed values or cross-referenced source keys stay hardcoded.
"""

from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HymerBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a HYMER Connect binary sensor."""

    value_path: str
    on_value: Any = True


# ---------------------------------------------------------------------------
# Static binary sensor descriptions — entities with computed values or
# cross-referenced source keys that cannot be expressed in JSON.
# ---------------------------------------------------------------------------
STATIC_BINARY_SENSORS: tuple[HymerBinarySensorEntityDescription, ...] = (
    # cruise_control reads from "cruise_control" which has no SENSOR_MAP entry
    HymerBinarySensorEntityDescription(
        key="cruise_control",
        translation_key="cruise_control",
        value_path="signalr_sensors.cruise_control",
        icon="mdi:car-cruise-control",
    ),
    # Solar active is computed from solar_current > 0
    HymerBinarySensorEntityDescription(
        key="solar_active",
        translation_key="solar_active",
        device_class=BinarySensorDeviceClass.POWER,
        value_path="computed.solar_active",
        icon="mdi:solar-power",
    ),
    # Water pump reads from light_nightlight (cross-ref)
    HymerBinarySensorEntityDescription(
        key="water_pump",
        translation_key="water_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_path="signalr_sensors.light_nightlight",
        icon="mdi:water-pump",
    ),
    # Fridge door reads from fridge_status (cross-ref)
    HymerBinarySensorEntityDescription(
        key="fridge_door",
        translation_key="fridge_door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_path="signalr_sensors.fridge_status",
        on_value="Open",
        icon="mdi:fridge-outline",
    ),
)

# Keys of static descriptions — the dynamic builder skips these.
_STATIC_BINARY_KEYS: set[str] = {d.key for d in STATIC_BINARY_SENSORS}


def _build_dynamic_binary_sensors() -> list[HymerBinarySensorEntityDescription]:
    """Build binary sensor entity descriptions from JSON-loaded ENTITY_DEFS."""
    from .pia_decoder import ENTITY_DEFS

    descriptions: list[HymerBinarySensorEntityDescription] = []
    for name, meta in ENTITY_DEFS.items():
        if meta.get("platform") != "binary_sensor":
            continue
        if name in _STATIC_BINARY_KEYS:
            continue
        kwargs: dict[str, Any] = {
            "key": name,
            "translation_key": name,
            "value_path": f"signalr_sensors.{name}",
        }
        if meta.get("device_class"):
            kwargs["device_class"] = BinarySensorDeviceClass(meta["device_class"])
        if meta.get("icon"):
            kwargs["icon"] = meta["icon"]
        if "on_value" in meta:
            kwargs["on_value"] = meta["on_value"]
        if meta.get("enabled") is False:
            kwargs["entity_registry_enabled_default"] = False
        descriptions.append(HymerBinarySensorEntityDescription(**kwargs))
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect binary sensors from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Build the full description list: static + JSON-driven dynamic
    dynamic = _build_dynamic_binary_sensors()
    all_descriptions = STATIC_BINARY_SENSORS + tuple(dynamic)
    _LOGGER.debug(
        "Binary sensor platform: %d static + %d dynamic = %d total descriptions",
        len(STATIC_BINARY_SENSORS),
        len(dynamic),
        len(all_descriptions),
    )

    async_add_entities(
        HymerConnectBinarySensor(coordinator, desc, entry)
        for desc in all_descriptions
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
