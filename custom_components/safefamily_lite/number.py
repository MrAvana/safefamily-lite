"""Number entities for SafeFamily Lite.

Exposes the pedometer goal (CmdCode 1508) as a settable number.

Design note: the SafeFamily API does not return 1508 in its CommandList
response, and the app stores its own copy of the goal in local
SharedPreferences ("STEP_COUNT_APEX"). There is no server-side value to
read, so Home Assistant is treated as the authoritative source. The value
is persisted across HA restarts via RestoreEntity and pushed to the watch
on every change.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CMD_STEP_GOAL, DOMAIN
from .coordinator import SafeFamilyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SafeFamilyCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(
        SafeFamilyStepGoalNumber(coord, device_id, dev)
        for device_id, dev in (coord.data or {}).items()
    )


class SafeFamilyStepGoalNumber(
    CoordinatorEntity[SafeFamilyCoordinator], NumberEntity, RestoreEntity
):
    """Pedometer goal (steps). Writes 1508 with the value in Params."""

    _attr_has_entity_name = True
    _attr_translation_key = "step_goal"
    _attr_icon = "mdi:target"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 500
    _attr_native_max_value = 50000
    _attr_native_step = 500
    _attr_native_unit_of_measurement = "steps"

    def __init__(self, coord, device_id: int, dev: dict):
        super().__init__(coord)
        self._device_id = device_id
        self._cached_value: float | None = None
        label = dev.get("NickName") or dev.get("Name") or f"Watch {device_id}"
        self._attr_unique_id = f"safefamily_{device_id}_num_step_goal"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(device_id))},
            "name": label,
            "manufacturer": "Elari",
            "model": dev.get("Type"),
            "sw_version": dev.get("Protocol"),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            try:
                self._cached_value = float(last.state)
            except (TypeError, ValueError):
                self._cached_value = None

    @property
    def native_value(self) -> float | None:
        return self._cached_value

    async def async_set_native_value(self, value: float) -> None:
        self._cached_value = float(value)
        try:
            await self.coordinator.async_send_command(
                self._device_id, CMD_STEP_GOAL, str(int(value))
            )
        except Exception:
            self.async_write_ha_state()
            raise
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        goal = self._cached_value
        steps_data = (self.coordinator.steps_today or {}).get(self._device_id, {}) or {}
        raw_steps = steps_data.get("Step")
        try:
            current_steps = int(raw_steps) if raw_steps is not None else None
        except (TypeError, ValueError):
            current_steps = None

        progress_pct = None
        if goal and current_steps is not None and goal > 0:
            progress_pct = round(current_steps / goal * 100, 1)

        return {
            "source": "Home Assistant",
            "current_steps": current_steps,
            "progress_percent": progress_pct,
            "goal_reached": bool(
                goal and current_steps is not None and current_steps >= goal
            ),
        }