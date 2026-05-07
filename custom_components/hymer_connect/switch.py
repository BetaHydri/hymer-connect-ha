"""Switch platform for HYMER Connect — controllable switches.

Switch definitions are loaded from JSON ``"switches"`` sections in
``sensor_maps/base.json`` + ``{brand}.json``.  Each entry defines the
bus/slot, write type (str/bool/uint), on/off values, and optional
holdoff for SCU bounce-back protection.
"""

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


@dataclass(frozen=True, kw_only=True)
class HymerSwitchEntityDescription(SwitchEntityDescription):
    """Describe a HYMER Connect switch."""

    bus_id: int
    sensor_id: int
    value_path: str
    on_value: Any = True
    write_type: str = "bool"       # "str", "bool", or "uint"
    write_on: Any = None           # value sent for ON (str switches)
    write_off: Any = None          # value sent for OFF (str switches)
    holdoff_off: int = 15          # seconds to hold optimistic OFF
    requires_12v: bool = False     # entity unavailable when 12V off
    is_main_switch: bool = False   # special main_switch optimistic hack


def _build_switch_descriptions() -> list[HymerSwitchEntityDescription]:
    """Build switch entity descriptions from JSON-loaded SWITCH_DEFS."""
    from .pia_decoder import SWITCH_DEFS

    descriptions: list[HymerSwitchEntityDescription] = []
    for key_str, meta in SWITCH_DEFS.items():
        if not isinstance(meta, dict) or "name" not in meta:
            continue
        parts = key_str.split(",")
        if len(parts) != 2:
            continue
        bus_id, sensor_id = int(parts[0].strip()), int(parts[1].strip())
        name = meta["name"]
        kwargs: dict[str, Any] = {
            "key": name,
            "translation_key": name,
            "device_class": SwitchDeviceClass.SWITCH,
            "bus_id": bus_id,
            "sensor_id": sensor_id,
            "value_path": meta.get("read_path", f"signalr_sensors.{name}"),
        }
        if "on_value" in meta:
            kwargs["on_value"] = meta["on_value"]
        if meta.get("icon"):
            kwargs["icon"] = meta["icon"]
        if meta.get("write_type"):
            kwargs["write_type"] = meta["write_type"]
        if "write_on" in meta:
            kwargs["write_on"] = meta["write_on"]
        if "write_off" in meta:
            kwargs["write_off"] = meta["write_off"]
        if "holdoff_off" in meta:
            kwargs["holdoff_off"] = meta["holdoff_off"]
        if meta.get("requires_12v"):
            kwargs["requires_12v"] = True
        if meta.get("enabled") is False:
            kwargs["entity_registry_enabled_default"] = False
        # Detect main switch for optimistic sensor_data hack
        if name == "main_switch_ctrl":
            kwargs["is_main_switch"] = True
        descriptions.append(HymerSwitchEntityDescription(**kwargs))
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HYMER Connect switches from a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions = _build_switch_descriptions()
    _LOGGER.debug("Switch platform: %d switch entities from JSON", len(descriptions))
    async_add_entities(
        HymerConnectSwitch(coordinator, desc, entry)
        for desc in descriptions
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
        self._retry_task: asyncio.Task | None = None

    async def _verify_send(self, expected_on: bool) -> None:
        """Verify the SCU acknowledged the command after a delay.

        When the SCU is offline (scu_connected=false), commands are queued
        server-side but not delivered until the SCU wakes up.  In that case
        we clear optimistic state so the UI shows the real readback, but
        do NOT kill the SignalR connection (it's healthy — the SCU is just
        asleep).
        """
        # Main switch ON needs extra time — SCU may be waking from standby
        if expected_on and self.entity_description.is_main_switch:
            delay = 60
        elif not expected_on:
            delay = self.entity_description.holdoff_off
        else:
            delay = 15
        await asyncio.sleep(delay)
        if self.coordinator.data is None:
            return
        value = _resolve_path(
            self.coordinator.data, self.entity_description.value_path
        )
        if value is None:
            return
        if isinstance(value, str) and isinstance(self.entity_description.on_value, str):
            actual_on = value.upper() == self.entity_description.on_value.upper()
        else:
            actual_on = value == self.entity_description.on_value
        if actual_on != expected_on:
            # Check if SCU is offline — if so, the command wasn't delivered
            # yet but SignalR itself is fine.
            client = self.coordinator.signalr_client
            scu_online = False
            if client:
                scu_online = client._sensor_data.get("scu_connected") is True
            if not scu_online:
                _LOGGER.warning(
                    "Switch %s: command (%s) not confirmed after %ds "
                    "— SCU is offline, command queued until SCU wakes up",
                    self.entity_description.key, expected_on, delay,
                )
                # Clear optimistic state so UI shows real readback
                self._optimistic_on = None
                self.async_write_ha_state()
            else:
                _LOGGER.warning(
                    "Switch %s: SCU readback (%s) doesn't match commanded (%s) "
                    "after %ds — SignalR send channel likely dead, forcing reconnect "
                    "and retrying command",
                    self.entity_description.key, value, expected_on, delay,
                )
                if client:
                    client._connected = False
                    _LOGGER.info("Marked SignalR as disconnected — will reconnect on next poll")
                # Retry the command after reconnect settles
                self._retry_task = asyncio.ensure_future(
                    self._retry_after_reconnect(expected_on)
                )

    async def _retry_after_reconnect(self, expected_on: bool) -> None:
        """Wait for SignalR to reconnect, then re-send the failed command.

        After _verify_send detects a dead send channel and marks SignalR as
        disconnected, the coordinator's next poll cycle will reconnect.  We
        wait up to 90s for the connection to come back, then re-issue the
        original command exactly once.  No further verification loop — if the
        retry also fails, the user will see the mismatch in the UI.
        """
        # Wait for reconnect (coordinator polls every ~60s)
        for _ in range(18):  # 18 × 5s = 90s
            await asyncio.sleep(5)
            client = self.coordinator.signalr_client
            if client and client._connected:
                break
        else:
            _LOGGER.warning(
                "Switch %s: reconnect did not complete within 90s — "
                "skipping command retry",
                self.entity_description.key,
            )
            self._optimistic_on = None
            self.async_write_ha_state()
            return

        _LOGGER.info(
            "Switch %s: SignalR reconnected — retrying %s command",
            self.entity_description.key,
            "ON" if expected_on else "OFF",
        )
        if expected_on:
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    @property
    def available(self) -> bool:
        """Switches with requires_12v need the 12V main switch to be on."""
        if self.entity_description.requires_12v:
            if self.coordinator.data is None:
                return False
            main = _resolve_path(self.coordinator.data, "signalr_sensors.main_switch")
            if main is not None and str(main) != "On":
                return False
        return super().available

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        desc = self.entity_description
        _LOGGER.info(
            "Switch %s → ON (bus=%d, sid=%d, type=%s)",
            desc.key, desc.bus_id, desc.sensor_id, desc.write_type,
        )
        if desc.write_type == "str":
            on_str = desc.write_on if desc.write_on else str(desc.on_value)
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, str_value=on_str,
            )
        elif desc.write_type == "uint":
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, uint_value=1,
            )
        else:
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, bool_value=True,
            )
        self._optimistic_on = True
        self._optimistic_set_at = time.monotonic()
        # NOTE: Do NOT write back into client._sensor_data here.  Doing so
        # poisons _verify_send (which reads the same path back) and the
        # is_standby check in needs_reconnect (main_switch=='Off' bypasses
        # the 3-min stale-data reconnect).  _optimistic_on already drives
        # is_on for the UI; the SCU will push the real value within ~3s.
        self.async_write_ha_state()
        if self._verify_task and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = asyncio.ensure_future(self._verify_send(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        desc = self.entity_description
        _LOGGER.info(
            "Switch %s → OFF (bus=%d, sid=%d, type=%s)",
            desc.key, desc.bus_id, desc.sensor_id, desc.write_type,
        )
        if desc.write_type == "str":
            off_str = desc.write_off if desc.write_off else "Off"
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, str_value=off_str,
            )
        elif desc.write_type == "uint":
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, uint_value=0,
            )
        else:
            await self.coordinator.async_send_light_command(
                desc.bus_id, desc.sensor_id, bool_value=False,
            )
        self._optimistic_on = False
        self._optimistic_set_at = time.monotonic()
        # NOTE: Do NOT write back into client._sensor_data here.  See the
        # matching comment in async_turn_on — poisoning _sensor_data breaks
        # _verify_send and the standby reconnect heuristic.
        self.async_write_ha_state()
        if self._verify_task and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = asyncio.ensure_future(self._verify_send(False))

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when SCU confirms the commanded value."""
        if self._optimistic_on is not None and self.coordinator.data:
            value = _resolve_path(
                self.coordinator.data, self.entity_description.value_path
            )
            if value is not None:
                if isinstance(value, str) and isinstance(self.entity_description.on_value, str):
                    actual = value.upper() == self.entity_description.on_value.upper()
                else:
                    actual = value == self.entity_description.on_value

                # Hold optimistic OFF through bounce-back window
                if (
                    self._optimistic_on is False
                    and actual is True
                    and self.entity_description.holdoff_off > 15
                ):
                    elapsed = time.monotonic() - self._optimistic_set_at
                    if elapsed < self.entity_description.holdoff_off:
                        _LOGGER.debug(
                            "Switch %s: ignoring stale readback "
                            "%.1fs after OFF command (holdoff %ds)",
                            self.entity_description.key,
                            elapsed,
                            self.entity_description.holdoff_off,
                        )
                        super()._handle_coordinator_update()
                        return

                if actual == self._optimistic_on:
                    self._optimistic_on = None
        super()._handle_coordinator_update()
