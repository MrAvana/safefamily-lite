"""SafeFamily Lite integration entry point."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .alarms import (
    ALARM_CODE,
    DAY_NAMES,
    default_alarm,
    days_to_weeks,
    parse_alarms_json,
    weeks_to_days,
)
from .classmode import (
    CLASS_MODE_CODE,
    make_class_window,
    parse_class_mode_json,
)
from .classschedule import (
    CLASS_SCHEDULE_CODE,
    DAY_NAMES as SCHEDULE_DAY_NAMES,
    add_period,
    delete_period,
    encode_day_subjects,
    normalize_day_param,
    parse_periods,
    parse_schedule,
    parse_schedule_json,
)
from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator

_LOGGER = logging.getLogger(__name__)

# Set to True once we've registered the static paths (global, not per entry).
_STATIC_PATHS_REGISTERED = False

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "device_tracker",
    "button",
    "switch",
    "number",
    "geo_location",
    "text",
    "date",
    "select",
    "time",
    "todo",
    "image",
]

SERVICE_SEND_COMMAND = "send_command"
SERVICE_SAVE_PROFILE = "save_profile"
SERVICE_GEOFENCE_CREATE = "geofence_create"
SERVICE_GEOFENCE_DELETE = "geofence_delete"
SERVICE_GEOFENCE_EDIT = "geofence_edit"
SERVICE_GEOFENCE_LIST = "list_geofences"
SERVICE_LOCATION_HISTORY = "get_location_history"
SERVICE_SEND_TEXT = "send_text"
SERVICE_SEND_EMOJI = "send_emoji"
SERVICE_SET_ALARMS = "set_alarms"
SERVICE_ADD_ALARM = "add_alarm"
SERVICE_DELETE_ALARM = "delete_alarm"
SERVICE_SET_CLASS_MODE = "set_class_mode"
SERVICE_ADD_CLASS_WINDOW = "add_class_window"
SERVICE_CLEAR_CLASS_MODE = "clear_class_mode"
SERVICE_SET_CLASS_SCHEDULE = "set_class_schedule"
SERVICE_SET_CLASS_SUBJECT = "set_class_subject"
SERVICE_CLEAR_CLASS_SCHEDULE = "clear_class_schedule"
SERVICE_ADD_CLASS_PERIOD = "add_class_period"
SERVICE_DELETE_CLASS_PERIOD = "delete_class_period"
SERVICE_CHECK_DEVICE = "check_device"
SERVICE_ADD_DEVICE = "add_device"
SERVICE_REMOVE_DEVICE = "remove_device"
SERVICE_ADD_CONTACT = "add_contact"
SERVICE_REMOVE_CONTACT = "remove_contact"
SERVICE_SET_CONTACTS = "set_contacts"

ATTR_DEVICE_ID = "device_id"
ATTR_CMD_CODE = "cmd_code"
ATTR_PARAMS = "params"

ATTR_NICKNAME = "nickname"
ATTR_BIRTHDAY = "birthday"
ATTR_GENDER = "gender"
ATTR_GRADE = "grade"
ATTR_CLASS = "class_name"
ATTR_SCHOOL = "school"
ATTR_HEIGHT = "height_cm"
ATTR_WEIGHT = "weight_kg"
ATTR_BLOOD_TYPE = "blood_type"
ATTR_ALLERGIC = "allergic"
ATTR_NOTES = "notes"
ATTR_CONDITION = "condition"
ATTR_DRUG = "drug"
ATTR_ADDRESS = "address"
ATTR_AREA = "area"
ATTR_CELL_PHONE = "cell_phone"
ATTR_CELL_PHONE_2 = "cell_phone_2"

ATTR_FENCE_ID = "fence_id"
ATTR_FENCE_NAME = "name"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_RADIUS = "radius"
ATTR_FENCE_UPDATES = "updates"
ATTR_REFRESH = "refresh"

ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_SELECT_COUNT = "select_count"
ATTR_TEXT = "text"
ATTR_EMOJI = "emoji"
ATTR_ALARMS_JSON = "alarms_json"
ATTR_ALARM_TIME = "time"
ATTR_ALARM_DAYS = "days"
ATTR_ALARM_INDEX = "index"

ATTR_CLASS_WINDOWS_JSON = "windows_json"
ATTR_CLASS_START = "start"
ATTR_CLASS_END = "end"
ATTR_CLASS_DAYS = "days"

ATTR_SCHEDULE_JSON = "schedule_json"
ATTR_SCHEDULE_DAY = "day"
ATTR_SCHEDULE_PERIOD = "period"
ATTR_SCHEDULE_SUBJECT = "subject"
ATTR_PERIOD_POSITION = "position"

ATTR_IMEI = "imei"
ATTR_RELATION_NAME = "relation_name"
ATTR_RELATION_PHONE = "relation_phone"
ATTR_DEVICE_INFO = "info"

ATTR_CONTACT_NAME = "name"
ATTR_CONTACT_NUMBER = "number"
ATTR_CONTACT_ICON = "icon"
ATTR_CONTACT_SOS = "sos"
ATTR_CONTACT_SHORT_NUMBER = "short_number"
ATTR_CONTACTS_JSON = "contacts_json"

EMOJI_URL_PATH = "/safefamily_lite/emojis"
EMOJI_DIR = "custom_components/safefamily_lite/assets/emojis"
CONTACT_ICON_URL_PATH = "/safefamily_lite/contact_icons"
CONTACT_ICON_DIR = "custom_components/safefamily_lite/assets/contact_icons"


SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CMD_CODE): cv.string,
        vol.Optional(ATTR_PARAMS, default=""): cv.string,
    }
)

SAVE_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Optional(ATTR_NICKNAME): cv.string,
        vol.Optional(ATTR_BIRTHDAY): cv.string,
        vol.Optional(ATTR_GENDER): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
        vol.Optional(ATTR_GRADE): cv.string,
        vol.Optional(ATTR_CLASS): cv.string,
        vol.Optional(ATTR_SCHOOL): cv.string,
        vol.Optional(ATTR_HEIGHT): vol.Coerce(int),
        vol.Optional(ATTR_WEIGHT): vol.Coerce(float),
        vol.Optional(ATTR_BLOOD_TYPE): cv.string,
        vol.Optional(ATTR_ALLERGIC): cv.string,
        vol.Optional(ATTR_NOTES): cv.string,
        vol.Optional(ATTR_CONDITION): cv.string,
        vol.Optional(ATTR_DRUG): cv.string,
        vol.Optional(ATTR_ADDRESS): cv.string,
        vol.Optional(ATTR_AREA): cv.string,
        vol.Optional(ATTR_CELL_PHONE): cv.string,
        vol.Optional(ATTR_CELL_PHONE_2): cv.string,
    }
)

GEOFENCE_CREATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_FENCE_NAME): cv.string,
        vol.Required(ATTR_LATITUDE): vol.Coerce(float),
        vol.Required(ATTR_LONGITUDE): vol.Coerce(float),
        vol.Required(ATTR_RADIUS): vol.All(vol.Coerce(int), vol.Range(min=50, max=5000)),
        vol.Optional(ATTR_ADDRESS, default=""): cv.string,
    }
)

GEOFENCE_DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_FENCE_ID): cv.positive_int,
    }
)

GEOFENCE_EDIT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_FENCE_ID): cv.positive_int,
        vol.Required(ATTR_FENCE_UPDATES): dict,
    }
)

GEOFENCE_LIST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): cv.positive_int,
        vol.Optional(ATTR_REFRESH, default=False): cv.boolean,
    }
)

LOCATION_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_START_TIME): cv.string,
        vol.Required(ATTR_END_TIME): cv.string,
        vol.Optional(ATTR_SELECT_COUNT, default=500): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=2147483647)
        ),
    }
)

SEND_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_TEXT): cv.string,
    }
)

SEND_EMOJI_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_EMOJI): cv.string,
    }
)

SET_ALARMS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_ALARMS_JSON): cv.string,
    }
)

ADD_ALARM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_ALARM_TIME): cv.string,
        vol.Optional(ATTR_ALARM_DAYS): vol.Any(cv.string, [cv.string]),
    }
)

DELETE_ALARM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Optional(ATTR_ALARM_INDEX): vol.Coerce(int),
        vol.Optional(ATTR_ALARM_TIME): cv.string,
    }
)

SET_CLASS_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CLASS_WINDOWS_JSON): cv.string,
    }
)

ADD_CLASS_WINDOW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CLASS_START): cv.string,
        vol.Required(ATTR_CLASS_END): cv.string,
        vol.Optional(ATTR_CLASS_DAYS): vol.Any(cv.string, [cv.string]),
    }
)

CLEAR_CLASS_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
    }
)

SET_CLASS_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_SCHEDULE_JSON): cv.string,
    }
)

SET_CLASS_SUBJECT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_SCHEDULE_DAY): vol.Any(cv.positive_int, cv.string),
        vol.Required(ATTR_SCHEDULE_PERIOD): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
        vol.Required(ATTR_SCHEDULE_SUBJECT): cv.string,
    }
)

CLEAR_CLASS_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
    }
)

ADD_CLASS_PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CLASS_START): cv.string,
        vol.Required(ATTR_CLASS_END): cv.string,
        vol.Optional(ATTR_PERIOD_POSITION): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
    }
)

DELETE_CLASS_PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_PERIOD_POSITION): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
    }
)

CHECK_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_IMEI): cv.string,
    }
)

ADD_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_IMEI): cv.string,
        vol.Optional(ATTR_RELATION_NAME, default=""): cv.string,
        vol.Optional(ATTR_RELATION_PHONE, default=""): cv.string,
        vol.Optional(ATTR_DEVICE_INFO, default=""): cv.string,
    }
)

REMOVE_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
    }
)

ADD_CONTACT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CONTACT_NAME): cv.string,
        vol.Required(ATTR_CONTACT_NUMBER): cv.string,
        vol.Optional(ATTR_CONTACT_ICON): vol.Any(vol.Coerce(int), cv.string),
        vol.Optional(ATTR_CONTACT_SOS, default=False): cv.boolean,
        vol.Optional(ATTR_CONTACT_SHORT_NUMBER, default=""): cv.string,
    }
)

REMOVE_CONTACT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Optional(ATTR_CONTACT_NAME): cv.string,
        vol.Optional(ATTR_CONTACT_NUMBER): cv.string,
    }
)

SET_CONTACTS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.positive_int,
        vol.Required(ATTR_CONTACTS_JSON): cv.string,
    }
)

PROFILE_FIELD_MAP = {
    ATTR_NICKNAME: "Nickname",
    ATTR_BIRTHDAY: "Birthday",
    ATTR_GENDER: "Gender",
    ATTR_GRADE: "Grade",
    ATTR_CLASS: "Class",
    ATTR_SCHOOL: "School",
    ATTR_HEIGHT: "Height",
    ATTR_WEIGHT: "Weight",
    ATTR_BLOOD_TYPE: "BloodType",
    ATTR_ALLERGIC: "Allergic",
    ATTR_NOTES: "Notes",
    ATTR_CONDITION: "Condition",
    ATTR_DRUG: "Drug",
    ATTR_ADDRESS: "Address",
    ATTR_AREA: "Area",
    ATTR_CELL_PHONE: "CellPhone",
    ATTR_CELL_PHONE_2: "CellPhone2",
}


def _parse_location(entry: dict) -> dict:
    return {
        "location_id": entry.get("LocationId"),
        "lat": entry.get("Lat"),
        "lng": entry.get("Lng"),
        "time": entry.get("Time"),
        "speed": entry.get("Speed"),
        "course": entry.get("Course"),
        "battery": entry.get("Battery"),
        "data_type": entry.get("DataType"),
        "icon": entry.get("Icon"),
        "is_stop": entry.get("IsStop"),
        "stop_time": entry.get("StopTime"),
        "stop_time_str": entry.get("StopTimeStr"),
    }


def _parse_fence(fence: dict) -> dict:
    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "fence_id": fence.get("FenceId"),
        "name": fence.get("FenceName"),
        "latitude": _f(fence.get("Latitude")),
        "longitude": _f(fence.get("Longitude")),
        "radius": fence.get("Radius"),
        "address": fence.get("Address"),
        "fence_type": fence.get("FenceType"),
        "alarm_type": fence.get("AlarmType"),
        "in_use": fence.get("InUse"),
        "is_device_fence": fence.get("IsDeviceFence"),
        "device_id": fence.get("DeviceId"),
        "start_time": fence.get("StartTime"),
        "end_time": fence.get("EndTime"),
    }


def _current_alarms(coordinator: SafeFamilyCoordinator, device_id: int) -> list[dict]:
    item = (coordinator.commands.get(device_id) or {}).get(ALARM_CODE, {})
    return parse_alarms_json(str(item.get("CmdValue") or ""))


def _current_class_windows(
    coordinator: SafeFamilyCoordinator, device_id: int
) -> list[dict]:
    item = (coordinator.commands.get(device_id) or {}).get(CLASS_MODE_CODE, {})
    return parse_class_mode_json(str(item.get("CmdValue") or ""))


def _current_schedule_raw(coordinator: SafeFamilyCoordinator, device_id: int) -> str:
    item = (coordinator.commands.get(device_id) or {}).get(CLASS_SCHEDULE_CODE, {})
    return str(item.get("CmdValue") or "")


def _parse_days_param(days) -> list[str]:
    if days is None or days == "":
        return list(DAY_NAMES)
    if isinstance(days, list):
        flat: list[str] = []
        for d in days:
            flat.extend([x.strip() for x in str(d).split(",") if x.strip()])
        normalized = [x[:3].capitalize() for x in flat if x[:3].capitalize() in DAY_NAMES]
        return normalized or list(DAY_NAMES)
    s = str(days).strip()
    if s.isdigit():
        return weeks_to_days(s)
    parts = [x.strip() for x in s.split(",") if x.strip()]
    normalized = [x[:3].capitalize() for x in parts if x[:3].capitalize() in DAY_NAMES]
    return normalized or list(DAY_NAMES)


def _normalize_hhmm(value: str) -> str:
    s = str(value).strip()
    if ":" in s:
        h, m = s.split(":", 1)
        return f"{int(h):02d}:{int(m):02d}"
    raise vol.Invalid(f"Time must be HH:MM, got {value!r}")


async def _async_register_static_paths(hass: HomeAssistant) -> None:
    """Serve emoji and contact-icon PNGs from inside the integration folder.

    Uses the modern StaticPathConfig API when available and falls back to
    the legacy register_static_path call on older HA versions. Never raises
    — a failure here should not prevent the integration from setting up.
    """
    global _STATIC_PATHS_REGISTERED
    if _STATIC_PATHS_REGISTERED:
        return

    sources = [
        (EMOJI_URL_PATH, EMOJI_DIR),
        (CONTACT_ICON_URL_PATH, CONTACT_ICON_DIR),
    ]
    configs: list[tuple[str, str]] = []
    for url_path, rel_dir in sources:
        full = Path(hass.config.path(rel_dir))
        if not full.is_dir():
            _LOGGER.warning("Asset directory missing: %s", full)
            continue
        configs.append((url_path, str(full)))

    if not configs:
        return

    try:
        try:
            from homeassistant.components.http import StaticPathConfig  # noqa: WPS433
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(url_path=u, path=p, cache_headers=False)
                    for u, p in configs
                ]
            )
        except ImportError:
            for u, p in configs:
                hass.http.register_static_path(u, p, cache_headers=False)
        _STATIC_PATHS_REGISTERED = True
        _LOGGER.debug("Registered static paths: %s", [u for u, _ in configs])
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not register static paths: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        await _async_register_static_paths(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Static path setup skipped: %s", err)

    coordinator = SafeFamilyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _handle_send_command(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID],
            call.data[ATTR_CMD_CODE],
            call.data.get(ATTR_PARAMS, ""),
        )

    async def _handle_save_profile(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        updates = {
            PROFILE_FIELD_MAP[key]: value
            for key, value in call.data.items()
            if key != ATTR_DEVICE_ID and key in PROFILE_FIELD_MAP
        }
        await coordinator.async_save_profile(device_id, updates)

    async def _handle_geofence_create(call: ServiceCall) -> None:
        await coordinator.async_geofence_create(
            call.data[ATTR_DEVICE_ID],
            call.data[ATTR_FENCE_NAME],
            call.data[ATTR_LATITUDE],
            call.data[ATTR_LONGITUDE],
            call.data[ATTR_RADIUS],
            call.data.get(ATTR_ADDRESS, ""),
        )

    async def _handle_geofence_delete(call: ServiceCall) -> None:
        await coordinator.async_geofence_delete(
            call.data[ATTR_DEVICE_ID], call.data[ATTR_FENCE_ID],
        )

    async def _handle_geofence_edit(call: ServiceCall) -> None:
        await coordinator.async_geofence_edit(
            call.data[ATTR_DEVICE_ID],
            call.data[ATTR_FENCE_ID],
            call.data[ATTR_FENCE_UPDATES],
        )

    async def _handle_geofence_list(call: ServiceCall):
        if call.data.get(ATTR_REFRESH):
            await coordinator.async_request_refresh()
        fences_by_device = coordinator.geofences or {}
        requested_device = call.data.get(ATTR_DEVICE_ID)

        if requested_device is not None:
            raw = fences_by_device.get(requested_device, []) or []
            parsed = [_parse_fence(f) for f in raw]
            return {
                "device_id": requested_device,
                "count": len(parsed),
                "fences": parsed,
            }

        all_fences: list[dict] = []
        for did, fences in fences_by_device.items():
            for f in fences or []:
                parsed = _parse_fence(f)
                if parsed.get("device_id") is None:
                    parsed["device_id"] = did
                all_fences.append(parsed)

        return {"count": len(all_fences), "fences": all_fences}

    async def _handle_location_history(call: ServiceCall):
        raw = await coordinator.async_get_location_history(
            call.data[ATTR_DEVICE_ID],
            call.data[ATTR_START_TIME],
            call.data[ATTR_END_TIME],
            call.data.get(ATTR_SELECT_COUNT, 500),
        )
        parsed = [_parse_location(item) for item in raw]
        parsed.sort(key=lambda p: p.get("time") or "", reverse=True)
        return {"count": len(parsed), "items": parsed}

    async def _handle_send_text(call: ServiceCall) -> None:
        await coordinator.async_send_text(
            call.data[ATTR_DEVICE_ID], call.data[ATTR_TEXT]
        )

    async def _handle_send_emoji(call: ServiceCall) -> None:
        await coordinator.async_send_emoji(
            call.data[ATTR_DEVICE_ID], call.data[ATTR_EMOJI]
        )

    async def _handle_set_alarms(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID], ALARM_CODE, call.data[ATTR_ALARMS_JSON]
        )
        await coordinator.async_request_refresh()

    async def _handle_add_alarm(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        time_str = _normalize_hhmm(call.data[ATTR_ALARM_TIME])
        days = _parse_days_param(call.data.get(ATTR_ALARM_DAYS))
        alarms = _current_alarms(coordinator, device_id)
        alarms.append(default_alarm(time_str, days, enabled=True))
        params = json.dumps(alarms, separators=(",", ":"))
        await coordinator.async_send_command(device_id, ALARM_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_delete_alarm(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        alarms = _current_alarms(coordinator, device_id)

        idx = call.data.get(ATTR_ALARM_INDEX)
        time_filter = call.data.get(ATTR_ALARM_TIME)

        if idx is not None:
            if idx < 0 or idx >= len(alarms):
                raise vol.Invalid(f"Alarm index {idx} out of range (0-{len(alarms)-1})")
            remaining = [a for i, a in enumerate(alarms) if i != idx]
        elif time_filter:
            tf = _normalize_hhmm(time_filter)
            remaining = [a for a in alarms if str(a.get("Time") or "") != tf]
            if len(remaining) == len(alarms):
                raise vol.Invalid(f"No alarm found with time {time_filter!r}")
        else:
            raise vol.Invalid("Provide either 'index' or 'time' to delete an alarm")

        params = json.dumps(remaining, separators=(",", ":")) if remaining else "[]"
        await coordinator.async_send_command(device_id, ALARM_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_set_class_mode(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID],
            CLASS_MODE_CODE,
            call.data[ATTR_CLASS_WINDOWS_JSON],
        )
        await coordinator.async_request_refresh()

    async def _handle_add_class_window(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        start = _normalize_hhmm(call.data[ATTR_CLASS_START])
        end = _normalize_hhmm(call.data[ATTR_CLASS_END])
        days = _parse_days_param(call.data.get(ATTR_CLASS_DAYS))

        windows = _current_class_windows(coordinator, device_id)
        windows.append(make_class_window(start, end, days, enabled=True))
        params = json.dumps(windows, separators=(",", ":"))
        await coordinator.async_send_command(device_id, CLASS_MODE_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_clear_class_mode(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID], CLASS_MODE_CODE, "[]"
        )
        await coordinator.async_request_refresh()

    async def _handle_set_class_schedule(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID],
            CLASS_SCHEDULE_CODE,
            call.data[ATTR_SCHEDULE_JSON],
        )
        await coordinator.async_request_refresh()

    async def _handle_set_class_subject(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        day_index = normalize_day_param(call.data[ATTR_SCHEDULE_DAY])
        period = int(call.data[ATTR_SCHEDULE_PERIOD])
        subject = str(call.data[ATTR_SCHEDULE_SUBJECT]).strip()

        raw = _current_schedule_raw(coordinator, device_id)
        windows = parse_schedule_json(raw)
        if not windows:
            raise vol.Invalid(
                "No schedule exists yet — use set_class_schedule or add_class_period first"
            )

        week0 = next((w for w in windows if w.get("Week") == 0), None)
        if week0 is None:
            raise vol.Invalid("Schedule has no Week 0 (period definitions)")

        periods = parse_periods(week0.get("Subject", ""))
        if period < 1 or period > len(periods):
            raise vol.Invalid(f"Period {period} out of range 1-{len(periods)}")

        day_entry = next((w for w in windows if w.get("Week") == day_index), None)
        if day_entry is None:
            day_entry = {"Week": day_index, "Subject": ""}
            windows.append(day_entry)

        sched = parse_schedule(raw)
        day_name = SCHEDULE_DAY_NAMES.get(day_index, "Mon")
        subjects = list(sched["days"].get(day_name, [None] * len(periods)))
        while len(subjects) < len(periods):
            subjects.append(None)
        subjects[period - 1] = subject or None
        day_entry["Subject"] = encode_day_subjects(subjects[: len(periods)])

        params = json.dumps(windows, separators=(",", ":"))
        await coordinator.async_send_command(device_id, CLASS_SCHEDULE_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_clear_class_schedule(call: ServiceCall) -> None:
        await coordinator.async_send_command(
            call.data[ATTR_DEVICE_ID], CLASS_SCHEDULE_CODE, "[]"
        )
        await coordinator.async_request_refresh()

    async def _handle_add_class_period(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        start = _normalize_hhmm(call.data[ATTR_CLASS_START])
        end = _normalize_hhmm(call.data[ATTR_CLASS_END])
        position = call.data.get(ATTR_PERIOD_POSITION)

        raw = _current_schedule_raw(coordinator, device_id)
        try:
            windows = add_period(raw, start, end, position)
        except ValueError as err:
            raise vol.Invalid(str(err)) from err

        params = json.dumps(windows, separators=(",", ":"))
        await coordinator.async_send_command(device_id, CLASS_SCHEDULE_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_delete_class_period(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        position = int(call.data[ATTR_PERIOD_POSITION])

        raw = _current_schedule_raw(coordinator, device_id)
        try:
            windows = delete_period(raw, position)
        except ValueError as err:
            raise vol.Invalid(str(err)) from err

        params = json.dumps(windows, separators=(",", ":"))
        await coordinator.async_send_command(device_id, CLASS_SCHEDULE_CODE, params)
        await coordinator.async_request_refresh()

    async def _handle_check_device(call: ServiceCall):
        return await coordinator.async_check_device(call.data[ATTR_IMEI])

    async def _handle_add_device(call: ServiceCall):
        return await coordinator.async_add_device(
            call.data[ATTR_IMEI],
            call.data.get(ATTR_RELATION_NAME, ""),
            call.data.get(ATTR_RELATION_PHONE, ""),
            call.data.get(ATTR_DEVICE_INFO, ""),
        )

    async def _handle_remove_device(call: ServiceCall):
        return await coordinator.async_remove_device(call.data[ATTR_DEVICE_ID])

    async def _handle_add_contact(call: ServiceCall) -> None:
        await coordinator.async_add_contact(
            call.data[ATTR_DEVICE_ID],
            call.data[ATTR_CONTACT_NAME],
            call.data[ATTR_CONTACT_NUMBER],
            call.data.get(ATTR_CONTACT_ICON, 6),
            call.data.get(ATTR_CONTACT_SOS, False),
            call.data.get(ATTR_CONTACT_SHORT_NUMBER, ""),
        )

    async def _handle_remove_contact(call: ServiceCall) -> None:
        await coordinator.async_remove_contact(
            call.data[ATTR_DEVICE_ID],
            call.data.get(ATTR_CONTACT_NAME),
            call.data.get(ATTR_CONTACT_NUMBER),
        )

    async def _handle_set_contacts(call: ServiceCall) -> None:
        await coordinator.async_set_contacts(
            call.data[ATTR_DEVICE_ID], call.data[ATTR_CONTACTS_JSON]
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_COMMAND, _handle_send_command,
            schema=SEND_COMMAND_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SAVE_PROFILE):
        hass.services.async_register(
            DOMAIN, SERVICE_SAVE_PROFILE, _handle_save_profile,
            schema=SAVE_PROFILE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GEOFENCE_CREATE):
        hass.services.async_register(
            DOMAIN, SERVICE_GEOFENCE_CREATE, _handle_geofence_create,
            schema=GEOFENCE_CREATE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GEOFENCE_DELETE):
        hass.services.async_register(
            DOMAIN, SERVICE_GEOFENCE_DELETE, _handle_geofence_delete,
            schema=GEOFENCE_DELETE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GEOFENCE_EDIT):
        hass.services.async_register(
            DOMAIN, SERVICE_GEOFENCE_EDIT, _handle_geofence_edit,
            schema=GEOFENCE_EDIT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GEOFENCE_LIST):
        hass.services.async_register(
            DOMAIN, SERVICE_GEOFENCE_LIST, _handle_geofence_list,
            schema=GEOFENCE_LIST_SCHEMA, supports_response=True,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_LOCATION_HISTORY):
        hass.services.async_register(
            DOMAIN, SERVICE_LOCATION_HISTORY, _handle_location_history,
            schema=LOCATION_HISTORY_SCHEMA, supports_response=True,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TEXT):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_TEXT, _handle_send_text,
            schema=SEND_TEXT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_EMOJI):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_EMOJI, _handle_send_emoji,
            schema=SEND_EMOJI_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_ALARMS):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_ALARMS, _handle_set_alarms,
            schema=SET_ALARMS_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_ALARM):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_ALARM, _handle_add_alarm,
            schema=ADD_ALARM_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_ALARM):
        hass.services.async_register(
            DOMAIN, SERVICE_DELETE_ALARM, _handle_delete_alarm,
            schema=DELETE_ALARM_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_CLASS_MODE):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CLASS_MODE, _handle_set_class_mode,
            schema=SET_CLASS_MODE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_CLASS_WINDOW):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_CLASS_WINDOW, _handle_add_class_window,
            schema=ADD_CLASS_WINDOW_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_CLASS_MODE):
        hass.services.async_register(
            DOMAIN, SERVICE_CLEAR_CLASS_MODE, _handle_clear_class_mode,
            schema=CLEAR_CLASS_MODE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_CLASS_SCHEDULE):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CLASS_SCHEDULE, _handle_set_class_schedule,
            schema=SET_CLASS_SCHEDULE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_CLASS_SUBJECT):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CLASS_SUBJECT, _handle_set_class_subject,
            schema=SET_CLASS_SUBJECT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_CLASS_SCHEDULE):
        hass.services.async_register(
            DOMAIN, SERVICE_CLEAR_CLASS_SCHEDULE, _handle_clear_class_schedule,
            schema=CLEAR_CLASS_SCHEDULE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_CLASS_PERIOD):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_CLASS_PERIOD, _handle_add_class_period,
            schema=ADD_CLASS_PERIOD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_CLASS_PERIOD):
        hass.services.async_register(
            DOMAIN, SERVICE_DELETE_CLASS_PERIOD, _handle_delete_class_period,
            schema=DELETE_CLASS_PERIOD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_DEVICE):
        hass.services.async_register(
            DOMAIN, SERVICE_CHECK_DEVICE, _handle_check_device,
            schema=CHECK_DEVICE_SCHEMA, supports_response=True,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_DEVICE):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_DEVICE, _handle_add_device,
            schema=ADD_DEVICE_SCHEMA, supports_response=True,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_DEVICE):
        hass.services.async_register(
            DOMAIN, SERVICE_REMOVE_DEVICE, _handle_remove_device,
            schema=REMOVE_DEVICE_SCHEMA, supports_response=True,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_CONTACT):
        hass.services.async_register(
            DOMAIN, SERVICE_ADD_CONTACT, _handle_add_contact,
            schema=ADD_CONTACT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_CONTACT):
        hass.services.async_register(
            DOMAIN, SERVICE_REMOVE_CONTACT, _handle_remove_contact,
            schema=REMOVE_CONTACT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_CONTACTS):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CONTACTS, _handle_set_contacts,
            schema=SET_CONTACTS_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            for svc in (
                SERVICE_SEND_COMMAND,
                SERVICE_SAVE_PROFILE,
                SERVICE_GEOFENCE_CREATE,
                SERVICE_GEOFENCE_DELETE,
                SERVICE_GEOFENCE_EDIT,
                SERVICE_GEOFENCE_LIST,
                SERVICE_LOCATION_HISTORY,
                SERVICE_SEND_TEXT,
                SERVICE_SEND_EMOJI,
                SERVICE_SET_ALARMS,
                SERVICE_ADD_ALARM,
                SERVICE_DELETE_ALARM,
                SERVICE_SET_CLASS_MODE,
                SERVICE_ADD_CLASS_WINDOW,
                SERVICE_CLEAR_CLASS_MODE,
                SERVICE_SET_CLASS_SCHEDULE,
                SERVICE_SET_CLASS_SUBJECT,
                SERVICE_CLEAR_CLASS_SCHEDULE,
                SERVICE_ADD_CLASS_PERIOD,
                SERVICE_DELETE_CLASS_PERIOD,
                SERVICE_CHECK_DEVICE,
                SERVICE_ADD_DEVICE,
                SERVICE_REMOVE_DEVICE,
                SERVICE_ADD_CONTACT,
                SERVICE_REMOVE_CONTACT,
                SERVICE_SET_CONTACTS,
            ):
                hass.services.async_remove(DOMAIN, svc)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)