"""Shared alarm parsing utilities for SafeFamily Lite."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time, timedelta

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

ALARM_CODE = "0146"
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_INDEX = {name: i + 1 for i, name in enumerate(DAY_NAMES)}
DAY_INDEX.update({name.lower(): i + 1 for i, name in enumerate(DAY_NAMES)})

_SUMMARY_RE = re.compile(
    r"^\s*(?P<time>[0-2]?\d:[0-5]\d)\s*(?P<days>[\d,\s]+|[A-Za-z,]+)?\s*$"
)


def weeks_to_days(weeks: str) -> list[str]:
    """'146' → ['Mon', 'Thu', 'Sat']"""
    if not weeks:
        return list(DAY_NAMES)
    out = []
    for ch in weeks:
        try:
            idx = int(ch)
        except ValueError:
            continue
        if 1 <= idx <= 7:
            out.append(DAY_NAMES[idx - 1])
    return out


def days_to_weeks(days: list[str]) -> str:
    """['Mon','Thu','Sat'] → '146'"""
    nums = []
    for d in days:
        idx = DAY_INDEX.get(d) or DAY_INDEX.get(d.lower())
        if idx:
            nums.append(str(idx))
    return "".join(sorted(set(nums)))


def parse_summary(summary: str) -> tuple[str, list[str]]:
    """Parse 'HH:MM [days]' → (time_str, day_list)."""
    m = _SUMMARY_RE.match(summary)
    if not m:
        raise ValueError(
            f"Alarm summary must be 'HH:MM' or 'HH:MM days'; got {summary!r}"
        )
    time_str = m.group("time").zfill(5)
    days_raw = (m.group("days") or "").strip()
    if not days_raw:
        return time_str, list(DAY_NAMES)
    if days_raw.isdigit():
        return time_str, weeks_to_days(days_raw)
    names = [d.strip() for d in days_raw.split(",") if d.strip()]
    normalized = []
    for n in names:
        key = n[:3].capitalize()
        if key in DAY_INDEX:
            normalized.append(key)
    if not normalized:
        raise ValueError(f"Could not parse days from {days_raw!r}")
    return time_str, normalized


def summary_of(alarm: dict) -> str:
    time_str = alarm.get("Time") or "00:00"
    days = weeks_to_days(str(alarm.get("Weeks") or ""))
    if days == DAY_NAMES:
        return time_str
    return f"{time_str} {','.join(days)}"


def is_enabled(alarm: dict) -> bool:
    return int(alarm.get("IsEnable") or 0) == 1


def default_alarm(time_str: str, days: list[str], enabled: bool = True) -> dict:
    return {
        "BellType": 0,
        "EndTime": "",
        "Interval": 0,
        "isCheck": False,
        "IsEnable": 1 if enabled else 0,
        "RemindType": 0,
        "StartTime": "",
        "Time": time_str,
        "Type": 0,
        "Weeks": days_to_weeks(days),
    }


def parse_alarms_json(raw: str) -> list[dict]:
    """Parse the CmdValue JSON from a CommandList 0146 entry."""
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("Could not parse alarms JSON: %r", raw[:200])
        return []
    if not isinstance(parsed, list):
        return []
    return [a for a in parsed if isinstance(a, dict)]


def next_trigger(
    alarms: list[dict], now: datetime | None = None
) -> datetime | None:
    """Compute the next datetime any enabled alarm will fire."""
    if now is None:
        now = dt_util.now()
    candidates: list[datetime] = []
    for alarm in alarms:
        if not is_enabled(alarm):
            continue
        time_str = str(alarm.get("Time") or "")
        try:
            hh, mm = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            continue
        days = weeks_to_days(str(alarm.get("Weeks") or ""))
        day_idxs = [DAY_NAMES.index(d) for d in days if d in DAY_NAMES]
        if not day_idxs:
            continue
        for offset in range(8):
            candidate_day = (now + timedelta(days=offset)).date()
            if candidate_day.weekday() not in day_idxs:
                continue
            fire = datetime.combine(candidate_day, time(hh, mm))
            if fire.tzinfo is None:
                fire = fire.replace(tzinfo=now.tzinfo)
            if fire > now:
                candidates.append(fire)
                break
    return min(candidates) if candidates else None