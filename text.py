"""Text entities for editable SafeFamily Lite profile fields."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator


# translation_key, profile field, max length, read fallbacks
TEXT_FIELDS = [
    ("nickname", "Nickname", 100, []),
    ("cell_phone", "CellPhone", 30, ["Sim"]),
    ("grade", "Grade", 50, []),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyProfileText(coord, device_id, dev, key, field, maxlen, fallbacks)
        for device_id, dev in (coord.data or {}).items()
        for key, field, maxlen, fallbacks in TEXT_FIELDS
    )


class SafeFamilyProfileText(CoordinatorEntity[SafeFamilyCoordinator], TextEntity):
    _attr_has_entity_name = True
    _attr_mode = TextMode.TEXT

    def __init__(self, coord, device_id, dev, key, field, maxlen, fallbacks):
        super().__init__(coord)
        self._device_id = device_id
        self._field = field
        self._fallbacks = fallbacks
        self._attr_translation_key = key
        self._attr_native_max = maxlen
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_text_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    def _profile(self) -> dict:
        return (self.coordinator.profiles or {}).get(self._device_id, {}) or {}

    @property
    def native_value(self) -> str | None:
        p = self._profile()
        raw = p.get(self._field)
        if raw not in (None, ""):
            return str(raw)
        for fb in self._fallbacks:
            v = p.get(fb)
            if v not in (None, ""):
                return str(v)
        return None

    async def async_set_value(self, value: str) -> None:
        updates = {self._field: value}
        if self._field == "CellPhone":
            for fb in self._fallbacks:
                updates[fb] = value
        await self.coordinator.async_save_profile(self._device_id, updates)