"""Select platform for HYMER Connect — enum-valued SCU controls.

Used for sensors that accept a small, fixed set of string or integer
options. The Truma heater exposes three such settings: the electric
power limit (0/900/1800 W) and two energy-source selectors for the
air-heating and water-heating subsystems ("Diesel"/"Electric"/"Both").

Each SelectEntity maps friendly UI options onto the raw values the SCU
expects on the wire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HymerSelectEntityDescription(SelectEntityDescription):
    """Describe a HYMER Connect select control.

    option_map is an ordered mapping from the UI option label (shown in HA)
    to the raw value the SCU expects. Values may be int or str.
    """

    bus_id: int
    sensor_id: int
    value_path: str
    option_map: dict[str, Any] = field(default_factory=dict)


SELECT_DESCRIPTIONS: tuple[HymerSelectEntityDescription, ...] = (
    HymerSelectEntityDescription(
        key="heater_power_limit_ctrl",
        translation_key="heater_power_limit_ctrl",
        bus_id=58,
        sensor_id=9,
        value_path="signalr_sensors.heater_electric_power",
        option_map={"Off": 0, "900 W": 900, "1800 W": 1800},
        icon="mdi:lightning-bolt",
    ),
    HymerSelectEntityDescription(
        key="heater_air_energy_source_ctrl",
        translation_key="heater_air_energy_source_ctrl",
        bus_id=58,
        sensor_id=4,
        value_path="signalr_sensors.heater_fuel_type",
        option_map={"Diesel": "Diesel", "Electric": "Electric", "Both": "Both"},
        icon="mdi:radiator",
    ),
    HymerSelectEntityDescription(
        key="heater_water_energy_source_ctrl",
        translation_key="heater_water_energy_source_ctrl",
        bus_id=58,
        sensor_id=6,
        value_path="signalr_sensors.heater_fuel_type_2",
        option_map={"Diesel": "Diesel", "Electric": "Electric", "Both": "Both"},
        icon="mdi:water-boiler",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect select entities from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectSelect(coordinator, desc, entry)
        for desc in SELECT_DESCRIPTIONS
    )


class HymerConnectSelect(
    CoordinatorEntity[HymerConnectCoordinator], SelectEntity
):
    """Representation of a HYMER Connect select control."""

    entity_description: HymerSelectEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerSelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_options = list(description.option_map.keys())
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"HYMER {entry.title}",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic_option: str | None = None

    @property
    def current_option(self) -> str | None:
        """Return the current SCU value as one of the configured options."""
        if self._optimistic_option is not None:
            return self._optimistic_option
        if self.coordinator.data is None:
            return None
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return None
        for label, raw in self.entity_description.option_map.items():
            if raw == value:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the SCU."""
        raw = self.entity_description.option_map.get(option)
        if raw is None:
            _LOGGER.warning(
                "Unknown option %r for %s",
                option,
                self.entity_description.key,
            )
            return
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning(
                "Cannot set %s — SignalR not connected",
                self.entity_description.key,
            )
            return

        if isinstance(raw, bool):
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                bool_value=raw,
            )
        elif isinstance(raw, int):
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                uint_value=raw,
            )
        else:
            # String option. send_light_command can't express strings; fall
            # back to the more general build_sensor_write (added in PR #31)
            # if it's available, otherwise warn.
            try:
                from .pia_decoder import build_sensor_write
            except ImportError:
                _LOGGER.warning(
                    "String select not supported on this version of the "
                    "integration — need build_sensor_write helper."
                )
                return
            payload = build_sensor_write(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                raw,
            )
            await client.send_pia_request(payload)

        self._optimistic_option = option
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when the SCU confirms the commanded option."""
        if self._optimistic_option is not None and self.coordinator.data:
            value = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            expected = self.entity_description.option_map.get(
                self._optimistic_option
            )
            if value is not None and value == expected:
                self._optimistic_option = None
        super()._handle_coordinator_update()
