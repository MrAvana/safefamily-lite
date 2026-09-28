"""Config and options flow for SafeFamily Lite."""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .api import SafeFamilyApi, SafeFamilyAuthError
from .const import (
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REGIONS,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default="EU"): vol.In(list(REGIONS.keys())),
    }
)


class SafeFamilyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            try:
                api = SafeFamilyApi(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_REGION],
                )
                async with aiohttp.ClientSession() as session:
                    await api.login(session)
            except SafeFamilyAuthError:
                errors["base"] = "auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SafeFamilyOptionsFlow(config_entry)


class SafeFamilyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=30, max=3600)
                    )
                }
            ),
        )