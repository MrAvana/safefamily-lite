"""Config and options flow for SafeFamily Lite (local backend only)."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_LOCAL_NAME,
    CONF_LOCAL_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_LOCAL_SCAN_INTERVAL,
    DOMAIN,
)
from .local import LocalApi, LocalApiError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_LOCAL_URL, default="http://homeassistant.local:8080"
        ): str,
        vol.Optional(CONF_LOCAL_NAME, default=""): str,
    }
)


class SafeFamilyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_LOCAL_URL].strip().rstrip("/")
            name = (user_input.get(CONF_LOCAL_NAME) or "").strip()

            await self.async_set_unique_id(url.lower())
            self._abort_if_unique_id_configured()

            api = LocalApi(url)
            async with aiohttp.ClientSession() as session:
                if not await api.health(session):
                    errors["base"] = "cannot_connect"
                else:
                    try:
                        state = await api.state(session)
                    except LocalApiError:
                        state = {}
                    if not state:
                        # The backend is up but nothing has logged in yet. The
                        # entry is still worth creating: Home Assistant retries
                        # setup, so the watch appears by itself once it does.
                        _LOGGER.warning(
                            "Local backend %s answered but no watch has reported "
                            "yet; setup will keep retrying until one does",
                            url,
                        )
                    return self.async_create_entry(
                        title=name or url,
                        data={CONF_LOCAL_URL: url, CONF_LOCAL_NAME: name},
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SafeFamilyOptionsFlow()


class SafeFamilyOptionsFlow(config_entries.OptionsFlow):
    """Options for the local backend.

    Deliberately no ``__init__``: Home Assistant injects ``config_entry`` as a
    read-only property on OptionsFlow, and assigning to it raises
    "property 'config_entry' has no setter", which kills the whole flow.
    """

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        local_url = entry.options.get(CONF_LOCAL_URL) or entry.data.get(
            CONF_LOCAL_URL
        )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_LOCAL_URL,
                    default=local_url or "http://homeassistant.local:8080",
                ): str,
                vol.Optional(
                    CONF_LOCAL_NAME,
                    default=entry.options.get(CONF_LOCAL_NAME)
                    or entry.data.get(CONF_LOCAL_NAME, ""),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_LOCAL_SCAN_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=15, max=3600)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
