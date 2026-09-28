"""DataUpdateCoordinator for SafeFamily Lite."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import SafeFamilyApi, SafeFamilyAuthError, SafeFamilyCommandTimeout
from .const import (
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PROFILE_REFRESH_CMD = "0039"
CAMERA_SHOT_CMD = "0031"
HISTORY_TODAY_MAX_POINTS = 2000
MESSAGE_PAGE_SIZE = 20
PHOTO_DAY_PAGE_SIZE = 30


class SafeFamilyCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    """Polls the SafeFamily API and caches devices by Id."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.api = SafeFamilyApi(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data[CONF_REGION],
        )
        self.calls_last: dict[int, dict | None] = {}
        self.calls_history: dict[int, list[dict]] = {}
        self.commands: dict[int, dict[str, dict]] = {}
        self.care_time_interval: dict[int, str] = {}
        self.profiles: dict[int, dict] = {}
        self.geofences: dict[int, list[dict]] = {}
        self.steps_today: dict[int, dict] = {}
        self.friends: dict[int, list[dict]] = {}
        self.shares: dict[int, list[dict]] = {}
        self.alerts: dict[int, list[dict]] = {}
        self.messages: dict[int, list[dict]] = {}
        self.voice_messages: dict[int, list[dict]] = {}
        self.photos: dict[int, list[dict]] = {}
        self.location_history_today: dict[int, list[dict]] = {}
        self._fence_entities: set = set()

        scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan),
        )

    async def _async_update_data(self) -> dict[int, dict]:
        async with aiohttp.ClientSession() as session:
            try:
                items = await self.api.person_device_list(session)
            except SafeFamilyAuthError as first_err:
                try:
                    await self.api.login(session)
                    items = await self.api.person_device_list(session)
                except Exception as err:  # noqa: BLE001
                    raise UpdateFailed(f"auth retry failed: {err}") from first_err
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"API error: {err}") from err

            self.calls_last = {}
            self.calls_history = {}
            self.commands = {}
            self.profiles = {}
            self.geofences = {}
            self.steps_today = {}
            self.friends = {}
            self.shares = {}
            self.alerts = {}
            self.messages = {}
            self.voice_messages = {}
            self.photos = {}
            self.location_history_today = {}
            # NOTE: self.care_time_interval is intentionally NOT reset —
            # it accumulates the last non-off interval across polls.

            today = dt_util.now().strftime("%Y-%m-%d")
            tomorrow = (dt_util.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            for item in items:
                device_id = item.get("Id")
                man_id = item.get("SerialNumber")
                if not device_id:
                    continue

                if man_id:
                    try:
                        self.calls_last[device_id] = await self.api.ecp_calls_last(
                            session, man_id
                        )
                        self.calls_history[device_id] = (
                            await self.api.ecp_calls_history(session, man_id)
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "ECP calls fetch failed for device %s: %s",
                            device_id, err,
                        )
                        self.calls_last[device_id] = None
                        self.calls_history[device_id] = []

                try:
                    cmds = await self.api.command_list(session, device_id)
                    self.commands[device_id] = {
                        c["Code"]: c for c in cmds if c.get("Code")
                    }
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "CommandList fetch failed for device %s: %s",
                        device_id, err,
                    )
                    self.commands[device_id] = {}

                cmds_for_device = self.commands.get(device_id) or {}
                interval_val = str(
                    cmds_for_device.get("0003", {}).get("CmdValue") or ""
                ).strip()
                if interval_val and interval_val != "1440":
                    self.care_time_interval[device_id] = interval_val

                try:
                    self.profiles[device_id] = await self.api.get_person_profile(
                        session, device_id
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Profile fetch failed for device %s: %s", device_id, err
                    )
                    self.profiles[device_id] = {}

                try:
                    self.geofences[device_id] = await self.api.geofence_list(
                        session, device_id
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Geofence list failed for device %s: %s", device_id, err
                    )
                    self.geofences[device_id] = []

                try:
                    self.location_history_today[device_id] = (
                        await self.api.location_history(
                            session,
                            device_id,
                            start_time=f"{today} 00:00:00",
                            end_time=f"{tomorrow} 00:00:00",
                            select_count=HISTORY_TODAY_MAX_POINTS,
                        )
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Location history fetch failed for device %s: %s",
                        device_id, err,
                    )
                    self.location_history_today[device_id] = []

                if man_id:
                    try:
                        self.steps_today[device_id] = await self.api.steps_for_day(
                            session, man_id, today
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Steps fetch failed for device %s: %s", device_id, err
                        )
                        self.steps_today[device_id] = {}

                    try:
                        self.friends[device_id] = await self.api.friends_list(
                            session, man_id
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Friends fetch failed for device %s: %s", device_id, err
                        )
                        self.friends[device_id] = []

                    try:
                        self.messages[device_id] = await self.api.messages(
                            session,
                            imei=man_id,
                            chat_type=2,
                            file_type=0,
                            page_no=1,
                            page_count=MESSAGE_PAGE_SIZE,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Messages fetch failed for device %s: %s",
                            device_id, err,
                        )
                        self.messages[device_id] = []

                    try:
                        self.voice_messages[device_id] = await self.api.messages(
                            session,
                            imei=man_id,
                            chat_type=1,
                            file_type=8,
                            page_no=1,
                            page_count=MESSAGE_PAGE_SIZE,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Voice messages fetch failed for device %s: %s",
                            device_id, err,
                        )
                        self.voice_messages[device_id] = []

                    try:
                        self.photos[device_id] = await self.api.get_pictures(
                            session,
                            imei=man_id,
                            day_per_page=PHOTO_DAY_PAGE_SIZE,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Photos fetch failed for device %s: %s",
                            device_id, err,
                        )
                        self.photos[device_id] = []

                try:
                    self.shares[device_id] = await self.api.share_list(
                        session, device_id
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Shares fetch failed for device %s: %s", device_id, err
                    )
                    self.shares[device_id] = []

                try:
                    self.alerts[device_id] = await self.api.exception_messages(
                        session, page_no=1, page_count=50
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Alerts fetch failed for device %s: %s", device_id, err
                    )
                    self.alerts[device_id] = []

        return {item["Id"]: item for item in items}

    async def async_send_command(
        self, device_id: int, cmd_code: str, params: str = ""
    ) -> None:
        """Send a command. A watch-side timeout is logged but not raised."""
        dev = (self.data or {}).get(device_id)
        if not dev:
            raise UpdateFailed(f"Unknown device_id {device_id}")
        model = dev.get("Model", 0)
        async with aiohttp.ClientSession() as session:
            try:
                await self.api.send_command(
                    session, device_id, str(model), cmd_code, params
                )
            except SafeFamilyCommandTimeout as err:
                _LOGGER.warning(
                    "Command %s to device %s queued but not acked: %s",
                    cmd_code, device_id, err,
                )

    async def async_save_profile(self, device_id: int, updates: dict) -> None:
        current = dict(self.profiles.get(device_id) or {})
        async with aiohttp.ClientSession() as session:
            if not current:
                current = await self.api.get_person_profile(session, device_id)

            merged = {
                **current,
                **updates,
                "DeviceID": device_id,
                "UserId": self.api.user_id,
                "UpdateTime": "",
            }
            for key in ("Height", "Weight"):
                if key in merged:
                    merged[key] = str(merged[key])

            await self.api.save_person_profile(session, device_id, merged)

            dev = (self.data or {}).get(device_id) or {}
            try:
                await self.api.send_command(
                    session, device_id, str(dev.get("Model", 0)),
                    PROFILE_REFRESH_CMD,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Profile refresh command failed: %s", err)

        await self.async_request_refresh()

    async def async_geofence_create(
        self,
        device_id: int,
        name: str,
        latitude: float,
        longitude: float,
        radius: int,
        address: str = "",
    ) -> None:
        async with aiohttp.ClientSession() as session:
            await self.api.geofence_create(
                session, device_id,
                name=name, latitude=latitude, longitude=longitude,
                radius=radius, address=address,
            )
        await self.async_request_refresh()

    async def async_geofence_delete(self, device_id: int, fence_id: int) -> None:
        fences = self.geofences.get(device_id) or []
        fence = next((f for f in fences if f.get("FenceId") == fence_id), None)
        if not fence:
            raise UpdateFailed(f"Unknown fence_id {fence_id}")
        async with aiohttp.ClientSession() as session:
            await self.api.geofence_delete(session, device_id, fence)
        await self.async_request_refresh()

    async def async_geofence_edit(
        self, device_id: int, fence_id: int, updates: dict
    ) -> None:
        fences = self.geofences.get(device_id) or []
        fence = next((f for f in fences if f.get("FenceId") == fence_id), None)
        if not fence:
            raise UpdateFailed(f"Unknown fence_id {fence_id}")
        merged = {**fence, **updates}
        async with aiohttp.ClientSession() as session:
            await self.api.geofence_edit(session, device_id, merged)
        await self.async_request_refresh()

    async def async_get_location_history(
        self,
        device_id: int,
        start_time: str,
        end_time: str,
        select_count: int = 500,
    ) -> list[dict]:
        async with aiohttp.ClientSession() as session:
            return await self.api.location_history(
                session, device_id,
                start_time=start_time, end_time=end_time,
                select_count=select_count,
            )

    async def async_send_text(self, device_id: int, text: str) -> None:
        dev = (self.data or {}).get(device_id)
        if not dev:
            raise UpdateFailed(f"Unknown device_id {device_id}")
        imei = dev.get("SerialNumber")
        if not imei:
            raise UpdateFailed(f"No IMEI for device_id {device_id}")
        async with aiohttp.ClientSession() as session:
            await self.api.send_text_message(session, imei=imei, text=text)

    async def async_send_emoji(self, device_id: int, emoji: str) -> None:
        from .chat import resolve_emoji  # local import to avoid cycles

        code = resolve_emoji(emoji)
        if code is None:
            raise UpdateFailed(
                f"Unknown emoji {emoji!r}; expected one of k01em0..k01em3"
            )
        dev = (self.data or {}).get(device_id)
        if not dev:
            raise UpdateFailed(f"Unknown device_id {device_id}")
        imei = dev.get("SerialNumber")
        if not imei:
            raise UpdateFailed(f"No IMEI for device_id {device_id}")
        async with aiohttp.ClientSession() as session:
            await self.api.send_text_message(session, imei=imei, text=code)

    def camera_target_number(self, device_id: int) -> str:
        cmds = self.commands.get(device_id) or {}
        item = cmds.get(CAMERA_SHOT_CMD, {})
        val = str(item.get("CmdValue") or "").strip()
        if val:
            return val
        dev = (self.data or {}).get(device_id) or {}
        for key in ("MainPhone", "Sim"):
            v = dev.get(key)
            if v:
                return str(v)
        return ""

    async def async_take_photo(self, device_id: int) -> None:
        number = self.camera_target_number(device_id)
        if not number:
            raise UpdateFailed(
                "No phone number available for the camera command "
                "(checked 0031, MainPhone, Sim)"
            )
        await self.async_send_command(device_id, CAMERA_SHOT_CMD, number)
        await self.async_request_refresh()

    async def async_get_photos(
        self,
        device_id: int,
        min_date: str | None = None,
        day_per_page: int = 30,
    ) -> list[dict]:
        dev = (self.data or {}).get(device_id)
        if not dev:
            raise UpdateFailed(f"Unknown device_id {device_id}")
        imei = dev.get("SerialNumber")
        if not imei:
            raise UpdateFailed(f"No IMEI for device_id {device_id}")
        async with aiohttp.ClientSession() as session:
            return await self.api.get_pictures(
                session,
                imei=imei,
                min_date=min_date,
                day_per_page=day_per_page,
            )

    # ------------------------------------------------------------------
    # device pairing helpers
    # ------------------------------------------------------------------

    async def async_check_device(self, serial_number: str) -> dict:
        async with aiohttp.ClientSession() as session:
            return await self.api.check_device(session, serial_number)

    async def async_add_device(
        self,
        serial_number: str,
        relation_name: str = "",
        relation_phone: str = "",
        info: str = "",
    ) -> dict:
        check = await self.async_check_device(serial_number)

        state = check.get("State")
        if state not in (0, None):
            raise UpdateFailed(
                f"check device failed: {check.get('Message', check)}"
            )

        device_id = check.get("DeviceId")
        try:
            device_id = int(device_id) if device_id is not None else None
        except (TypeError, ValueError):
            device_id = None

        if device_id is None:
            raise UpdateFailed(
                "CheckDevice did not return a DeviceId — the watch may be "
                "offline, already bound to another account, or the IMEI is "
                f"wrong. Server said: {check.get('Message')!r}"
            )

        if check.get("IsActivation") is True:
            raise UpdateFailed(
                "This watch is already activated on another account"
            )

        if check.get("NeedPhone") and not relation_phone:
            raise UpdateFailed(
                "Server requires a phone number to bind this watch "
                "(NeedPhone=true). Pass relation_phone in the service call."
            )

        async with aiohttp.ClientSession() as session:
            add = await self.api.add_device(
                session,
                device_id=device_id,
                relation_name=relation_name,
                relation_phone=relation_phone,
                info=info,
            )

        await self.async_request_refresh()

        return {
            "device_id": device_id,
            "check_response": check,
            "add_response": add,
        }

    async def async_remove_device(self, device_id: int) -> dict:
        async with aiohttp.ClientSession() as session:
            result = await self.api.unbound_device(session, device_id)
        await self.async_request_refresh()
        return result

    # ------------------------------------------------------------------
    # contacts helpers
    # ------------------------------------------------------------------

    def _current_contacts(self, device_id: int) -> list[dict]:
        from .contacts import normalize_contacts, parse_contacts_json

        item = (self.commands.get(device_id) or {}).get("9016", {})
        return normalize_contacts(
            parse_contacts_json(str(item.get("CmdValue") or ""))
        )

    async def _send_contacts(self, device_id: int, contacts: list[dict]) -> None:
        from .contacts import CONTACTS_CODE, contacts_to_wire_json

        params = contacts_to_wire_json(contacts) if contacts else "[]"
        await self.async_send_command(device_id, CONTACTS_CODE, params)
        await self.async_request_refresh()

    async def async_set_contacts(self, device_id: int, raw_json: str) -> None:
        """Send a full raw contacts JSON list. Advanced use."""
        from .contacts import CONTACTS_CODE

        await self.async_send_command(device_id, CONTACTS_CODE, raw_json)
        await self.async_request_refresh()

    async def async_add_contact(
        self,
        device_id: int,
        name: str,
        number: str,
        icon: int | str = 6,
        sos: bool = False,
        short_number: str = "",
    ) -> None:
        from .contacts import find_contact, normalize_contact, resolve_icon

        if not name or not number:
            raise UpdateFailed("Both 'name' and 'number' are required")

        contacts = self._current_contacts(device_id)

        existing = find_contact(contacts, name=name)
        if existing is None:
            existing = find_contact(contacts, number=number)

        new_entry = normalize_contact(
            {
                "name": name,
                "number": number,
                "icon": resolve_icon(icon),
                "sosFlag": 1 if sos else 0,
                "shortNumber": short_number,
                "relation": "",
            }
        )

        if existing is not None:
            contacts[existing] = new_entry
        else:
            contacts.append(new_entry)

        await self._send_contacts(device_id, contacts)

    async def async_remove_contact(
        self,
        device_id: int,
        name: str | None = None,
        number: str | None = None,
    ) -> None:
        from .contacts import find_contact

        if not name and not number:
            raise UpdateFailed("Provide either 'name' or 'number' to remove")

        contacts = self._current_contacts(device_id)
        idx = find_contact(contacts, name=name, number=number)
        if idx is None:
            raise UpdateFailed(
                f"No contact matches name={name!r} number={number!r}"
            )

        contacts.pop(idx)
        await self._send_contacts(device_id, contacts)