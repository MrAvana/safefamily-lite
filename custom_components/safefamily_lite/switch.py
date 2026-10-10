"""Switches for SafeFamily Lite device settings."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator

_LOGGER = logging.getLogger(__name__)


# Data-driven switch definitions.
#
# Every switch here has been validated against a mitmproxy capture of the
# SafeFamily app, so we know both the correct CmdCode and the on/off params.
#
# Removed as non-functional (present in CommandList but never sent by the
# app and not observed to affect the watch):
#   0144 "Set the bluetooth switch"
#   0115 "Set the body feeling switch"
#
# Each entry:
#   key          translation key (matches translations/en.json)
#   on           list of (cmd_code, params) sent on turn_on, in order
#   off          list of (cmd_code, params) sent on turn_off, in order
#   state_code   CmdCode whose CmdValue represents the switch state
#   state_match  ("exact", str) or ("prefix", str) against CmdValue
SWITCH_DEFS = [
    {
        "key": "stranger_block",
        "on": [("9008", "0")],       # inverted: "0" enables protection
        "off": [("9008", "1")],
        "state_code": "9008",
        "state_match": ("exact", "0"),
    },
    {
        "key": "auto_answer",
        "on": [("9209", "1")],
        "off": [("9209", "0")],
        "state_code": "9209",
        "state_match": ("exact", "1"),
    },
    {
        "key": "take_off_alert",
        "on": [("9200", "1"), ("9202", "1,0000,2359")],
        "off": [("9202", "0,0000,2359"), ("9200", "1440")],
        "state_code": "9202",
        "state_match": ("prefix", "1,"),
    },
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]

    add(
        SafeFamilyCommandSwitch(coord, device_id, dev, spec)
        for device_id, dev in (coord.data or {}).items()
        for spec in SWITCH_DEFS
    )

    add(
        SafeFamilyCareTimeSwitch(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyCommandSwitch(CoordinatorEntity[SafeFamilyCoordinator], SwitchEntity):
    """Data-driven switch for simple on/off CmdCodes."""

    _attr_has_entity_name = True

    def __init__(self, coord, device_id: int, dev: dict, spec: dict):
        super().__init__(coord)
        self._device_id = device_id
        self._spec = spec
        self._state_code = spec["state_code"]
        self._attr_translation_key = spec["key"]
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_sw_{spec['key']}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    @property
    def _cmd_item(self) -> dict:
        return (self.coordinator.commands.get(self._device_id) or {}).get(
            self._state_code, {}
        )

    def _state_matches(self, raw: str) -> bool:
        mode, value = self._spec["state_match"]
        if mode == "exact":
            return raw == value
        if mode == "prefix":
            return raw.startswith(value)
        return False

    @property
    def is_on(self) -> bool:
        raw = str(self._cmd_item.get("CmdValue", "")).strip()
        return self._state_matches(raw)

    async def _send_all(self, commands: list[tuple[str, str]]) -> None:
        for cmd_code, params in commands:
            await self.coordinator.async_send_command(
                self._device_id, cmd_code, params
            )

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.debug("Turning ON %s: %s", self._spec["key"], self._spec["on"])
        await self._send_all(self._spec["on"])
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.debug("Turning OFF %s: %s", self._spec["key"], self._spec["off"])
        await self._send_all(self._spec["off"])
        await self.coordinator.async_request_refresh()


class SafeFamilyCareTimeSwitch(CoordinatorEntity[SafeFamilyCoordinator], SwitchEntity):
    """Care Time toggle.

    Interval (0003) drives on/off state:
      1440 min (24 h) = OFF
      anything smaller = ON

    When turning on, restores the last non-off interval (via the
    coordinator's ``care_time_interval`` cache), falling back to 25.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "care_time"
    _attr_icon = "mdi:crosshairs-gps"

    INTERVAL_CODE = "0003"
    WINDOW_CODE = "9203"
    OFF_INTERVAL = "1440"
    FALLBACK_INTERVAL = "25"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_sw_care_time"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    def _cmd(self, code: str) -> str:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(code, {})
        return str(item.get("CmdValue") or "").strip()

    @property
    def is_on(self) -> bool:
        raw = self._cmd(self.INTERVAL_CODE)
        return raw not in ("", self.OFF_INTERVAL)

    def _interval_to_restore(self) -> str:
        current = self._cmd(self.INTERVAL_CODE)
        if current and current != self.OFF_INTERVAL:
            return current
        remembered = self.coordinator.care_time_interval.get(self._device_id)
        if remembered:
            return remembered
        return self.FALLBACK_INTERVAL

    async def async_turn_on(self, **kwargs) -> None:
        interval = self._interval_to_restore()
        await self.coordinator.async_send_command(
            self._device_id, self.INTERVAL_CODE, interval
        )
        window = self._cmd(self.WINDOW_CODE)
        if window:
            await self.coordinator.async_send_command(
                self._device_id, self.WINDOW_CODE, window
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_send_command(
            self._device_id, self.INTERVAL_CODE, self.OFF_INTERVAL
        )
        await self.coordinator.async_request_refresh()