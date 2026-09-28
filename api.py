"""SafeFamily Lite API client (reverse-engineered)."""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta

import aiohttp

from .const import (
    API_KEY,
    APEX_APP_ID,
    DEVICE_BASE,
    ECP_BASE,
    PKG_NAME,
    PKG_VERSION,
    REGIONS,
    SIGNING_SECRET,
)

_LOGGER = logging.getLogger(__name__)


class SafeFamilyAuthError(Exception):
    """Auth failure (bad creds or expired token)."""


class SafeFamilyCommandTimeout(Exception):
    """Command accepted by the server but the watch did not acknowledge."""


class SafeFamilyApi:
    """Minimal client for the Elari / ru-watch backend."""

    def __init__(self, username: str, password: str, region: str) -> None:
        self.username = username
        self.password = password
        self.login_base = REGIONS[region]
        self.access_token: str | None = None
        self.token_expires_at: float = 0.0
        self.user_id: int | None = None
        self.lang = "en-US"
        self.timezone = self._build_timezone()

    @staticmethod
    def _build_timezone() -> str:
        now = datetime.now().astimezone()
        iana = getattr(now.tzinfo, "key", None) or now.tzname() or "UTC"
        offset = now.utcoffset() or timedelta(0)
        total_min = int(offset.total_seconds() // 60)
        sign = "+" if total_min >= 0 else "-"
        hh, mm = divmod(abs(total_min), 60)
        return f"{iana}(GMT{sign}{hh:02d}:{mm:02d})"

    @staticmethod
    def _authkey(authtime_ms: int) -> str:
        raw = SIGNING_SECRET + APEX_APP_ID + str(authtime_ms)
        return hashlib.md5(raw.encode()).hexdigest().upper()

    def _headers(self, token: str | None = None) -> dict[str, str]:
        authtime = int(time.time() * 1000)
        h: dict[str, str] = {
            "authtime": str(authtime),
            "authkey": self._authkey(authtime),
            "content-type": "application/json; charset=UTF-8",
            "accept": "application/json",
            "user-agent": "okhttp/4.10.0",
        }
        if token:
            h["token"] = token
        return h

    async def _post_json(
        self, session: aiohttp.ClientSession, url: str, body: dict
    ) -> dict:
        async with session.post(
            url, json=body, headers=self._headers(self.access_token)
        ) as r:
            if r.status in (401, 403):
                self.access_token = None
                self.token_expires_at = 0.0
                raise SafeFamilyAuthError(f"{url} rejected: {r.status}")
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")
            return await r.json()

    async def login(self, session: aiohttp.ClientSession) -> None:
        url = self.login_base + "eap/login"
        payload = {
            "ApiKey": API_KEY,
            "lang": self.lang,
            "login": self.username,
            "packageName": PKG_NAME,
            "packageVersion": PKG_VERSION,
            "pass": self.password,
            "pushId": "",
            "timezone": self.timezone,
        }
        async with session.post(url, json=payload, headers=self._headers()) as r:
            text = await r.text()
            if r.status != 200:
                raise SafeFamilyAuthError(f"HTTP {r.status}: {text[:200]}")
            data = await r.json()

        if data.get("error") not in (0, None):
            raise SafeFamilyAuthError(
                f"{data.get('error_text', 'login failed')}: {data.get('fields', [])}"
            )

        gz = (data.get("data") or {}).get("gz") or {}
        self.access_token = gz.get("AccessToken")
        self.user_id = (gz.get("Item") or {}).get("UserId")
        if not self.access_token or not self.user_id:
            raise SafeFamilyAuthError(
                f"login ok but missing token/userId: keys={list(gz.keys())}"
            )
        self.token_expires_at = time.time() + 30 * 24 * 3600 - 3600
        _LOGGER.debug("SafeFamily login OK user_id=%s", self.user_id)

    async def _ensure_token(self, session: aiohttp.ClientSession) -> None:
        if not self.access_token or time.time() >= self.token_expires_at:
            await self.login(session)

    async def person_device_list(
        self, session: aiohttp.ClientSession
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Device/PersonDeviceList"
        body = {
            "AppId": APEX_APP_ID,
            "Language": self.lang,
            "MapType": "google",
            "TimeOffset": 0.0,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def command_list(
        self, session: aiohttp.ClientSession, device_id: int
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Command/CommandList"
        body = {
            "DeviceId": device_id,
            "IsNewCmdFormat": 1,
            "Language": self.lang,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def send_command(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        device_model: str,
        cmd_code: str,
        params: str = "",
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Command/SendCommand"
        body = {
            "AppId": APEX_APP_ID,
            "CmdCode": cmd_code,
            "DeviceId": device_id,
            "DeviceModel": str(device_model),
            "IsNewCmdFormat": 1,
            "Language": self.lang,
            "Params": params,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        state = data.get("State")
        if state == 1801:
            raise SafeFamilyCommandTimeout(
                f"send timeout: {data.get('Message', '')}"
            )
        if state != 0:
            raise RuntimeError(f"command failed: {data.get('Message', data)}")
        return data

    async def get_person_profile(
        self, session: aiohttp.ClientSession, device_id: int
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Person/GetPersonProfile"
        body = {"DeviceId": device_id, "UserId": self.user_id}
        data = await self._post_json(session, url, body)
        return data.get("Item") or {}

    async def save_person_profile(
        self, session: aiohttp.ClientSession, device_id: int, item: dict
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Person/SavePersonProfile"
        body = {
            "AppId": APEX_APP_ID,
            "Item": item,
            "error": False,
            "Language": self.lang,
            "State": -1,
        }
        data = await self._post_json(session, url, body)
        if data.get("State") != 0:
            raise RuntimeError(f"save profile failed: {data.get('Message', data)}")
        return data

    async def geofence_list(
        self, session: aiohttp.ClientSession, device_id: int
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Geofence/GeofenceList"
        body = {
            "AppId": APEX_APP_ID,
            "DeviceId": device_id,
            "Language": self.lang,
            "MapType": "google",
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def geofence_create(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        *,
        name: str,
        latitude: float,
        longitude: float,
        radius: int,
        address: str = "",
        alarm_type: int = 1,
        fence_type: int = 1,
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Geofence/CreateGeofence"
        body = {
            "AppId": APEX_APP_ID,
            "Language": self.lang,
            "MapType": "google",
            "Item": {
                "DeviceId": device_id,
                "FenceName": name,
                "FenceType": fence_type,
                "Latitude": str(latitude),
                "Longitude": str(longitude),
                "Radius": int(radius),
                "Address": address,
                "AlarmType": alarm_type,
                "InUse": False,
                "IsDeviceFence": False,
                "StartTime": "",
                "EndTime": "",
            },
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(f"geofence create failed: {data.get('Message', data)}")
        return data

    async def geofence_edit(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        fence: dict,
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Geofence/EditGeofence"
        body = {
            "AppId": APEX_APP_ID,
            "Language": self.lang,
            "MapType": "google",
            "Item": {
                "DeviceId": device_id,
                "FenceId": fence.get("FenceId"),
                "FenceName": fence.get("FenceName"),
                "FenceType": fence.get("FenceType") or 1,
                "Latitude": str(fence.get("Latitude")),
                "Longitude": str(fence.get("Longitude")),
                "Radius": int(fence.get("Radius") or 0),
                "Address": fence.get("Address") or "",
                "AlarmType": fence.get("AlarmType") or 1,
                "InUse": fence.get("InUse", False),
                "IsDeviceFence": fence.get("IsDeviceFence", False),
                "StartTime": fence.get("StartTime") or "",
                "EndTime": fence.get("EndTime") or "",
            },
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(f"geofence edit failed: {data.get('Message', data)}")
        return data

    async def geofence_delete(
        self, session: aiohttp.ClientSession, device_id: int, fence: dict
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Geofence/DeleteGeofence"
        body = {
            "AppId": APEX_APP_ID,
            "Language": self.lang,
            "MapType": "google",
            "DeviceId": device_id,
            "FenceId": fence.get("FenceId"),
            "FenceName": fence.get("FenceName") or "",
            "FenceType": fence.get("FenceType") or 1,
            "InUse": fence.get("InUse", False),
            "IsDeviceFence": fence.get("IsDeviceFence", False),
            "Latitude": str(fence.get("Latitude") or ""),
            "Longitude": str(fence.get("Longitude") or ""),
            "Radius": float(fence.get("Radius") or 0),
            "Address": fence.get("Address") or "",
            "AlarmType": fence.get("AlarmType") or 1,
            "StartTime": "",
            "EndTime": "",
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(f"geofence delete failed: {data.get('Message', data)}")
        return data

    async def location_history(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        start_time: str,
        end_time: str,
        select_count: int = 500,
        position_type: int = 0,
        show_lbs: int = 1,
        show_wifi: int = 1,
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Location/History"
        body = {
            "AppId": APEX_APP_ID,
            "DeviceId": device_id,
            "StartTime": start_time,
            "EndTime": end_time,
            "Language": self.lang,
            "MapType": "google",
            "PositionType": position_type,
            "SelectCount": select_count,
            "ShowLbs": show_lbs,
            "ShowWifi": show_wifi,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def steps_for_day(
        self,
        session: aiohttp.ClientSession,
        imei: str,
        date: str,
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Health/GetStepsForHour"
        body = {
            "AppId": APEX_APP_ID,
            "Imei": imei,
            "Date": date,
            "Language": self.lang,
            "TimeOffset": 0.0,
        }
        return await self._post_json(session, url, body)

    async def friends_list(
        self, session: aiohttp.ClientSession, imei: str
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Device/GetDeviceFriendsList"
        body = {
            "AppId": APEX_APP_ID,
            "IMEI": imei,
            "Language": self.lang,
            "TimeOffset": 0.0,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def share_list(
        self, session: aiohttp.ClientSession, device_id: int
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/AuthShare/ShareList"
        body = {
            "AppId": APEX_APP_ID,
            "DeviceId": device_id,
            "Language": self.lang,
            "MapType": "google",
            "TimeOffset": 0.0,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def exception_messages(
        self,
        session: aiohttp.ClientSession,
        page_no: int = 1,
        page_count: int = 20,
        type_id: int = 0,
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/ExceptionMessage/ExcdeptionListWhitoutCode"
        body = {
            "AppId": APEX_APP_ID,
            "Id": self.user_id,
            "Language": self.lang,
            "PageCount": page_count,
            "PageNo": page_no,
            "TypeID": type_id,
            "UserID": self.user_id,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def messages(
        self,
        session: aiohttp.ClientSession,
        imei: str,
        chat_type: int = 2,
        file_type: int = 0,
        page_no: int = 1,
        page_count: int = 10,
        get_top: bool = False,
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Files/VoiceFileListByTime"
        body = {
            "AppId": APEX_APP_ID,
            "ChatType": chat_type,
            "FileType": file_type,
            "GetTop": get_top,
            "Imei": imei,
            "Language": self.lang,
            "pageCount": page_count,
            "pageNo": page_no,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        return data.get("Items") or []

    async def send_text_message(
        self,
        session: aiohttp.ClientSession,
        imei: str,
        text: str,
        chat_type: int = 2,
    ) -> dict:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Files/ChatTextUpload"
        body = {
            "AppId": APEX_APP_ID,
            "ChatType": chat_type,
            "Content": text,
            "Language": self.lang,
            "SerialNumber": imei,
            "TimeOffset": 0.0,
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(f"send_text failed: {data.get('Message', data)}")
        return data

    async def get_pictures(
        self,
        session: aiohttp.ClientSession,
        imei: str,
        min_date: str | None = None,
        day_per_page: int = 30,
    ) -> list[dict]:
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Files/GetPicture"
        if min_date is None:
            min_date = datetime.now().strftime("%Y-%m-%d")
        body = {
            "DayPerPage": day_per_page,
            "Imei": imei,
            "Language": self.lang,
            "MinDate": min_date,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        result: list[dict] = []
        for day in data.get("Items") or []:
            date = day.get("Date")
            for photo in day.get("Items") or []:
                if not isinstance(photo, dict):
                    continue
                entry = dict(photo)
                entry.setdefault("Date", date)
                result.append(entry)
        return result

    # ------------------------------------------------------------------
    # device pairing
    # ------------------------------------------------------------------

    async def check_device(
        self,
        session: aiohttp.ClientSession,
        serial_number: str,
    ) -> dict:
        """Register a watch IMEI with the server and return the check result.

        Response is a flat object:
          {"DeviceId": <int|null>, "DeviceType": <int>,
           "IsActivation": <bool>, "MainPhone": <str>,
           "Message": <str>, "Model": <int>,
           "NeedPhone": <bool>, "State": <int>}
        """
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Device/CheckDevice"
        body = {
            "AppId": APEX_APP_ID,
            "Language": self.lang,
            "SerialNumber": serial_number,
            "UserId": self.user_id,
        }
        return await self._post_json(session, url, body)

    async def add_device(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        relation_name: str = "",
        relation_phone: str = "",
        info: str = "",
    ) -> dict:
        """Bind a previously-checked device to the account."""
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/Device/AddDeviceAndUserGroup"
        body = {
            "AppId": APEX_APP_ID,
            "DeviceId": device_id,
            "Info": info,
            "Language": self.lang,
            "RelationName": relation_name,
            "RelationPhone": relation_phone,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(
                f"add device failed: {data.get('Message', data)}"
            )
        return data

    async def unbound_device(
        self,
        session: aiohttp.ClientSession,
        device_id: int,
        user_group_id: int = 1,
    ) -> dict:
        """Remove a device from the account."""
        await self._ensure_token(session)
        url = DEVICE_BASE + "api/AuthShare/RemoveShare"
        body = {
            "AppId": APEX_APP_ID,
            "DeviceId": device_id,
            "Language": self.lang,
            "UserGroupId": user_group_id,
            "UserId": self.user_id,
        }
        data = await self._post_json(session, url, body)
        if data.get("State") not in (0, None):
            raise RuntimeError(
                f"remove device failed: {data.get('Message', data)}"
            )
        return data

    # ------------------------------------------------------------------
    # ECP calls API
    # ------------------------------------------------------------------

    async def ecp_calls_last(
        self, session: aiohttp.ClientSession, man_id: str
    ) -> dict:
        url = ECP_BASE + "ecp/calls/last"
        body = {"ApiKey": API_KEY, "man_id": man_id}
        async with session.post(url, json=body) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")
            return await r.json()

    async def ecp_calls_history(
        self, session: aiohttp.ClientSession, man_id: str
    ) -> list[dict]:
        url = ECP_BASE + "ecp/calls/history"
        body = {"ApiKey": API_KEY, "man_id": man_id}
        async with session.post(url, json=body) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")
            data = await r.json()
        return data.get("history", []) or []