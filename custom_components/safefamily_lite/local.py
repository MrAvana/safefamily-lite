"""Local backend support for SafeFamily Lite.

This integration was written against the Elari vendor cloud
(`appapi.ru-watch.com`), which no longer answers. The watch itself is happy to
talk to any server, so it can instead be pointed at a private backend that
speaks the watch's own "IW" protocol over plain TCP. That backend is small: it
stores positions, battery and heartbeats and offers an HTTP JSON API:

    GET  /health                     liveness
    GET  /state                      current device + position, keyed by IMEI
    POST /locate?imei=               ask the watch for a real-time fix

(The backend also serves /locations history, /interval and /cmd; nothing in
this integration needs them yet.)

Only what that backend can serve is exposed here: the position (device_tracker),
battery and last-contact sensors, and the locate / refresh buttons. Everything
else in this integration (chat, contacts, geofences, photos, class mode) needs
the vendor cloud and is untouched by this mode.

Two deliberate omissions, both because the firmware makes them up: the heartbeat
"signal" and "satellite" counts are hardcoded constants on this hardware, so
they are not published as if they were measurements.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.components.button import ButtonEntity
from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_LOCAL_NAME,
    CONF_LOCAL_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_LOCAL_SCAN_INTERVAL,
    DOMAIN,
    LOCAL_OFFLINE_AFTER_MIN,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


class LocalApiError(Exception):
    """The local backend could not be reached or answered with an error."""


class LocalApi:
    """Thin client for the private backend's JSON API.

    Every call takes the session from the caller so the coordinator owns the
    connection pool, and every call is bounded by REQUEST_TIMEOUT: a backend on
    the LAN that stops answering must not hang the integration.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _request(
        self, session: aiohttp.ClientSession, method: str, path: str, **params
    ) -> dict:
        url = f"{self.base_url}{path}"
        try:
            async with session.request(
                method, url, params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    body = (await resp.text())[:200]
                    raise LocalApiError(f"{path} -> HTTP {resp.status}: {body}")
                return await resp.json(content_type=None)
        except LocalApiError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise LocalApiError(f"{path} failed: {err}") from err

    async def health(self, session: aiohttp.ClientSession) -> bool:
        try:
            await self._request(session, "GET", "/health")
            return True
        except LocalApiError:
            return False

    async def state(self, session: aiohttp.ClientSession) -> dict:
        return await self._request(session, "GET", "/state")

    async def locate(self, session: aiohttp.ClientSession, imei: str) -> dict:
        return await self._request(session, "POST", "/locate", imei=imei)


class LocalCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Polls the private backend and caches one dict per watch, keyed by IMEI."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        # Options win over data: the options flow is where a URL gets corrected,
        # and changing it reloads the entry.
        self.url = (
            entry.options.get(CONF_LOCAL_URL) or entry.data[CONF_LOCAL_URL]
        ).rstrip("/")
        self.name_hint = (
            entry.options.get(CONF_LOCAL_NAME)
            or entry.data.get(CONF_LOCAL_NAME)
            or ""
        )
        self.api = LocalApi(self.url)
        scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_LOCAL_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan),
        )
        # Home Assistant's shared session: no connection pool churn every poll.
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            state = await self.api.state(self._session)
        except LocalApiError as err:
            raise UpdateFailed(f"local backend unavailable: {err}") from err

        devices: dict[str, dict] = {}
        for imei, payload in (state or {}).items():
            if isinstance(payload, dict) and payload:
                devices[imei] = self._flatten(imei, payload)

        if not devices:
            # Nothing has logged in yet. Failing setup makes Home Assistant
            # retry, so the entities appear by themselves once the watch
            # connects instead of leaving an empty integration behind.
            raise UpdateFailed("no watches have reported to the backend yet")

        return devices

    def _flatten(self, imei: str, payload: dict) -> dict:
        """Turn the nested /state payload into one flat dict per watch."""
        device = payload.get("device") or {}
        location = payload.get("location") or {}
        lbs = payload.get("lbs") or {}

        # Whichever of the two has a position *and* the newest timestamp wins: a
        # freshly resolved tower fix beats a slightly older published one.
        candidates = [c for c in (location, lbs) if c.get("lat") is not None]
        fix = max(candidates, key=lambda c: _parse_ts(c.get("ts")), default={})
        lat = fix.get("lat")
        lon = fix.get("lon")

        # The watch holds one long-lived TCP session and logs in once, so
        # last_seen is useless for "online". Its heartbeats every ~5 minutes are
        # the honest sign of life, and the backend stamps those as `updated`.
        stamps = [
            device.get("updated"),
            device.get("last_seen"),
            lbs.get("ts"),
            location.get("ts"),
        ]
        last_contact = max(
            (s for s in stamps if s), key=_parse_ts, default=None
        )
        online = False
        if last_contact:
            age = datetime.now(timezone.utc) - _parse_ts(last_contact)
            online = age < timedelta(minutes=LOCAL_OFFLINE_AFTER_MIN)

        name = self.name_hint or f"Watch {imei}"
        return {
            "imei": imei,
            "name": name,
            "lat": lat,
            "lon": lon,
            "accuracy": fix.get("accuracy"),
            "source": fix.get("source") or fix.get("raw"),
            "fix_ts": fix.get("ts"),
            "speed": fix.get("speed"),
            "course": fix.get("course"),
            "battery": device.get("battery"),
            "firmware": device.get("firmware"),
            "last_seen": device.get("last_seen"),
            "last_contact": last_contact,
            "online": online,
        }

    def device_info(self, imei: str) -> dict:
        data = (self.data or {}).get(imei) or {}
        return {
            "identifiers": {(DOMAIN, str(imei))},
            "name": data.get("name") or f"Watch {imei}",
            "manufacturer": "Elari",
            "sw_version": data.get("firmware") or None,
        }

    async def async_locate(self, imei: str) -> None:
        """Ask the watch for a real-time fix; the next poll picks it up."""
        await self.api.locate(self._session, imei)
        _LOGGER.debug("Real-time locate requested for %s", imei)


