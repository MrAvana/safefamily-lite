"""Config and options flow for SafeFamily Lite.

Two very different backends can serve this integration:

* the Elari vendor cloud, which the integration was originally written for
  (username / password), and
* a private local backend that speaks the watch's own protocol and offers a
  small HTTP JSON API (a URL, no credentials).
"""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .api import SafeFamilyApi, SafeFamilyAuthError
from .const import (
    CONF_LOCAL_NAME,
    CONF_LOCAL_URL,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_LOCAL_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REGIONS,
)
from .local import LocalApi, LocalApiError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default="EU"): vol.In(list(REGIONS.keys())),
    }
)

STEP_LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOCAL_URL, default="http://homeassistant.local:8080"): str,
        vol.Optional(CONF_LOCAL_NAME, default=""): str,
    }
)


class SafeFamilyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["cloud", "local"])

    async def async_step_cloud(self, user_input=None):
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
            step_id="cloud", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_local(self, user_input=None):
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
                        # setup, so the watche appears by itself once it does.
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
            step_id="local", data_schema=STEP_LOCAL_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SafeFamilyOptionsFlow()


class SafeFamilyOptionsFlow(config_entries.OptionsFlow):
    """Options for either backend.

    Deliberately no ``__init__``: Home Assistant injects ``config_entry`` as a
    read-only property on OptionsFlow, and assigning to it raises
    "property 'config_entry' has no setter", which kills the whole flow.
    """

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        local_url = entry.options.get(CONF_LOCAL_URL) or entry.data.get(CONF_LOCAL_URL)

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        if local_url:
            schema = vol.Schema(
                {
                    vol.Optional(CONF_LOCAL_URL, default=local_url): str,
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
        else:
            current_scan = entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            )
            current_region = entry.options.get(CONF_REGION) or entry.data.get(
                CONF_REGION, "EU"
            )
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_REGION, default=current_region
                    ): vol.In(list(REGIONS.keys())),
                    vol.Optional(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                        int, vol.Range(min=30, max=3600)
                    ),
                }
            )

        return self.async_show_form(step_id="init", data_schema=schema)
