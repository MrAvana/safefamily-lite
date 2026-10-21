"""Binary sensors for SafeFamily Lite (local backend)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .local import LocalCoordinator, local_binary_sensors


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coordinator: LocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(local_binary_sensors(coordinator))