def _parse_ts(value: str) -> datetime:
    """Parse a backend timestamp; unparseable values sort last."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class _LocalEntity(CoordinatorEntity[LocalCoordinator]):
    """Shared plumbing: identity, naming and device registry wiring."""

    _attr_has_entity_name = True

    def __init__(self, coord: LocalCoordinator, imei: str, key: str) -> None:
        super().__init__(coord)
        self._imei = imei
        self._attr_unique_id = f"safefamily_{imei}_{key}"
        self._attr_device_info = coord.device_info(imei)

    @property
    def _dev(self) -> dict:
        return (self.coordinator.data or {}).get(self._imei) or {}


class LocalTracker(_LocalEntity, TrackerEntity):
    """The watch position, from the backend's newest fix."""

    _attr_name = None

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "tracker")

    @property
    def latitude(self):
        return self._dev.get("lat")

    @property
    def longitude(self):
        return self._dev.get("lon")

    @property
    def location_accuracy(self):
        acc = self._dev.get("accuracy")
        return int(acc) if acc else 0

    @property
    def extra_state_attributes(self):
        d = self._dev
        return {
            # "unwired" / "gps" / "unwired+cache": how the fix was obtained, so a
            # 5 km tower fix is never mistaken for a street-level one.
            "source": d.get("source"),
            "position_type": d.get("source"),
            "accuracy_m": d.get("accuracy"),
            "fix_time": d.get("fix_ts"),
            "last_contact": d.get("last_contact"),
            "battery": d.get("battery"),
            "online": d.get("online"),
            "firmware": d.get("firmware"),
            "imei": d.get("imei"),
        }


class LocalBatterySensor(_LocalEntity, SensorEntity):
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "battery")

    @property
    def native_value(self):
        return self._dev.get("battery")


class LocalLastContactSensor(_LocalEntity, SensorEntity):
    """Newest sign of life, so automations can tell a deaf watch from an idle one."""

    _attr_translation_key = "last_contact"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "last_contact")

    @property
    def native_value(self):
        value = self._dev.get("last_contact")
        if not value:
            return None
        parsed = _parse_ts(value)
        return None if parsed.year == 1 else parsed


class LocalOnlineSensor(_LocalEntity, SensorEntity):
    _attr_translation_key = "backend_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["online", "offline"]

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "online")

    @property
    def native_value(self):
        return "online" if self._dev.get("online") else "offline"


class LocalLocateButton(_LocalEntity, ButtonEntity):
    """Ask the watch for a real-time fix right now."""

    _attr_translation_key = "locate"
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "btn_locate")

    async def async_press(self) -> None:
        await self.coordinator.async_locate(self._imei)
        await self.coordinator.async_request_refresh()


class LocalRefreshButton(_LocalEntity, ButtonEntity):
    """Re-poll the backend without waiting for the next interval."""

    _attr_translation_key = "backend_refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "btn_refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


def local_trackers(coord: LocalCoordinator) -> list[LocalTracker]:
    return [LocalTracker(coord, imei) for imei in (coord.data or {})]


def local_sensors(coord: LocalCoordinator) -> list[SensorEntity]:
    return [
        entity(coord, imei)
        for imei in (coord.data or {})
        for entity in (LocalBatterySensor, LocalLastContactSensor, LocalOnlineSensor)
    ]


def local_buttons(coord: LocalCoordinator) -> list[ButtonEntity]:
    return [
        entity(coord, imei)
        for imei in (coord.data or {})
        for entity in (LocalLocateButton, LocalRefreshButton)
    ]
