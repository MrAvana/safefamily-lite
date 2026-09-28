"""Sensors for SafeFamily Lite (numeric, timestamp, enum, diagnostic)."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .alarms import (
    ALARM_CODE,
    is_enabled,
    next_trigger,
    parse_alarms_json,
    weeks_to_days,
)
from .chat import emoji_label, is_emoji_code
from .classmode import (
    CLASS_MODE_CODE,
    normalize_window,
    parse_class_mode_json,
)
from .classschedule import (
    CLASS_SCHEDULE_CODE,
    parse_schedule,
)
from .contacts import CONTACTS_CODE, normalize_contacts, parse_contacts_json
from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator


NUMERIC_DEFS = [
    ("Battery", "Battery", "%", SensorDeviceClass.BATTERY, None, "battery"),
    ("Steps", "Steps", "steps", None, SensorStateClass.TOTAL_INCREASING, "steps"),
    ("Satellite", "Satellites", "sats", None, None, "satellites"),
    ("Signal", "Signal", "%", None, None, "signal"),
]

TIMESTAMP_DEFS = [
    ("DeviceUtcTime", "Last Contact", "last_contact"),
    ("LastCommunication", "Last Heartbeat", "last_heartbeat"),
]

POSITION_TYPE_MAP = {1: "GPS", 2: "LBS", 3: "WiFi", 0: "Unknown"}
CALL_TYPE_MAP = {0: "Incoming", 1: "Outgoing", 2: "Missed", 3: "Rejected"}
GENDER_MAP = {0: "Unknown", 1: "Male", 2: "Female"}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * R * asin(sqrt(a))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for device_id, dev in (coord.data or {}).items():
        for field, name, unit, dev_class, state_class, key in NUMERIC_DEFS:
            entities.append(
                SafeFamilyNumericSensor(
                    coord, device_id, dev, field, name, unit, dev_class, state_class, key
                )
            )
        for field, name, key in TIMESTAMP_DEFS:
            entities.append(
                SafeFamilyTimestampSensor(coord, device_id, dev, field, name, key)
            )
        entities.append(SafeFamilyPositionModeSensor(coord, device_id, dev))
        entities.append(SafeFamilyLastCallSensor(coord, device_id, dev))
        entities.append(SafeFamilyCallHistorySensor(coord, device_id, dev))
        entities.append(SafeFamilyCommandsSensor(coord, device_id, dev))
        entities.append(SafeFamilyProfileSensor(coord, device_id, dev))
        entities.append(SafeFamilyGeofencesSensor(coord, device_id, dev))
        entities.append(SafeFamilyStepsTodaySensor(coord, device_id, dev))
        entities.append(SafeFamilyFriendsSensor(coord, device_id, dev))
        entities.append(SafeFamilySharesSensor(coord, device_id, dev))
        entities.append(SafeFamilyAlertsSensor(coord, device_id, dev))
        entities.append(SafeFamilyNextAlarmSensor(coord, device_id, dev))
        entities.append(SafeFamilyAlarmsSensor(coord, device_id, dev))
        entities.append(SafeFamilyDeviceIdSensor(coord, device_id, dev))
        entities.append(SafeFamilyImeiSensor(coord, device_id, dev))
        entities.append(SafeFamilyClassModeSensor(coord, device_id, dev))
        entities.append(SafeFamilyTimetableSensor(coord, device_id, dev))
        entities.append(SafeFamilyMessagesSensor(coord, device_id, dev))
        entities.append(SafeFamilyVoiceMessagesSensor(coord, device_id, dev))
        entities.append(SafeFamilyPhotosSensor(coord, device_id, dev))
        entities.append(SafeFamilyContactsSensor(coord, device_id, dev))
        entities.append(SafeFamilyLocationHistorySensor(coord, device_id, dev))

    add(entities)


class _SafeFamilyBase(CoordinatorEntity[SafeFamilyCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, device_id: int, dev: dict, field: str, translation_key: str):
        super().__init__(coord)
        self._device_id = device_id
        self._field = field
        self._attr_translation_key = translation_key
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_{field.lower()}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    def _device(self) -> dict | None:
        return (self.coordinator.data or {}).get(self._device_id)


class SafeFamilyNumericSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id, dev, field, name, unit, dev_class, state_class, key):
        super().__init__(coord, device_id, dev, field, key)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_state_class = state_class

    @property
    def native_value(self):
        dev = self._device()
        return None if not dev else dev.get(self._field)


class SafeFamilyTimestampSensor(_SafeFamilyBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord, device_id, dev, field, name, translation_key):
        super().__init__(coord, device_id, dev, field, translation_key)

    @property
    def native_value(self):
        dev = self._device()
        if not dev:
            return None
        raw = dev.get(self._field)
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw).replace(" ", "T"))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed

    @property
    def extra_state_attributes(self):
        dev = self._device() or {}
        return {
            "raw_value": dev.get(self._field),
            "status_code": dev.get("Status"),
            "position_type": dev.get("PositionType"),
        }


class SafeFamilyPositionModeSensor(_SafeFamilyBase):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(POSITION_TYPE_MAP.values())

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "PositionType", "position_mode")

    @property
    def native_value(self) -> str | None:
        dev = self._device()
        if not dev:
            return None
        raw = dev.get("PositionType")
        if raw is None:
            return None
        try:
            return POSITION_TYPE_MAP.get(int(raw), f"Unknown ({raw})")
        except (TypeError, ValueError):
            return f"Unknown ({raw})"

    @property
    def extra_state_attributes(self):
        dev = self._device() or {}
        return {
            "position_type": dev.get("PositionType"),
            "status_code": dev.get("Status"),
            "satellites": dev.get("Satellite"),
        }


class SafeFamilyLastCallSensor(_SafeFamilyBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "LastCall", "last_call")

    @property
    def _history(self) -> list[dict]:
        return (self.coordinator.calls_history or {}).get(self._device_id, []) or []

    @property
    def native_value(self):
        hist = self._history
        if not hist:
            return None
        latest = sorted(hist, key=lambda e: e.get("call_date", ""))[-1]
        raw = latest.get("call_date")
        if not raw:
            return None
        return dt_util.parse_datetime(raw.replace(" ", "T", 1))

    @property
    def extra_state_attributes(self):
        hist = self._history
        if not hist:
            return {"total_calls": 0}
        latest = sorted(hist, key=lambda e: e.get("call_date", ""))[-1]
        calls_last = (self.coordinator.calls_last or {}).get(self._device_id) or {}
        return {
            "total_calls": len(hist),
            "last_call_account": latest.get("account"),
            "last_call_type_raw": latest.get("call_type"),
            "last_call_type": CALL_TYPE_MAP.get(
                latest.get("call_type"), f"unknown ({latest.get('call_type')})"
            ),
            "calls_last_value": calls_last.get("callsLast"),
        }


class SafeFamilyCallHistorySensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "CallHistory", "call_history")

    @property
    def _history(self) -> list[dict]:
        return (self.coordinator.calls_history or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._history)

    @property
    def extra_state_attributes(self):
        return {"total_calls": len(self._history), "history": self._history[:50]}


class SafeFamilyCommandsSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Commands", "commands")
        self._attr_icon = "mdi:format-list-bulleted"

    @property
    def _commands(self) -> dict[str, dict]:
        return (self.coordinator.commands or {}).get(self._device_id, {}) or {}

    @property
    def native_value(self) -> int:
        return len(self._commands)

    @property
    def extra_state_attributes(self):
        return {
            f"{code}_{item.get('Name', '').replace(' ', '_') or 'unnamed'}": item.get(
                "CmdValue"
            )
            for code, item in sorted(self._commands.items())
        }


class SafeFamilyProfileSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Profile", "profile")
        self._attr_icon = "mdi:account-card"

    @property
    def _profile(self) -> dict:
        return (self.coordinator.profiles or {}).get(self._device_id, {}) or {}

    @property
    def native_value(self) -> str | None:
        return self._profile.get("Nickname") or None

    @property
    def extra_state_attributes(self):
        p = self._profile
        return {
            "birthday": p.get("Birthday"),
            "gender_raw": p.get("Gender"),
            "gender": GENDER_MAP.get(p.get("Gender"), "unknown"),
            "grade": p.get("Grade"),
            "class": p.get("Class"),
            "school": p.get("School"),
            "height_cm": p.get("Height"),
            "weight_kg": p.get("Weight"),
            "blood_type": p.get("BloodType"),
            "allergies": p.get("Allergic"),
            "medical_notes": p.get("Notes"),
            "conditions": p.get("Condition"),
            "drug": p.get("Drug"),
            "address": p.get("Address"),
            "area": p.get("Area"),
            "cell_phone": p.get("CellPhone"),
            "cell_phone_2": p.get("CellPhone2"),
            "sim": p.get("Sim"),
            "update_time": p.get("UpdateTime"),
        }


class SafeFamilyGeofencesSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Geofences", "geofences")
        self._attr_icon = "mdi:map-marker-radius"

    @property
    def _fences(self) -> list[dict]:
        return (self.coordinator.geofences or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._fences)

    @property
    def extra_state_attributes(self):
        return {"fences": self._fences}


class SafeFamilyStepsTodaySensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "StepsToday", "steps_today")
        self._attr_icon = "mdi:walk"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = "steps"

    @property
    def _data(self) -> dict:
        return (self.coordinator.steps_today or {}).get(self._device_id, {}) or {}

    @property
    def native_value(self) -> int | None:
        raw = self._data.get("Step")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        d = self._data
        hourly = [
            {
                "hour": item.get("Hour"),
                "steps": item.get("Steps"),
                "distance": item.get("Distance"),
                "calories": item.get("Cariello"),
            }
            for item in (d.get("Items") or [])
        ]
        return {
            "distance": d.get("Distance"),
            "calories": d.get("Cariello"),
            "hourly": hourly,
        }


class SafeFamilyFriendsSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Friends", "friends")
        self._attr_icon = "mdi:account-multiple"

    @property
    def _items(self) -> list[dict]:
        return (self.coordinator.friends or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        friends = [
            {
                "name": item.get("Nickname"),
                "phone": item.get("PhoneNum"),
                "imei": item.get("IMEI"),
                "avatar": item.get("AvatarImage"),
            }
            for item in self._items
        ]
        return {"friends": friends}


class SafeFamilySharesSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Shares", "shares")
        self._attr_icon = "mdi:account-group"

    @property
    def _items(self) -> list[dict]:
        return (self.coordinator.shares or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        return {"shares": self._items}


class SafeFamilyAlertsSensor(_SafeFamilyBase):
    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Alerts", "alerts")
        self._attr_icon = "mdi:alert-circle"

    @property
    def _items(self) -> list[dict]:
        return (self.coordinator.alerts or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        items = self._items
        sorted_items = sorted(
            items, key=lambda e: e.get("CreateDate") or "", reverse=True
        )
        latest = sorted_items[0] if sorted_items else {}
        compact = [
            {
                "name": it.get("ExceptionName"),
                "message": it.get("Message"),
                "date": it.get("CreateDate"),
                "device_date": it.get("DeviceDate"),
                "address": it.get("Address"),
                "lat": it.get("Lat"),
                "lng": it.get("Lng"),
                "fence_no": it.get("FenceNo"),
                "fence_id": it.get("GeoFenceID"),
                "exception_id": it.get("ExceptionID"),
                "notification_type": it.get("NotificationType"),
                "deleted": it.get("Deleted"),
            }
            for it in sorted_items[:30]
        ]
        return {
            "last_alert_name": latest.get("ExceptionName"),
            "last_alert_message": latest.get("Message"),
            "last_alert_date": latest.get("CreateDate"),
            "last_alert_address": latest.get("Address"),
            "alerts": compact,
        }


class SafeFamilyNextAlarmSensor(_SafeFamilyBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "NextAlarm", "next_alarm")

    def _raw_alarms(self) -> list[dict]:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            ALARM_CODE, {}
        )
        return parse_alarms_json(str(item.get("CmdValue") or ""))

    @property
    def native_value(self):
        return next_trigger(self._raw_alarms())

    @property
    def extra_state_attributes(self):
        alarms = self._raw_alarms()
        next_fire = self.native_value
        next_alarm_info = None
        if next_fire is not None:
            for a in alarms:
                if not is_enabled(a):
                    continue
                t = str(a.get("Time") or "")
                try:
                    hh, mm = map(int, t.split(":"))
                except ValueError:
                    continue
                if hh == next_fire.hour and mm == next_fire.minute:
                    next_alarm_info = {
                        "time": t,
                        "days": weeks_to_days(str(a.get("Weeks") or "")),
                    }
                    break

        return {
            "next_alarm_time": next_alarm_info["time"] if next_alarm_info else None,
            "next_alarm_days": next_alarm_info["days"] if next_alarm_info else None,
            "count": len(alarms),
            "enabled_count": sum(1 for a in alarms if is_enabled(a)),
            "alarms": [
                {
                    "time": a.get("Time"),
                    "days": weeks_to_days(str(a.get("Weeks") or "")),
                    "enabled": is_enabled(a),
                }
                for a in alarms
            ],
        }


class SafeFamilyAlarmsSensor(_SafeFamilyBase):
    _attr_icon = "mdi:alarm-multiple"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Alarms", "alarms")

    def _raw_alarms(self) -> list[dict]:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            ALARM_CODE, {}
        )
        return parse_alarms_json(str(item.get("CmdValue") or ""))

    @property
    def native_value(self) -> int:
        return len(self._raw_alarms())

    @property
    def extra_state_attributes(self):
        alarms = self._raw_alarms()
        return {
            "enabled_count": sum(1 for a in alarms if is_enabled(a)),
            "alarms": [
                {
                    "time": a.get("Time"),
                    "days": weeks_to_days(str(a.get("Weeks") or "")),
                    "enabled": is_enabled(a),
                }
                for a in alarms
            ],
        }


class SafeFamilyDeviceIdSensor(_SafeFamilyBase):
    _attr_icon = "mdi:identifier"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "DeviceId", "device_id")

    @property
    def native_value(self) -> str:
        return str(self._device_id)

    @property
    def extra_state_attributes(self):
        dev = self._device() or {}
        return {
            "imei": dev.get("SerialNumber"),
            "model": dev.get("Model"),
            "type": dev.get("Type"),
        }


class SafeFamilyImeiSensor(_SafeFamilyBase):
    _attr_icon = "mdi:barcode"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Imei", "imei")

    @property
    def native_value(self) -> str | None:
        dev = self._device()
        if not dev:
            return None
        return dev.get("SerialNumber")

    @property
    def extra_state_attributes(self):
        dev = self._device() or {}
        return {
            "device_id": self._device_id,
            "imsi": dev.get("IMSI"),
            "sim": dev.get("Sim"),
        }


class SafeFamilyClassModeSensor(_SafeFamilyBase):
    _attr_icon = "mdi:school"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "ClassMode", "class_mode")

    def _raw_windows(self) -> list[dict]:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            CLASS_MODE_CODE, {}
        )
        return parse_class_mode_json(str(item.get("CmdValue") or ""))

    @property
    def native_value(self) -> int:
        return len(self._raw_windows())

    @property
    def extra_state_attributes(self):
        windows = [normalize_window(w) for w in self._raw_windows()]
        enabled_count = sum(1 for w in windows if w.get("enabled"))
        return {
            "enabled_count": enabled_count,
            "windows": windows,
        }


class SafeFamilyTimetableSensor(_SafeFamilyBase):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Timetable", "timetable")

    def _raw(self) -> str:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            CLASS_SCHEDULE_CODE, {}
        )
        return str(item.get("CmdValue") or "")

    @property
    def native_value(self) -> int:
        sched = parse_schedule(self._raw())
        return sum(
            1
            for subjects in sched["days"].values()
            for s in subjects
            if s
        )

    @property
    def extra_state_attributes(self):
        sched = parse_schedule(self._raw())
        return {
            "period_count": len(sched["periods"]),
            "periods": sched["periods"],
            "days": sched["days"],
        }


class SafeFamilyMessagesSensor(_SafeFamilyBase):
    _attr_icon = "mdi:message-text"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Messages", "messages")

    @property
    def _items(self) -> list[dict]:
        return (self.coordinator.messages or {}).get(self._device_id, []) or []

    def _clean(self, item: dict) -> dict:
        content = item.get("Content") or ""
        emoji = is_emoji_code(content)
        return {
            "file_id": item.get("FileId"),
            "content": content,
            "display": emoji_label(content) if emoji else content,
            "emoji": emoji,
            "created": item.get("Created"),
            "type": item.get("Type"),
            "source_type": item.get("SourceType"),
            "is_read": item.get("IsRead"),
            "user_id": item.get("UserId"),
            "avatar": item.get("Avatar"),
        }

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        items = sorted(
            self._items, key=lambda e: e.get("Created") or "", reverse=True
        )
        compact = [self._clean(it) for it in items[:20]]
        last = compact[0] if compact else None
        return {
            "last_content": last.get("content") if last else None,
            "last_display": last.get("display") if last else None,
            "last_created": last.get("created") if last else None,
            "last_is_emoji": last.get("emoji") if last else None,
            "messages": compact,
        }


class SafeFamilyVoiceMessagesSensor(_SafeFamilyBase):
    _attr_icon = "mdi:microphone"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "VoiceMessages", "voice_messages")

    @property
    def _items(self) -> list[dict]:
        return (
            (self.coordinator.voice_messages or {}).get(self._device_id, []) or []
        )

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        items = sorted(
            self._items, key=lambda e: e.get("Created") or "", reverse=True
        )
        compact = [
            {
                "file_id": it.get("FileId"),
                "url": it.get("FileUrl"),
                "created": it.get("Created"),
                "is_read": it.get("IsRead"),
                "type": it.get("Type"),
                "source_type": it.get("SourceType"),
            }
            for it in items[:20]
        ]
        last = compact[0] if compact else None
        return {
            "last_url": last.get("url") if last else None,
            "last_created": last.get("created") if last else None,
            "voice_messages": compact,
        }


class SafeFamilyPhotosSensor(_SafeFamilyBase):
    _attr_icon = "mdi:image-multiple"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Photos", "photos")

    @property
    def _items(self) -> list[dict]:
        return (self.coordinator.photos or {}).get(self._device_id, []) or []

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self):
        items = sorted(
            self._items, key=lambda e: e.get("Created") or "", reverse=True
        )
        compact = [
            {
                "file_id": it.get("FileId"),
                "url": it.get("FileName"),
                "created": it.get("Created"),
                "date": it.get("Date"),
            }
            for it in items[:30]
        ]
        last = compact[0] if compact else None
        return {
            "last_url": last.get("url") if last else None,
            "last_created": last.get("created") if last else None,
            "photos": compact,
        }


class SafeFamilyContactsSensor(_SafeFamilyBase):
    """SOS / phonebook contacts stored on the watch."""

    _attr_icon = "mdi:account-box-multiple"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "Contacts", "contacts")

    def _raw(self) -> list[dict]:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            CONTACTS_CODE, {}
        )
        return parse_contacts_json(str(item.get("CmdValue") or ""))

    @property
    def native_value(self) -> int:
        return len(self._raw())

    @property
    def extra_state_attributes(self):
        contacts = normalize_contacts(self._raw())
        sos_count = sum(1 for c in contacts if c["sos"])
        return {
            "sos_count": sos_count,
            "contacts": contacts,
        }


class SafeFamilyLocationHistorySensor(_SafeFamilyBase):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = "km"
    _attr_icon = "mdi:map-marker-path"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    _MAX_ATTRIBUTE_POINTS = 200

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord, device_id, dev, "LocationHistory", "location_history")

    @property
    def _points(self) -> list[dict]:
        return (
            (self.coordinator.location_history_today or {}).get(self._device_id, [])
            or []
        )

    @property
    def _sorted_points(self) -> list[dict]:
        return sorted(self._points, key=lambda p: str(p.get("Time") or ""))

    @property
    def native_value(self) -> float:
        pts = self._sorted_points
        if len(pts) < 2:
            return 0.0
        total = 0.0
        prev: tuple[float, float] | None = None
        for p in pts:
            try:
                lat = float(p.get("Lat"))
                lng = float(p.get("Lng"))
            except (TypeError, ValueError):
                continue
            if prev is not None:
                total += _haversine_km(prev[0], prev[1], lat, lng)
            prev = (lat, lng)
        return round(total, 3)

    @property
    def extra_state_attributes(self):
        pts = self._sorted_points
        if not pts:
            return {"point_count": 0, "points": []}

        first = pts[0]
        last = pts[-1]

        trail_source = pts[-self._MAX_ATTRIBUTE_POINTS:]
        trail = [
            {
                "time": p.get("Time"),
                "lat": p.get("Lat"),
                "lng": p.get("Lng"),
                "speed": p.get("Speed"),
                "battery": p.get("Battery"),
                "data_type": p.get("DataType"),
            }
            for p in trail_source
        ]

        return {
            "point_count": len(pts),
            "first_time": first.get("Time"),
            "last_time": last.get("Time"),
            "last_lat": last.get("Lat"),
            "last_lng": last.get("Lng"),
            "last_battery": last.get("Battery"),
            "last_data_type": last.get("DataType"),
            "points_returned": len(trail),
            "points_capped": len(pts) > self._MAX_ATTRIBUTE_POINTS,
            "points": trail,
        }