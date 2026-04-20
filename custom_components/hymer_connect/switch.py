"""Switch platform for HYMER Connect — controllable switches."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HymerConnectCoordinator
from .sensor import _resolve_path

_LOGGER = logging.getLogger(__name__)

# How long (seconds) to hold optimistic state after commanding the 12V main
# switch OFF.  The SCU runs on the chassis battery and stays alive when the
# habitation 12V is cut.  During its reconnection cycle (~5 s) it pushes a
# stale cached "On" value that would overwrite the commanded "Off".  The EHG
# app handles this by caching the commanded state client-side.
#
# Observed in mitmproxy trace (2026-04-19):
#   19:56:02 — main_switch = "Off"   (command accepted)
#   19:56:03 — scu_connected = false (SCU briefly disconnects)
#   19:56:08 — main_switch = "On"    (stale readback after reconnection)
#
# We hold the optimistic OFF for 30 s to ride through this bounce-back.
# The ON direction doesn't need a holdoff — the SCU confirms "On" immediately.
_MAIN_SWITCH_OFF_HOLDOFF_S = 30


@dataclass(frozen=True, kw_only=True)
class HymerSwitchEntityDescription(SwitchEntityDescription):
    """Describe a HYMER Connect switch."""

    bus_id: int
    sensor_id: int
    value_path: str
    on_value: Any = True


SWITCH_DESCRIPTIONS: tuple[HymerSwitchEntityDescription, ...] = (
    HymerSwitchEntityDescription(
        key="main_switch_ctrl",
        translation_key="main_switch_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=3,
        sensor_id=1,
        value_path="signalr_sensors.main_switch",
        on_value="On",
        icon="mdi:power",
    ),
    HymerSwitchEntityDescription(
        key="water_pump_ctrl",
        translation_key="water_pump_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=3,
        sensor_id=3,
        value_path="signalr_sensors.charger_active",
        on_value=True,
        icon="mdi:water-pump",
    ),
    HymerSwitchEntityDescription(
        key="fridge_eco_ctrl",
        translation_key="fridge_eco_ctrl",
        device_class=SwitchDeviceClass.SWITCH,
        bus_id=34,
        sensor_id=2,
        value_path="signalr_sensors.fridge_eco",
        on_value=True,
        icon="mdi:leaf",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect switches from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HymerConnectSwitch(coordinator, desc, entry)
        for desc in SWITCH_DESCRIPTIONS
    )


class HymerConnectSwitch(
    CoordinatorEntity[HymerConnectCoordinator], SwitchEntity
):
    """Representation of a HYMER Connect switch."""

    entity_description: HymerSwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HymerConnectCoordinator,
        description: HymerSwitchEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "HYMER",
            "manufacturer": MANUFACTURER,
            "model": "Smart Interface Unit",
        }
        self._optimistic_on: bool | None = None
        self._optimistic_set_at: float = 0.0  # monotonic timestamp of last command
        self._verify_task: asyncio.Task | None = None

    async def _verify_send(self, expected_on: bool) -> None:
        """Verify the SCU acknowledged the command after a delay.

        If the readback doesn't match the expected state after 15 seconds,
        the SignalR connection is likely stale. Force a reconnect by marking
        the client as disconnected so the coordinator reconnects on next poll.
        """
        await asyncio.sleep(15)
        # Read the actual SCU readback (not optimistic)
        if self.coordinator.data is None:
            return
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return
        actual_on = value == self.entity_description.on_value
        if actual_on != expected_on:
            _LOGGER.warning(
                "Switch %s: SCU readback (%s) doesn't match commanded (%s) "
                "after 15s — SignalR send channel likely dead, forcing reconnect",
                self.entity_description.key, value, expected_on,
            )
            client = self.coordinator.signalr_client
            if client:
                client._connected = False
                _LOGGER.info("Marked SignalR as disconnected — will reconnect on next poll")

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        if self._optimistic_on is not None:
            return self._optimistic_on
        if self.coordinator.data is None:
            return None
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return None
        return value == self.entity_description.on_value

    async def _ensure_connected(self) -> None:
        """Ensure SignalR is connected, attempt reconnect if not."""
        client = self.coordinator.signalr_client
        if client and client.connected:
            return
        _LOGGER.info("SignalR not connected — attempting reconnect before switch command")
        await self.coordinator.start_signalr()
        client = self.coordinator.signalr_client
        if not client or not client.connected:
            raise HomeAssistantError(
                "Cannot control switch — SignalR not connected. "
                "Try reloading the integration."
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._ensure_connected()
        client = self.coordinator.signalr_client
        on_val = self.entity_description.on_value
        if isinstance(on_val, str):
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                str_value=on_val,
            )
        else:
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                bool_value=True,
            )
        self._optimistic_on = True
        self._optimistic_set_at = time.monotonic()
        # Optimistically update main_switch in SignalR sensor_data so the
        # standby bypass in needs_reconnect doesn't block auto-recovery
        # if the connection dies during the SCU reboot after 12V toggle.
        if self.entity_description.key == "main_switch_ctrl" and client:
            client._sensor_data["main_switch"] = on_val if isinstance(on_val, str) else "On"
        self.async_write_ha_state()
        # Schedule send verification — detect stale SignalR connections
        if self._verify_task and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = asyncio.ensure_future(self._verify_send(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._ensure_connected()
        client = self.coordinator.signalr_client
        on_val = self.entity_description.on_value
        if isinstance(on_val, str):
            off_val = "Off" if on_val == "On" else "False"
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                str_value=off_val,
            )
        else:
            await client.send_light_command(
                self.entity_description.bus_id,
                self.entity_description.sensor_id,
                bool_value=False,
            )
        self._optimistic_on = False
        self._optimistic_set_at = time.monotonic()
        # Optimistically update main_switch in SignalR sensor_data so the
        # standby bypass in needs_reconnect reflects the commanded state.
        if self.entity_description.key == "main_switch_ctrl" and client:
            client._sensor_data["main_switch"] = "Off" if isinstance(on_val, str) else False
        self.async_write_ha_state()
        # Schedule send verification — detect stale SignalR connections
        if self._verify_task and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = asyncio.ensure_future(self._verify_send(False))

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when SCU confirms the commanded value.

        Special handling for the 12V main switch OFF command:
        The SCU stays powered via the chassis battery when habitation 12V is
        cut. During its ~5s reconnection cycle it pushes a stale cached "On"
        that would overwrite our commanded "Off". We hold the optimistic OFF
        state for _MAIN_SWITCH_OFF_HOLDOFF_S seconds to ignore this bounce.
        """
        if self._optimistic_on is not None and self.coordinator.data:
            value = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            if value is not None:
                actual = value == self.entity_description.on_value

                # For the 12V main switch OFF: hold optimistic state through
                # the stale bounce-back window
                if (
                    self._optimistic_on is False
                    and actual is True
                    and self.entity_description.key == "main_switch_ctrl"
                ):
                    elapsed = time.monotonic() - self._optimistic_set_at
                    if elapsed < _MAIN_SWITCH_OFF_HOLDOFF_S:
                        _LOGGER.debug(
                            "12V switch: ignoring stale 'On' readback "
                            "%.1fs after OFF command (holdoff %ds)",
                            elapsed,
                            _MAIN_SWITCH_OFF_HOLDOFF_S,
                        )
                        super()._handle_coordinator_update()
                        return

                if actual == self._optimistic_on:
                    self._optimistic_on = None
        super()._handle_coordinator_update()
