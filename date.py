"""Date entity for the birthday field."""
from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyBirthday(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyBirthday(CoordinatorEntity[SafeFamilyCoordinator], DateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "birthday"
    _attr_icon = "mdi:cake-variant"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_date_birthday"
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
    def native_value(self) -> date | None:
        raw = self._profile().get("Birthday")
        if not raw:
            return None
        try:
            return date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None

    async def async_set_value(self, value: date) -> None:
        await self.coordinator.async_save_profile(
            self._device_id, {"Birthday": value.isoformat()}
        )