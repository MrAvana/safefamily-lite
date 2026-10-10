"""Todo platform for SafeFamily Lite.

Alarms are exposed as read-only sensors (sensor.<device>_alarms and
sensor.<device>_next_alarm). Editing is done via the services
safefamily_lite.add_alarm / delete_alarm / set_alarms.

This platform is intentionally empty but kept registered so existing
installations don't break on upgrade.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    # No entities — see module docstring.
    return