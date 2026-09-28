"""Buttons for SafeFamily Lite commands."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .chat import EMOJI_CODES, index_of
from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator

_LOGGER = logging.getLogger(__name__)


BUTTON_DEFS = [
    ("restart", "0010", ButtonDeviceClass.RESTART),
    ("ring", "9018", None),
    ("power_off", "0048", None),
]


# MDI icons that roughly mirror what each sticker looks like.
# Adjust once you see the actual images.
_EMOJI_ICONS = {
    "k01em0": "mdi:emoticon-happy-outline",
    "k01em1": "mdi:emoticon-cool-outline",
    "k01em2": "mdi:emoticon-lol-outline",
    "k01em3": "mdi:emoticon-excited-outline",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]

    add(
        SafeFamilyCommandButton(coord, device_id, dev, key, cmd, dev_class)
        for device_id, dev in (coord.data or {}).items()
        for key, cmd, dev_class in BUTTON_DEFS
    )

    add(
        SafeFamilyRefreshButton(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )

    add(
        SafeFamilyEmojiButton(coord, device_id, dev, code)
        for device_id, dev in (coord.data or {}).items()
        for code in EMOJI_CODES
    )

    add(
        SafeFamilyTakePhotoButton(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyCommandButton(CoordinatorEntity[SafeFamilyCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, device_id: int, dev: dict, key: str, cmd: str, dev_class):
        super().__init__(coord)
        self._device_id = device_id
        self._cmd_code = cmd
        self._attr_translation_key = key
        self._attr_device_class = dev_class
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_btn_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    async def async_press(self) -> None:
        _LOGGER.debug(
            "Sending CmdCode=%s to device %s", self._cmd_code, self._device_id
        )
        await self.coordinator.async_send_command(self._device_id, self._cmd_code)


class SafeFamilyRefreshButton(CoordinatorEntity[SafeFamilyCoordinator], ButtonEntity):
    """Force an immediate re-poll of the API for this integration."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_btn_refresh"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    async def async_press(self) -> None:
        _LOGGER.debug("Manual refresh triggered for device %s", self._device_id)
        await self.coordinator.async_request_refresh()


class SafeFamilyEmojiButton(CoordinatorEntity[SafeFamilyCoordinator], ButtonEntity):
    """Send one of the four built-in watch emoji stickers."""

    _attr_has_entity_name = True

    def __init__(self, coord, device_id: int, dev: dict, code: str):
        super().__init__(coord)
        self._device_id = device_id
        self._code = code
        idx = index_of(code)
        self._attr_translation_key = f"emoji_{idx}"
        self._attr_icon = _EMOJI_ICONS.get(code, "mdi:emoticon-outline")
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_btn_emoji_{idx}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    async def async_press(self) -> None:
        _LOGGER.debug(
            "Sending emoji %s to device %s", self._code, self._device_id
        )
        await self.coordinator.async_send_emoji(self._device_id, self._code)


class SafeFamilyTakePhotoButton(CoordinatorEntity[SafeFamilyCoordinator], ButtonEntity):
    """Trigger the watch camera.

    Sends CmdCode 0031 with the phone number stored in the watch's camera
    config (falls back to the device's MainPhone or Sim field).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "take_photo"
    _attr_icon = "mdi:camera"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_btn_take_photo"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    async def async_press(self) -> None:
        _LOGGER.debug("Take photo triggered for device %s", self._device_id)
        await self.coordinator.async_take_photo(self._device_id)