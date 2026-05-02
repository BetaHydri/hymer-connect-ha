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

    async def _verify_send(self, expected_on: bool) -> None:
        """Verify the SCU acknowledged the command after a delay."""
        delay = self.entity_description.holdoff_off if not expected_on else 15
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
            _LOGGER.warning(
                "Switch %s: SCU readback (%s) doesn't match commanded (%s) "
                "after %ds — SignalR send channel likely dead, forcing reconnect",
                self.entity_description.key, value, expected_on, delay,
            )
            client = self.coordinator.signalr_client
            if client:
                client._connected = False
                _LOGGER.info("Marked SignalR as disconnected — will reconnect on next poll")

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
        if desc.is_main_switch:
            client = self.coordinator.signalr_client
            if client:
                client._sensor_data["main_switch"] = desc.write_on or "On"
        self.async_write_ha_state()
        if self._verify_task and not self._verify_task.done():
            self._verify_task.cancel()
        self._verify_task = asyncio.ensure_future(self._verify_send(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        desc = self.entity_description
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
        if desc.is_main_switch:
            client = self.coordinator.signalr_client
            if client:
                client._sensor_data["main_switch"] = desc.write_off or "Off"
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
