"""Image entities for SafeFamily Lite.

Two entities:
- image.<device>_last_emoji  → most recent emoji sticker received
- image.<device>_last_photo  → most recent camera photo from the watch

The emoji PNGs are bundled inside the integration's assets folder. The
photos come from an external (unauthenticated) file server, and are
fetched on-demand.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import aiohttp
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .chat import emoji_filename, is_emoji_code
from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator

_LOGGER = logging.getLogger(__name__)

EMOJI_DIR = "custom_components/safefamily_lite/assets/emojis"
PHOTO_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=20)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device_id, dev in (coord.data or {}).items():
        entities.append(SafeFamilyLastEmojiImage(coord, hass, device_id, dev))
        entities.append(SafeFamilyLastPhotoImage(coord, hass, device_id, dev))
    add(entities)


class _SafeFamilyImageBase(CoordinatorEntity[SafeFamilyCoordinator], ImageEntity):
    """Shared plumbing for image entities on the watch device."""

    _attr_has_entity_name = True
    _attr_content_type = "image/png"

    def __init__(self, coordinator, hass, device_id: int, dev: dict, translation_key: str):
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._device_id = device_id
        self._attr_translation_key = translation_key
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_image_{translation_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }


class SafeFamilyLastEmojiImage(_SafeFamilyImageBase):
    """Most recently received emoji sticker."""

    def __init__(self, coord, hass, device_id: int, dev: dict):
        super().__init__(coord, hass, device_id, dev, "last_emoji")

    def _last_emoji_item(self) -> dict | None:
        items = (self.coordinator.messages or {}).get(self._device_id, []) or []
        items = sorted(items, key=lambda e: e.get("Created") or "", reverse=True)
        for item in items:
            if is_emoji_code(item.get("Content") or ""):
                return item
        return None

    def _last_emoji_code(self) -> str | None:
        item = self._last_emoji_item()
        return (item.get("Content") or None) if item else None

    def _last_emoji_time(self) -> datetime | None:
        item = self._last_emoji_item()
        if not item:
            return None
        raw = item.get("Created")
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw).replace(" ", "T"))
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed

    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_emoji_time()

    async def async_image(self) -> bytes | None:
        code = self._last_emoji_code()
        if code is None:
            return None
        filename = emoji_filename(code)
        if filename is None:
            return None
        path = Path(self.hass.config.path(EMOJI_DIR)) / filename
        if not path.is_file():
            _LOGGER.warning("Emoji asset missing: %s", path)
            return None
        try:
            return await self.hass.async_add_executor_job(path.read_bytes)
        except OSError as err:
            _LOGGER.warning("Could not read %s: %s", path, err)
            return None

    @property
    def extra_state_attributes(self):
        code = self._last_emoji_code()
        ts = self._last_emoji_time()
        return {
            "emoji_code": code,
            "emoji_received": ts.isoformat() if ts else None,
            "static_path": "/safefamily_lite/emojis",
        }


class SafeFamilyLastPhotoImage(_SafeFamilyImageBase):
    """Most recent camera photo taken by the watch."""

    def __init__(self, coord, hass, device_id: int, dev: dict):
        super().__init__(coord, hass, device_id, dev, "last_photo")

    def _latest_photo(self) -> dict | None:
        items = (self.coordinator.photos or {}).get(self._device_id, []) or []
        if not items:
            return None
        return max(items, key=lambda p: p.get("Created") or "")

    def _latest_photo_time(self) -> datetime | None:
        photo = self._latest_photo()
        if not photo:
            return None
        raw = photo.get("Created")
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw).replace(" ", "T"))
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed

    @property
    def image_last_updated(self) -> datetime | None:
        return self._latest_photo_time()

    async def async_image(self) -> bytes | None:
        photo = self._latest_photo()
        if not photo:
            return None
        url = photo.get("FileName")
        if not url:
            return None
        try:
            async with aiohttp.ClientSession(timeout=PHOTO_FETCH_TIMEOUT) as session:
                async with session.get(url) as r:
                    if r.status != 200:
                        _LOGGER.warning(
                            "Photo fetch %s returned HTTP %s", url, r.status
                        )
                        return None
                    return await r.read()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Photo fetch failed for %s: %s", url, err)
            return None

    @property
    def extra_state_attributes(self):
        photo = self._latest_photo()
        ts = self._latest_photo_time()
        return {
            "photo_url": photo.get("FileName") if photo else None,
            "photo_file_id": photo.get("FileId") if photo else None,
            "photo_taken": ts.isoformat() if ts else None,
            "photo_count": len(
                (self.coordinator.photos or {}).get(self._device_id, []) or []
            ),
        }