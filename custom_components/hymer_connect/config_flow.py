"""Config flow for HYMER Connect integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import HymerConnectApi, HymerConnectApiError, HymerConnectAuthError
from .const import (
    BRANDS,
    CONF_ACCESS_TOKEN,
    CONF_BRAND,
    CONF_EHG_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TANK_CAPACITY,
    DEFAULT_TANK_CAPACITY_LITERS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BRAND, default="hymer"): vol.In(BRANDS),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_EHG_REFRESH_TOKEN, default=""): str,
    }
)


class HymerConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HYMER Connect."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> HymerConnectOptionsFlow:
        """Get the options flow for this handler."""
        return HymerConnectOptionsFlow(config_entry)

    async def _async_try_authenticate(
        self, brand: str, username: str, password: str
    ) -> dict[str, str]:
        """Try to authenticate and return tokens."""
        session = async_create_clientsession(self.hass)
        api = HymerConnectApi(session, brand=brand)
        return await api.authenticate(username, password)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                tokens = await self._async_try_authenticate(
                    user_input[CONF_BRAND],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except HymerConnectAuthError:
                errors["base"] = "invalid_auth"
            except HymerConnectApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"
            else:
                # Normalize email to lowercase for unique ID
                unique_id = user_input[CONF_USERNAME].lower()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                brand_name = BRANDS.get(
                    user_input[CONF_BRAND], user_input[CONF_BRAND]
                )
                return self.async_create_entry(
                    title=f"HYMER Connect ({brand_name})",
                    data={
                        CONF_BRAND: user_input[CONF_BRAND],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                        CONF_EHG_REFRESH_TOKEN: user_input.get(CONF_EHG_REFRESH_TOKEN, ""),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth when credentials expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                tokens = await self._async_try_authenticate(
                    reauth_entry.data[CONF_BRAND],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except HymerConnectAuthError:
                errors["base"] = "invalid_auth"
            except HymerConnectApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauthentication")
                errors["base"] = "unknown"
            else:
                unique_id = user_input[CONF_USERNAME].lower()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reauth_entry.data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class HymerConnectOptionsFlow(OptionsFlow):
    """Handle options for HYMER Connect."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_capacity = self._config_entry.options.get(
            CONF_TANK_CAPACITY, DEFAULT_TANK_CAPACITY_LITERS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TANK_CAPACITY,
                        default=current_capacity,
                    ): vol.All(vol.Coerce(int), vol.Range(min=30, max=200)),
                }
            ),
        )
