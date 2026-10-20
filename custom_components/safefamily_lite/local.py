"""Local backend support for SafeFamily Lite.

This integration was written against the Elari vendor cloud
(`appapi.ru-watch.com`), which no longer answers. The watch itself is happy to
talk to any server, so it can instead be pointed at a private backend that
speaks the watch's own "IW" protocol over plain TCP. That backend is small: it
stores positions, battery and heartbeats and offers an HTTP JSON API:

    GET  /health                     liveness + tunnel reachability
    GET  /state                      current device + position, keyed by IMEI
    GET  /contacts?imei=             the phonebook last written to the watch
    POST /locate?imei=               ask the watch for a real-time fix
    POST /contacts?imei=             replace the watch's phonebook

(The backend also serves /locations history, /interval and /cmd; nothing in
this integration needs them yet.)

Only what that backend can serve is exposed here: the position (device_tracker),
battery and last-contact sensors, the tunnel sensor, the phonebook sensor, and
the locate / refresh / restart buttons, plus services to write the phonebook.
Everything else in this integration (chat, geofences, photos, class mode) needs
the vendor cloud and is untouched by this mode.

The phonebook deserves its own note. It is the watch's call whitelist: with
"Protect from Stranger Calls" on, a number not in it is rejected, so an empty
list means nobody can reach the child. `IWBP83` replaces all 13 entries at once
and nothing can read them back, so the backend keeps the list and re-pushes it
at every login. The sensor here reports that stored copy -- what was last
written, not an observation of the watch, which is not possible.

Two deliberate omissions, both because the firmware makes them up: the heartbeat
"signal" and "satellite" counts are hardcoded constants on this hardware, so
they are not published as if they were measurements.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
from .numbers import explain, normalize, number_forms

_LOGGER = logging.getLogger(__name__)

# The watch's own GPS frame. Unlike every other uplink its payload is not
# comma-separated, so it is recognised by prefix rather than by parsing. A row
# carrying one has no `source` (nothing resolved it -- the watch measured it) and
# no `accuracy` (the frame has no HDOP), which is exactly why the two would
# otherwise fall back to the raw frame text and to 0.
GPS_RAW_PREFIX = "IWAP01"

# What to report as accuracy for that frame. Home Assistant cannot render a
# tracker's accuracy as unknown -- `location_accuracy` feeds zone matching and
# the UI -- and this integration maps a missing value to 0. Zero is the one
# answer the data rules out, because it claims the fix is exact. So report a
# nominal figure and leave the honest value (`accuracy_m: None`) alongside it in
# the attributes. The number is measured rather than picked: over one break,
# consecutive fixes 106 s and 194 s apart moved 15 m and 4 m, i.e. the watch
# scatters by roughly 5-15 m on a clear fix.
GPS_ACCURACY_M = 10

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


class LocalApiError(Exception):
    """The local backend could not be reached or answered with an error.

    `refusal` separates the two cases that look alike in a log: the backend
    understood the request and said no -- a phonebook that would drop a
    protected number, a number that is not listed -- which is the caller's
    mistake, from a backend that is down or broken, which is not. The service
    layer turns the first into a validation error and the second into a plain
    failure, so an automation's log says which one happened.
    """

    def __init__(self, message: str, refusal: bool = False) -> None:
        super().__init__(message)
        self.refusal = refusal


class LocalApi:
    """Thin client for the private backend's JSON API.

    Every call takes the session from the caller so the coordinator owns the
    connection pool, and every call is bounded by REQUEST_TIMEOUT: a backend on
    the LAN that stops answering must not hang the integration.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def _request(
        self, session: aiohttp.ClientSession, method: str, path: str,
        json_body=None, **params,
    ) -> dict:
        url = f"{self.base_url}{path}"
        try:
            async with session.request(
                method, url, params=params, json=json_body, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    body = (await resp.text())[:200]
                    raise LocalApiError(
                        f"{path} -> HTTP {resp.status}: {body}",
                        400 <= resp.status < 500,
                    )
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

    async def health_detail(self, session: aiohttp.ClientSession) -> dict:
        """The whole /health payload, so the tunnel block can be read from it."""
        return await self._request(session, "GET", "/health")

    async def state(self, session: aiohttp.ClientSession) -> dict:
        return await self._request(session, "GET", "/state")

    async def contacts(self, session: aiohttp.ClientSession, imei: str) -> dict:
        """The phonebook the backend last wrote, plus when and its guard list."""
        return await self._request(session, "GET", "/contacts", imei=imei)

    async def set_contacts(
        self, session: aiohttp.ClientSession, imei: str, contacts: list[dict]
    ) -> dict:
        """Replace the whole phonebook. A refused list comes back as 409."""
        return await self._request(
            session, "POST", "/contacts", json_body={"contacts": contacts}, imei=imei
        )

    async def locate(self, session: aiohttp.ClientSession, imei: str) -> dict:
        return await self._request(session, "POST", "/locate", imei=imei)

    async def reboot(self, session: aiohttp.ClientSession, imei: str) -> dict:
        return await self._request(session, "POST", "/reboot", imei=imei)


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
        # None means "the backend did not tell us", which is what an older
        # backend without the tunnel block returns. Kept separate from a
        # reported-down tunnel so the sensor can say unknown instead of lying.
        self.tunnel: dict | None = None

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            state = await self.api.state(self._session)
        except LocalApiError as err:
            raise UpdateFailed(f"local backend unavailable: {err}") from err

        # Best-effort and deliberately forgiving: a backend too old to answer
        # /health with a tunnel block must not fail the whole update, or every
        # entity would go unavailable over a field nothing else depends on.
        try:
            health = await self.api.health_detail(self._session)
        except LocalApiError:
            health = None
        self.tunnel = (health or {}).get("tunnel")

        devices: dict[str, dict] = {}
        for imei, payload in (state or {}).items():
            if isinstance(payload, dict) and payload:
                flat = self._flatten(imei, payload)
                # Best effort, per watch: the phonebook lives at its own URL
                # and a backend too old to serve it must not take the tracker
                # down with it. None means "not known", which the sensor shows
                # as unknown rather than as an empty -- and empty is the state
                # worth alarming on, so the two must not be conflated.
                try:
                    info = await self.api.contacts(self._session, imei)
                except LocalApiError:
                    info = None
                flat["contacts"] = (info or {}).get("contacts") if info else None
                flat["contacts_pushed_at"] = (info or {}).get("pushed_at")
                flat["contacts_required"] = (info or {}).get("required") or []
                devices[imei] = flat

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

        # Which fix to show. The backend has already decided which fix is *the*
        # device position -- it refuses to let a kilometre-scale tower fix
        # outrank a recent GPS one -- and stores that decision as the newest
        # location row. So show that one.
        #
        # Taking the newer of `location` and `lbs` instead (which this did) undoes
        # the decision: `lbs` is the tower *report*, refreshed on every cell
        # frame, so the tracker stepped back onto the coarse cell fix seconds
        # after a street-accurate GPS row had arrived. `lbs` is now only a
        # fallback for before any position has been published at all.
        fix = next((c for c in (location, lbs) if c.get("lat") is not None), {})
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
            "source": _fix_source(fix),
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

    async def async_reboot(self, imei: str) -> None:
        """Reboot the watch.

        It acknowledges straight away, then the session drops and it logs
        back in about a minute later, so the entry goes briefly unavailable.
        Handy when the watch's session has wedged and stopped reporting.
        """
        await self.api.reboot(self._session, imei)
        _LOGGER.debug("Reboot requested for %s", imei)

    async def async_set_contacts(self, imei: str, contacts: list[dict]) -> dict:
        """Write a whole phonebook, then re-read so the sensor is honest.

        The backend refuses a list that drops a number it is configured to
        protect, and that refusal travels back as a `LocalApiError` -- which is
        what the caller should see, rather than a silent no-op.
        """
        result = await self.api.set_contacts(self._session, imei, contacts)
        await self.async_request_refresh()
        return result

    async def async_add_contact(
        self, imei: str, name: str, number: str, icon: int = 0, sos: bool = False
    ) -> dict:
        """Add one contact, storing every presentation of the number.

        `IWBP83` replaces all 13 slots, so "add" is read-modify-write: take the
        list the backend last wrote, put the pair where the contact already
        was, and push the result. Editing the stored copy is the only option
        because the watch cannot be asked what it currently holds.

        Both presentations are stored because the watch compares the calling
        number as a string: a subscriber saved only as `+261340000000` does not
        ring when the network presents `0340000000`. Only the international
        form carries the SOS flag, so the button dials one number rather than
        the same person twice.

        The number is validated against Home Assistant's own country setting
        before anything is written. A number that cannot be a real subscriber
        is refused rather than stored: an entry that will never ring looks
        exactly like success.
        """
        region = self.hass.config.country
        forms = number_forms(number, region)
        if not forms:
            raise LocalApiError(explain(number, region), refusal=True)

        info = await self.api.contacts(self._session, imei)
        contacts = list(info.get("contacts") or [])
        wanted = {_number_key(form) for form in forms}

        entries = [
            {
                "name": name,
                "number": form,
                "icon": int(icon),
                "is_sos": bool(sos) and index == 0,
            }
            for index, form in enumerate(forms)
        ]

        def key(contact: dict) -> str:
            return _number_key(contact.get("number") or "")

        # Replace in place rather than append, so editing a number does not
        # shuffle the order the child sees on the watch. A contact stored in
        # only one presentation is matched as well, so it becomes a pair here
        # rather than gaining a duplicate elsewhere in the list.
        kept = [contact for contact in contacts if key(contact) not in wanted]
        first = next(
            (index for index, contact in enumerate(contacts) if key(contact) in wanted),
            None,
        )
        if first is None:
            contacts = kept + entries
        else:
            cut = sum(1 for contact in contacts[:first] if key(contact) not in wanted)
            contacts = kept[:cut] + entries + kept[cut:]

        return await self.async_set_contacts(imei, _heal_forms(contacts, region))

    async def async_remove_contact(self, imei: str, number: str) -> dict:
        """Drop every presentation of `number`, then push what is left.

        Removal is read-modify-write for the same reason adding is: `IWBP83`
        replaces all 13 slots, so the only way to take something out is to
        write the rest back. Matching spans all presentations, so removing
        `+261340000000` also takes out `0340000000`: leaving one behind would
        keep the number ringing while the list claimed it was gone.

        A number that matches nothing raises `LocalApiError` rather than
        reporting success, because a typo must not look like a removal that
        worked. Nothing here is validated: removal has to work on whatever is
        already stored, including a number that would be refused today.
        """
        region = self.hass.config.country
        forms = number_forms(number, region) or [normalize(number)]
        info = await self.api.contacts(self._session, imei)
        contacts = list(info.get("contacts") or [])
        wanted = {_number_key(form) for form in forms}
        kept = [
            contact
            for contact in contacts
            if _number_key(contact.get("number") or "") not in wanted
        ]
        if len(kept) == len(contacts):
            raise LocalApiError(f"{number} is not in the phonebook", refusal=True)
        return await self.async_set_contacts(imei, _heal_forms(kept, region))


def _number_key(number: str) -> str:
    """Compare numbers ignoring `+` and the characters a screen adds.

    `+261340000000` and `261340000000` are the same subscriber, and the same
    number can arrive in either form depending on how a call is routed.
    """
    return normalize(number).replace("+", "")


def _heal_forms(contacts: list[dict], region: str | None) -> list[dict]:
    """Fill in the presentation(s) a stored entry is missing.

    The watch cannot be read back, so the stored copy is the only evidence of
    what the child can actually receive. An entry written before this expansion
    existed -- or pushed raw through `set_local_contacts` -- may carry one form
    only, and that is a silent hole: her calls ring in one presentation and not
    the other. Every write therefore re-derives the full set.

    An entry that no longer validates is kept exactly as typed. A repair pass
    must never be the reason a number leaves the whitelist: the parser not
    knowing a number is not the same as the person being gone.

    Entries stay in place, so the order on the watch does not change.
    Duplicates already in the list collapse, and only the international form
    keeps an SOS flag.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for contact in contacts:
        stored = contact.get("number") or ""
        forms = number_forms(stored, region) or [normalize(stored)]
        for index, form in enumerate(forms):
            key = _number_key(form)
            if key in seen:
                continue
            seen.add(key)
            copy = dict(contact)
            copy["number"] = form
            if index:
                copy["is_sos"] = False
            out.append(copy)
    return out


def _fix_source(fix: dict) -> str | None:
    """How a fix was obtained, in a form the UI can read.

    A resolved tower fix carries its provenance in `source` (`unwired`,
    `unwired+cache`, ...). A GPS row carries none, because nothing resolved it:
    the watch measured the position itself. Falling back to `raw` there would put
    an entire 75-character frame into the attribute, so name the case instead.
    """
    if fix.get("source"):
        return fix["source"]
    if str(fix.get("raw") or "").startswith(GPS_RAW_PREFIX):
        return "gps"
    return fix.get("raw") or None


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
        """Accuracy in metres, nominal for the watch's own GPS.

        Tower fixes carry a real figure from the resolver and are passed
        through. A GPS row cannot: the frame has no HDOP, so the backend stores
        nothing and 0 would claim an exact fix -- hence `GPS_ACCURACY_M`.
        """
        acc = self._dev.get("accuracy")
        if acc:
            return int(acc)
        if self._dev.get("source") == "gps":
            return GPS_ACCURACY_M
        return 0

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


class LocalContactsSensor(_LocalEntity, SensorEntity):
    """The phonebook the backend last wrote to the watch.

    This is the call whitelist. It reports the backend's stored copy -- there is
    no read-back from the device -- but the number of entries is the thing that
    matters at a glance, because an empty list is what silently turns every
    caller into a stranger when "Protect from Stranger Calls" is on.

    `None` (a backend that cannot be asked) is kept distinct from `0`, so
    "unknown" never reads as "nobody can call her".
    """

    _attr_translation_key = "contacts"
    _attr_icon = "mdi:phone-book"

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "contacts")

    @property
    def native_value(self):
        contacts = self._dev.get("contacts")
        return None if contacts is None else len(contacts)

    @property
    def extra_state_attributes(self):
        contacts = self._dev.get("contacts")
        required = self._dev.get("contacts_required") or []
        have = {_number_key(c.get("number") or "") for c in contacts or []}
        return {
            "contacts": contacts,
            "pushed_at": self._dev.get("contacts_pushed_at"),
            # The backend refuses a write that drops one of these, so this is
            # belt and braces -- but it is the state worth alarming on.
            "guardian_numbers": required,
            "guardian_present": (
                all(_number_key(n) in have for n in required)
                if required and contacts is not None else None
            ),
        }


class LocalOnlineSensor(_LocalEntity, SensorEntity):
    _attr_translation_key = "backend_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["online", "offline"]

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "online")

    @property
    def native_value(self):
        return "online" if self._dev.get("online") else "offline"


class LocalTunnelBinarySensor(_LocalEntity, BinarySensorEntity):
    """Whether the watch is reachable from outside, not just from the LAN.

    The watch talks to the backend over a public bore.pub tunnel, so the LAN
    API can answer perfectly while nothing from the watch arrives. The backend
    measures this by round-tripping a login frame through the relay; an open
    public port would be a false positive, because a half-open tunnel still
    accepts connections and then forwards nothing.
    """

    _attr_translation_key = "tunnel"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "tunnel")

    @property
    def _tunnel(self) -> dict | None:
        return self.coordinator.tunnel

    @property
    def available(self) -> bool:
        # Unknown is not the same as down: a backend that cannot be asked
        # about the tunnel must not read as "the watch is unreachable".
        return super().available and self._tunnel is not None

    @property
    def is_on(self):
        tunnel = self._tunnel
        if not tunnel:
            return None
        return bool(tunnel.get("ok"))

    @property
    def extra_state_attributes(self):
        tunnel = self._tunnel or {}
        return {
            "last_probe": tunnel.get("last_probe"),
            "age_s": tunnel.get("age_s"),
            "probe_every_s": tunnel.get("probe_every_s"),
            "stale_after_s": tunnel.get("stale_after_s"),
        }


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


class LocalRebootButton(_LocalEntity, ButtonEntity):
    """Reboot the watch over its own protocol session.

    Reuses the vendor button's translation key on purpose: "Restart" is
    already the established wording for this action, and it means local mode
    needs no new strings.
    """

    _attr_translation_key = "restart"
    _attr_icon = "mdi:restart"

    def __init__(self, coord: LocalCoordinator, imei: str) -> None:
        super().__init__(coord, imei, "btn_reboot")

    async def async_press(self) -> None:
        await self.coordinator.async_reboot(self._imei)
        await self.coordinator.async_request_refresh()


def local_trackers(coord: LocalCoordinator) -> list[LocalTracker]:
    return [LocalTracker(coord, imei) for imei in (coord.data or {})]


def local_sensors(coord: LocalCoordinator) -> list[SensorEntity]:
    return [
        entity(coord, imei)
        for imei in (coord.data or {})
        for entity in (LocalBatterySensor, LocalLastContactSensor,
                       LocalContactsSensor, LocalOnlineSensor)
    ]


def local_binary_sensors(coord: LocalCoordinator) -> list[BinarySensorEntity]:
    return [LocalTunnelBinarySensor(coord, imei) for imei in (coord.data or {})]


def local_buttons(coord: LocalCoordinator) -> list[ButtonEntity]:
    return [
        entity(coord, imei)
        for imei in (coord.data or {})
        for entity in (LocalLocateButton, LocalRefreshButton, LocalRebootButton)
    ]
