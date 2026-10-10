"""Geo-location entities for SafeFamily Lite fences."""
from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
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
    existing: set = getattr(coord, "_fence_entities", set())

    def _sync() -> None:
        new = []
        for device_id, fences in (coord.geofences or {}).items():
            for fence in fences:
                fid = fence.get("FenceId")
                if fid is None:
                    continue
                key = (device_id, fid)
                if key in existing:
                    continue
                existing.add(key)
                new.append(SafeFamilyFence(coord, device_id, fence))
        if new:
            add(new)
        coord._fence_entities = existing

    _sync()
    entry.async_on_unload(coord.async_add_listener(_sync))


class SafeFamilyFence(CoordinatorEntity[SafeFamilyCoordinator], GeolocationEvent):
    _attr_icon = "mdi:map-marker-radius"
    _attr_source = DOMAIN

    def __init__(self, coord, device_id: int, fence: dict):
        super().__init__(coord)
        self._device_id = device_id
        self._fence_id = fence.get("FenceId")
        self._attr_unique_id = f"safefamily_{device_id}_fence_{self._fence_id}"
        self._attr_name = fence.get("FenceName") or f"Fence {self._fence_id}"

    @property
    def _fence(self) -> dict:
        fences = (self.coordinator.geofences or {}).get(self._device_id, []) or []
        return next(
            (f for f in fences if f.get("FenceId") == self._fence_id), {}
        )

    @property
    def latitude(self) -> float | None:
        lat = self._fence.get("Latitude")
        try:
            return float(lat) if lat is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def longitude(self) -> float | None:
        lng = self._fence.get("Longitude")
        try:
            return float(lng) if lng is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        f = self._fence
        return {
            "radius_m": f.get("Radius"),
            "address": f.get("Address"),
            "fence_type": f.get("FenceType"),
            "alarm_type": f.get("AlarmType"),
            "in_use": f.get("InUse"),
            "is_device_fence": f.get("IsDeviceFence"),
        }