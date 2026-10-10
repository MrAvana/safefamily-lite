"""Select entities for enum fields and Care Time tracking mode."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SafeFamilyCoordinator


GENDER_OPTIONS = ["Unknown", "Male", "Female"]
GENDER_TO_INT = {"Unknown": 0, "Male": 1, "Female": 2}
INT_TO_GENDER = {0: "Unknown", 1: "Male", 2: "Female"}

CARE_TIME_OPTIONS = ["1", "5", "15", "20", "25", "30", "45", "60", "120"]
CARE_TIME_CODE = "0003"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyGender(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )
    add(
        SafeFamilyCareTimeMode(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyGender(CoordinatorEntity[SafeFamilyCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "gender"
    _attr_icon = "mdi:gender-male-female"
    _attr_options = GENDER_OPTIONS

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_select_gender"
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
    def current_option(self) -> str | None:
        raw = self._profile().get("Gender")
        try:
            return INT_TO_GENDER.get(int(raw), "Unknown")
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        int_val = GENDER_TO_INT.get(option)
        if int_val is None:
            return
        await self.coordinator.async_save_profile(
            self._device_id, {"Gender": int_val}
        )


class SafeFamilyCareTimeMode(CoordinatorEntity[SafeFamilyCoordinator], SelectEntity):
    """Care Time tracking mode (0003 interval)."""

    _attr_has_entity_name = True
    _attr_translation_key = "care_time_mode"
    _attr_icon = "mdi:update"
    _attr_options = CARE_TIME_OPTIONS

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_select_care_time_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    def _current_interval(self) -> str:
        item = (self.coordinator.commands.get(self._device_id) or {}).get(
            CARE_TIME_CODE, {}
        )
        return str(item.get("CmdValue") or "").strip()

    @property
    def current_option(self) -> str | None:
        current = self._current_interval()
        if current in CARE_TIME_OPTIONS:
            return current
        remembered = self.coordinator.care_time_interval.get(self._device_id)
        if remembered in CARE_TIME_OPTIONS:
            return remembered
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in CARE_TIME_OPTIONS:
            return
        await self.coordinator.async_send_command(
            self._device_id, CARE_TIME_CODE, option
        )
        await self.coordinator.async_request_refresh()