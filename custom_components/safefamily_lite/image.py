"""Image entities for SafeFamily Lite (local backend).

One entity: the newest photo the local backend holds. The watch camera and
photo upload are the only source, so there is no sticker or photo history.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .local import LocalCoordinator, local_images


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coordinator: LocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(local_images(coordinator, hass))
