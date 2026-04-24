"""Button platform for HYMER Connect integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect button entities."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HymerRestartButton(coordinator, entry),
    ])


class HymerRestartButton(
    CoordinatorEntity[HymerConnectCoordinator], ButtonEntity
):
    """SCU restart button — sends a cold reboot command to the Smart Control Unit.

    The SCU will disconnect from the cloud, reboot, and reconnect.
    This is useful when the SCU is stuck or not responding to commands.
    The integration will automatically reconnect after the reboot (~30-60s).
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart-alert"

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the restart button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_restart_system"
        self._attr_name = "Restart SCU"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }

    @property
    def available(self) -> bool:
        """Only available when SignalR is connected."""
        client = self.coordinator.signalr_client
        return client is not None and client.connected

    async def async_press(self) -> None:
        """Send SCU restart command."""
        await self.coordinator.async_send_restart_system_command()
