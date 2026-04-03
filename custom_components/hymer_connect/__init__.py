"""HYMER Connect integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HymerConnectApi, HymerConnectApiError, HymerConnectAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BRAND,
    CONF_REFRESH_TOKEN,
    CONF_SCU_URN,
    CONF_VEHICLE_URN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HymerConnectCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORM_LIST = [Platform(p) for p in PLATFORMS]

type HymerConnectConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: HymerConnectConfigEntry
) -> bool:
    """Set up HYMER Connect from a config entry."""
    session = async_get_clientsession(hass)
    brand = entry.data.get(CONF_BRAND, "hymer")
    api = HymerConnectApi(session, brand=brand)

    # Always re-authenticate with stored credentials to get fresh tokens
    if CONF_USERNAME in entry.data:
        try:
            tokens = await api.authenticate(
                entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
            )
            # Update stored tokens
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_ACCESS_TOKEN: tokens["access_token"],
                    CONF_REFRESH_TOKEN: tokens["refresh_token"],
                },
            )
        except HymerConnectAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except HymerConnectApiError as err:
            raise ConfigEntryNotReady(
                f"Cannot connect to HYMER API: {err}"
            ) from err
    else:
        raise ConfigEntryAuthFailed("No credentials available")

    vehicle_urn = entry.data.get(CONF_VEHICLE_URN, "")
    scu_urn = entry.data.get(CONF_SCU_URN, "")

    coordinator = HymerConnectCoordinator(
        hass, api, session, entry,
        vehicle_urn=vehicle_urn,
        scu_urn=scu_urn,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_LIST)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HymerConnectConfigEntry
) -> bool:
    """Unload a config entry."""
    coordinator: HymerConnectCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.stop_signalr()
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORM_LIST
    ):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
