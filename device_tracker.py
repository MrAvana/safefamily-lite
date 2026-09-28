"""Device tracker for SafeFamily Lite watches."""
from __future__ import annotations

from homeassistant.components.device_tracker import TrackerEntity
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
        SafeFamilyTracker(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyTracker(CoordinatorEntity[SafeFamilyCoordinator], TrackerEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_tracker"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    @property
    def _dev(self) -> dict:
        return (self.coordinator.data or {}).get(self._device_id) or {}

    @property
    def latitude(self):
        return self._dev.get("Latitude")

    @property
    def longitude(self):
        return self._dev.get("Longitude")

    @property
    def extra_state_attributes(self):
        d = self._dev
        return {
            "last_contact": d.get("DeviceUtcTime"),
            "last_heartbeat": d.get("LastCommunication"),
            "position_type": d.get("PositionType"),
            "speed": d.get("Speed"),
            "course": d.get("Course"),
            "battery": d.get("Battery"),
            "signal": d.get("Signal"),
            "satellites": d.get("Satellite"),
            "status": d.get("Status"),
        }