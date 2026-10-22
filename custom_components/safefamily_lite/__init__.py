"""SafeFamily Lite integration entry point (local backend only)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
try:  # `ServiceValidationError` arrived in 2023.7; keep older cores working.
    from homeassistant.exceptions import ServiceValidationError
except ImportError:  # pragma: no cover - depends on the core version
    ServiceValidationError = HomeAssistantError  # type: ignore[misc,assignment]
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import CONF_LOCAL_URL, DOMAIN
from .contacts import resolve_icon
from .local import ALARMS_MAX, LocalApiError, LocalCoordinator

_LOGGER = logging.getLogger(__name__)

# Set to True once we've registered the static paths (global, not per entry).
_STATIC_PATHS_REGISTERED = False

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "device_tracker",
    "button",
    "image",
]

SERVICE_SET_LOCAL_CONTACTS = "set_local_contacts"
SERVICE_SET_LOCAL_ALARMS = "set_local_alarms"
SERVICE_ADD_LOCAL_CONTACT = "add_local_contact"
SERVICE_REMOVE_LOCAL_CONTACT = "remove_local_contact"
SERVICE_SEND_LOCAL_VOICE = "send_local_voice"
SERVICE_SEND_TTS_VOICE = "send_tts_voice"
SERVICE_SEND_LOCAL_TEXT = "send_local_text"
SERVICE_SEND_LOCAL_EMOJI = "send_local_emoji"

ATTR_VOICE_URL = "url"
ATTR_VOICE_NOTIFY = "notify"
ATTR_VOICE_BURST = "burst"
ATTR_TEXT = "text"
ATTR_STICKER = "sticker"
ATTR_TTS_MESSAGE = "message"
ATTR_TTS_ENGINE = "engine"
ATTR_TTS_LANGUAGE = "language"
ATTR_TTS_OPTIONS = "options"

ATTR_WATCH = "watch"
ATTR_IMEI = "imei"

ATTR_CONTACT_NAME = "name"
ATTR_CONTACT_NUMBER = "number"
ATTR_CONTACT_ICON = "icon"
ATTR_CONTACT_SOS = "sos"
ATTR_CONTACTS_JSON = "contacts_json"
ATTR_ALARMS_JSON = "alarms_json"

WWW_URL_PATH = "/safefamily_lite/www"
WWW_DIR = "custom_components/safefamily_lite/www"

# Local mode addresses a watch by IMEI. `contacts_json` is a JSON array of
# {name, number, icon, is_sos}.
SET_LOCAL_CONTACTS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        vol.Required(ATTR_CONTACTS_JSON): cv.string,
    }
)

# `IWBP85` is also a full replace with no read-back, so the same JSON-list
# shape is used for alarms. The backend validates the individual alarms; the
# service checks the list shape and the firmware's three-slot limit.
SET_LOCAL_ALARMS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        vol.Required(ATTR_ALARMS_JSON): cv.string,
    }
)

ADD_LOCAL_CONTACT_SCHEMA = vol.Schema(
    {
        # The GUI sends the device-registry id from its watch picker. Scripts
        # may keep sending `imei`, so both forms stay accepted; the handler
        # requires exactly one of them.
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        vol.Required(ATTR_CONTACT_NAME): cv.string,
        vol.Required(ATTR_CONTACT_NUMBER): cv.string,
        # 0 Father, 1 Mother, 2 Sister, 3 Grandpa, 4 Granny, 5 Brother,
        # 6+ Other. Accepts the friendly name too, via `resolve_icon`.
        vol.Optional(ATTR_CONTACT_ICON, default=6): vol.Any(int, cv.string),
        vol.Optional(ATTR_CONTACT_SOS, default=False): cv.boolean,
    }
)

REMOVE_LOCAL_CONTACT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        # Number only: it is the key the watch compares against, and the name
        # is not unique.
        vol.Required(ATTR_CONTACT_NUMBER): cv.string,
    }
)

SEND_LOCAL_VOICE_SCHEMA = vol.Schema(
    {
        # The GUI sends the device-registry id from its watch picker. Scripts
        # may keep sending `imei`, so both forms stay accepted; the handler
        # requires exactly one of them.
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        # A URL the Home Assistant process can fetch. `notify` asks for the
        # immediate IWBP27 alert; the default is a silent queue.
        vol.Required(ATTR_VOICE_URL): cv.string,
        vol.Optional(ATTR_VOICE_NOTIFY, default=False): cv.boolean,
    }
)

SEND_LOCAL_TEXT_SCHEMA = vol.Schema(
    {
        # The GUI sends the device-registry id from its watch picker. Scripts
        # may keep sending `imei`, so both forms stay accepted.
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        # A transient notification on the watch screen, not an SMS.
        vol.Required(ATTR_TEXT): cv.string,
    }
)

# The four built-in K01 stickers, in firmware order (`k01em0`..`k01em3`).
# The service exposes the colours because that is how the images differ.
EMOJI_OPTIONS = {
    "Teal": 0,
    "Orange": 1,
    "Green": 2,
    "Red": 3,
}

SEND_LOCAL_EMOJI_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        # One of the watch's four predefined stickers, not free text.
        vol.Required(ATTR_STICKER): vol.In(EMOJI_OPTIONS),
    }
)

SEND_TTS_VOICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_WATCH): cv.string,
        vol.Optional(ATTR_IMEI): cv.string,
        vol.Required(ATTR_TTS_MESSAGE): cv.string,
        # Empty means "use tts.piper", the local engine, unless the caller
        # explicitly names another engine.
        vol.Optional(ATTR_TTS_ENGINE): cv.string,
        vol.Optional(ATTR_TTS_LANGUAGE): cv.string,
        vol.Optional(ATTR_TTS_OPTIONS, default={}): dict,
        vol.Optional(ATTR_VOICE_NOTIFY, default=False): cv.boolean,
        vol.Optional(ATTR_VOICE_BURST, default=True): cv.boolean,
    }
)


def _imei_for_watch(hass: HomeAssistant, device_id: str,
                    coordinator: LocalCoordinator) -> str:
    """Resolve a device-registry id from the GUI picker to its watch IMEI."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError("the selected watch device was not found")
    for domain, identifier in device.identifiers:
        if domain == DOMAIN and identifier in (coordinator.data or {}):
            return identifier
    raise ServiceValidationError(
        "the selected device is not a watch on this local backend"
    )


