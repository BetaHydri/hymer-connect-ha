"""Button platform for HYMER Connect — one-shot commands to the SCU."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HymerButtonEntityDescription(ButtonEntityDescription):
    """Describe a HYMER Connect button — a write-only SCU command."""

    bus_id: int
    sensor_id: int


# These slots are write-only in the SCU's capability surface: sending a
# boolean true pokes the SCU to do something (wake the chassis over cellular,
# force an immediate fresh water-tank read, etc.) rather than flipping a
# long-lived toggle. Pressing the button posts a single command; there is no
# corresponding read-back value.
BUTTON_DESCRIPTIONS: tuple[HymerButtonEntityDescription, ...] = (
    HymerButtonEntityDescription(
        key="wake_up_chassis_ctrl",
        translation_key="wake_up_chassis_ctrl",
        bus_id=30,
        sensor_id=11,
        icon="mdi:sleep-off",
    ),
    HymerButtonEntityDescription(
        key="update_tank_level_immediately_ctrl",
        translation_key="update_tank_level_immediately_ctrl",
        bus_id=3,
        sensor_id=21,
        icon="mdi:water-sync",
    ),
    HymerButtonEntityDescription(
        key="activate_tank_refill_interval_ctrl",
        translation_key="activate_tank_refill_interval_ctrl",
        bus_id=3,
        sensor_id=20,
        icon="mdi:water-pump",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect buttons from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectButton(coordinator, desc, entry)
        for desc in BUTTON_DESCRIPTIONS
    )


class HymerConnectButton(
    CoordinatorEntity[HymerConnectCoordinator], ButtonEntity
):
    """Representation of a HYMER Connect button."""

    entity_description: HymerButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerButtonEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"HYMER {entry.title}",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    async def async_press(self) -> None:
        """Fire the write-only command."""
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            _LOGGER.warning(
                "Cannot press %s — SignalR not connected",
                self.entity_description.key,
            )
            return
        await client.send_light_command(
            self.entity_description.bus_id,
            self.entity_description.sensor_id,
            bool_value=True,
        )
