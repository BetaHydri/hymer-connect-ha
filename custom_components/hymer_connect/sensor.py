"""Sensor platform for HYMER Connect.

GUIDELINE: All new entities MUST be defined in sensor_maps/*.json
(base.json for universal buses, <brand>.json for brand-specific).
Only computed/calculated sensors (cross-referenced sources, formulas,
override logic) may remain as static Python descriptions.
The static descriptions below are legacy exceptions.
"""

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


# ---------------------------------------------------------------------------
# Static sensor descriptions — entities that need special handling or read
# from a source key different from their own name.
# ---------------------------------------------------------------------------

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

# Sensors that need special value logic, computed values, or cross-referenced
# source keys.  These MUST stay hardcoded because the dynamic builder cannot
# express their behaviour.
STATIC_SIGNALR_SENSORS: tuple[HymerSensorEntityDescription, ...] = (
    # --- Computed fuel metrics ---
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
    # --- Computed solar power (V × A) ---
    HymerSensorEntityDescription(
        key="solar_power",
        translation_key="solar_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="computed.solar_power",
        icon="mdi:solar-power",
    ),
    # --- Battery SoC reads from lithium_soc (bus 99), not battery_soc (bus 3) ---
    HymerSensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_path="signalr_sensors.lithium_soc",
        icon="mdi:battery",
    ),
    # --- Charge phase has special idle override logic ---
    HymerSensorEntityDescription(
        key="charge_phase",
        translation_key="charge_phase",
        value_path="signalr_sensors.charge_phase",
        icon="mdi:battery-charging",
    ),

)

# Keys of static descriptions — the dynamic builder skips these.
_STATIC_SENSOR_KEYS: set[str] = {
    d.key for d in REST_SENSORS + STATIC_SIGNALR_SENSORS
}


def _build_dynamic_sensors() -> list[HymerSensorEntityDescription]:
    """Build sensor entity descriptions from JSON-loaded ENTITY_DEFS.

    Only entries where ``platform == "sensor"`` produce a description.
    Entries whose name collides with a static description are skipped.
    """
    from .pia_decoder import ENTITY_DEFS

    descriptions: list[HymerSensorEntityDescription] = []
    for name, meta in ENTITY_DEFS.items():
        if meta.get("platform") != "sensor":
            continue
        if name in _STATIC_SENSOR_KEYS:
            continue
        kwargs: dict[str, Any] = {
            "key": name,
            "translation_key": name,
            "value_path": f"signalr_sensors.{name}",
        }
        if meta.get("unit"):
            kwargs["native_unit_of_measurement"] = meta["unit"]
        if meta.get("device_class"):
            kwargs["device_class"] = SensorDeviceClass(meta["device_class"])
        if meta.get("state_class"):
            kwargs["state_class"] = SensorStateClass(meta["state_class"])
        if meta.get("icon"):
            kwargs["icon"] = meta["icon"]
        if meta.get("enabled") is False:
            kwargs["entity_registry_enabled_default"] = False
        descriptions.append(HymerSensorEntityDescription(**kwargs))
    return descriptions


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

    # Build the full description list: static + JSON-driven dynamic
    dynamic = _build_dynamic_sensors()
    all_descriptions = REST_SENSORS + STATIC_SIGNALR_SENSORS + tuple(dynamic)
    _LOGGER.debug(
        "Sensor platform: %d static + %d dynamic = %d total descriptions",
        len(REST_SENSORS) + len(STATIC_SIGNALR_SENSORS),
        len(dynamic),
        len(all_descriptions),
    )

    async_add_entities(
        HymerConnectSensor(coordinator, desc, entry)
        for desc in all_descriptions
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