def _imei_from_call(call: ServiceCall, hass: HomeAssistant,
                    coordinator: LocalCoordinator) -> str:
    """Return the IMEI from the watch picker, or the legacy `imei` field."""
    watch = call.data.get(ATTR_WATCH)
    imei = (
        _imei_for_watch(hass, watch, coordinator)
        if watch else call.data.get(ATTR_IMEI)
    )
    if not imei:
        raise ServiceValidationError("select a watch or provide an imei")
    return imei


async def _async_register_static_paths(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card from inside the integration folder.

    Never raises: a missing directory or an old core must not prevent the
    integration from setting up.
    """
    global _STATIC_PATHS_REGISTERED
    if _STATIC_PATHS_REGISTERED:
        return

    full = Path(hass.config.path(WWW_DIR))
    if not full.is_dir():
        _LOGGER.warning("Asset directory missing: %s", full)
        return

    try:
        try:
            from homeassistant.components.http import StaticPathConfig  # noqa: WPS433
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        url_path=WWW_URL_PATH, path=str(full),
                        cache_headers=False,
                    )
                ]
            )
        except ImportError:
            hass.http.register_static_path(
                WWW_URL_PATH, str(full), cache_headers=False
            )
        _STATIC_PATHS_REGISTERED = True
        _LOGGER.debug("Registered static path: %s", WWW_URL_PATH)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not register static paths: %s", err)


async def _explain_refusal(pending) -> None:
    """Await a local-backend write, and say why it failed in the UI's words.

    `LocalApiError` is how the backend refuses -- a list that would drop a
    protected number, a number that is not in the phonebook. A refusal becomes
    `ServiceValidationError`: the request was understood and rejected, so the
    REST API answers 400 and the message is the backend's. Anything else
    (unreachable, timeout, 5xx) stays `HomeAssistantError`.
    """
    try:
        await pending
    except LocalApiError as err:
        error = ServiceValidationError if err.refusal else HomeAssistantError
        raise error(str(err)) from err


async def _async_setup_local(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up against the private local backend."""
    coordinator = LocalCoordinator(hass, entry)
    # Raises ConfigEntryNotReady while nothing has reported yet, which makes
    # Home Assistant retry until the watch shows up.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    if not hass.services.has_service(DOMAIN, SERVICE_SET_LOCAL_CONTACTS):

        async def _handle_set_local_contacts(call: ServiceCall) -> None:
            imei = _imei_from_call(call, hass, coordinator)
            try:
                contacts = json.loads(call.data[ATTR_CONTACTS_JSON])
            except ValueError as err:
                raise ServiceValidationError(
                    f"contacts_json is not valid JSON: {err}"
                ) from err
            await _explain_refusal(
                coordinator.async_set_contacts(
                    imei, contacts, replace_unknown=True
                )
            )

        hass.services.async_register(
            DOMAIN, SERVICE_SET_LOCAL_CONTACTS, _handle_set_local_contacts,
            schema=SET_LOCAL_CONTACTS_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_LOCAL_ALARMS):

        async def _handle_set_local_alarms(call: ServiceCall) -> None:
            imei = _imei_from_call(call, hass, coordinator)
            try:
                alarms = json.loads(call.data[ATTR_ALARMS_JSON])
            except ValueError as err:
                raise ServiceValidationError(
                    f"alarms_json is not valid JSON: {err}"
                ) from err
            if not isinstance(alarms, list):
                raise ServiceValidationError("alarms_json must be a JSON array")
            if len(alarms) > ALARMS_MAX:
                raise ServiceValidationError(
                    f"at most {ALARMS_MAX} alarms"
                )
            await _explain_refusal(
                coordinator.async_set_alarms(imei, alarms)
            )

        hass.services.async_register(
            DOMAIN, SERVICE_SET_LOCAL_ALARMS, _handle_set_local_alarms,
            schema=SET_LOCAL_ALARMS_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_LOCAL_CONTACT):

        async def _handle_add_local_contact(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_add_contact(
                _imei_from_call(call, hass, coordinator),
                call.data[ATTR_CONTACT_NAME],
                call.data[ATTR_CONTACT_NUMBER],
                resolve_icon(call.data.get(ATTR_CONTACT_ICON), 6),
                call.data.get(ATTR_CONTACT_SOS, False),
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_ADD_LOCAL_CONTACT, _handle_add_local_contact,
            schema=ADD_LOCAL_CONTACT_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_LOCAL_CONTACT):

        async def _handle_remove_local_contact(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_remove_contact(
                _imei_from_call(call, hass, coordinator),
                call.data[ATTR_CONTACT_NUMBER],
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_REMOVE_LOCAL_CONTACT, _handle_remove_local_contact,
            schema=REMOVE_LOCAL_CONTACT_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_LOCAL_VOICE):

        async def _handle_send_local_voice(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_send_voice(
                _imei_from_call(call, hass, coordinator),
                call.data[ATTR_VOICE_URL],
                notify=call.data.get(ATTR_VOICE_NOTIFY, False),
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_SEND_LOCAL_VOICE, _handle_send_local_voice,
            schema=SEND_LOCAL_VOICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_LOCAL_TEXT):

        async def _handle_send_local_text(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_send_text(
                _imei_from_call(call, hass, coordinator),
                call.data[ATTR_TEXT],
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_SEND_LOCAL_TEXT, _handle_send_local_text,
            schema=SEND_LOCAL_TEXT_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_LOCAL_EMOJI):

        async def _handle_send_local_emoji(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_send_emoji(
                _imei_from_call(call, hass, coordinator),
                EMOJI_OPTIONS[call.data[ATTR_STICKER]],
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_SEND_LOCAL_EMOJI, _handle_send_local_emoji,
            schema=SEND_LOCAL_EMOJI_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TTS_VOICE):

        async def _handle_send_tts_voice(call: ServiceCall) -> None:
            await _explain_refusal(coordinator.async_send_tts(
                _imei_from_call(call, hass, coordinator),
                call.data[ATTR_TTS_MESSAGE],
                engine=call.data.get(ATTR_TTS_ENGINE),
                language=call.data.get(ATTR_TTS_LANGUAGE),
                options=call.data.get(ATTR_TTS_OPTIONS) or {},
                notify=call.data.get(ATTR_VOICE_NOTIFY, False),
                burst=call.data.get(ATTR_VOICE_BURST, True),
            ))

        hass.services.async_register(
            DOMAIN, SERVICE_SEND_TTS_VOICE, _handle_send_tts_voice,
            schema=SEND_TTS_VOICE_SCHEMA,
        )

    _LOGGER.info(
        "SafeFamily Lite using local backend %s (%d watch(es))",
        coordinator.url,
        len(coordinator.data or {}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        await _async_register_static_paths(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Static path setup skipped: %s", err)

    # Local entries always carry the URL in `data`; `options` may override it
    # later. An entry without it is an old cloud entry, and must be removed
    # rather than silently reused with the old credentials still stored.
    if not entry.data.get(CONF_LOCAL_URL):
        raise ConfigEntryError(
            "This SafeFamily Lite entry uses the removed Elari vendor cloud. "
            "Remove it and add the integration again with your local backend "
            "URL."
        )

    return await _async_setup_local(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            for svc in (
                SERVICE_SET_LOCAL_CONTACTS,
                SERVICE_SET_LOCAL_ALARMS,
                SERVICE_ADD_LOCAL_CONTACT,
                SERVICE_REMOVE_LOCAL_CONTACT,
                SERVICE_SEND_LOCAL_VOICE,
                SERVICE_SEND_LOCAL_TEXT,
                SERVICE_SEND_LOCAL_EMOJI,
                SERVICE_SEND_TTS_VOICE,
            ):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
