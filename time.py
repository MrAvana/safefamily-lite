"""Time entities for Care Time window (9203)."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator


CARE_TIME_CODE = "9203"


def parse_window(raw: str) -> tuple[bool, time, time]:
    parts = (raw or "").split(",")
    if len(parts) < 3:
        return False, time(0, 0), time(23, 59)

    def to_time(s: str) -> time:
        try:
            h = int(s[:2])
            m = int(s[2:4])
            if h == 24:
                h = 0
            return time(max(0, min(23, h)), max(0, min(59, m)))
        except (ValueError, IndexError):
            return time(0, 0)

    return parts[0] == "1", to_time(parts[1]), to_time(parts[2])


def format_window(enabled: bool, start: time, end: time) -> str:
    start_str = f"{start.hour:02d}{start.minute:02d}"
    if end.hour == 0 and end.minute == 0:
        end_str = "2400"
    else:
        end_str = f"{end.hour:02d}{end.minute:02d}"
    return f"{1 if enabled else 0},{start_str},{end_str}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyCareTimeStart(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )
    add(
        SafeFamilyCareTimeEnd(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class _CareTimeBase(CoordinatorEntity[SafeFamilyCoordinator], TimeEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, device_id: int, dev: dict, key: str):
        super().__init__(coord)
        self._device_id = device_id
        self._attr_translation_key = key
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_time_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    def _cmd_value(self) -> str:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            CARE_TIME_CODE, {}
        )
        return str(item.get("CmdValue") or "")

    async def _write(self, enabled: bool, start: time, end: time) -> None:
        await self.coordinator.async_send_command(
            self._device_id, CARE_TIME_CODE, format_window(enabled, start, end)
        )
        await self.coordinator.async_request_refresh()


class SafeFamilyCareTimeStart(_CareTimeBase):
    _attr_icon = "mdi:clock-start"

    def __init__(self, coord, device_id, dev):
        super().__init__(coord, device_id, dev, "care_time_start")

    @property
    def native_value(self) -> time | None:
        raw = self._cmd_value()
        if not raw:
            return None
        _, start, _ = parse_window(raw)
        return start

    async def async_set_value(self, value: time) -> None:
        enabled, _, end = parse_window(self._cmd_value())
        await self._write(enabled, value, end)


class SafeFamilyCareTimeEnd(_CareTimeBase):
    _attr_icon = "mdi:clock-end"

    def __init__(self, coord, device_id, dev):
        super().__init__(coord, device_id, dev, "care_time_end")

    @property
    def native_value(self) -> time | None:
        raw = self._cmd_value()
        if not raw:
            return None
        _, _, end = parse_window(raw)
        return end

    async def async_set_value(self, value: time) -> None:
        enabled, start, _ = parse_window(self._cmd_value())
        await self._write(enabled, start, value)