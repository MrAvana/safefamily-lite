"""Connectivity binary sensor — driven by DeviceUtcTime recency."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DEFAULT_OFFLINE_AFTER_MIN, DOMAIN
from .coordinator import SafeFamilyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyOnline(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyOnline(CoordinatorEntity[SafeFamilyCoordinator], BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_translation_key = "online"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_online"
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
    def _last_contact(self):
        raw = self._dev.get("DeviceUtcTime")
        if not raw:
            return None
        parsed = dt_util.parse_datetime(str(raw).replace(" ", "T"))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
        return parsed

    @property
    def is_on(self) -> bool:
        last = self._last_contact
        if last is None:
            return False
        return (dt_util.utcnow() - last) < timedelta(
            minutes=DEFAULT_OFFLINE_AFTER_MIN
        )

    @property
    def extra_state_attributes(self):
        dev = self._dev
        last = self._last_contact
        age_min = None
        if last is not None:
            age_min = round((dt_util.utcnow() - last).total_seconds() / 60, 1)
        status = dev.get("Status")
        position_type = dev.get("PositionType")
        position_label = {1: "GPS", 2: "LBS"}.get(status, f"unknown ({status})")
        return {
            "last_contact": last.isoformat() if last else None,
            "last_contact_age_minutes": age_min,
            "position_type": position_type,
            "position_mode": position_label,
            "status_code": status,
            "last_heartbeat": dev.get("LastCommunication"),
            "offline_after_minutes": DEFAULT_OFFLINE_AFTER_MIN,
        }