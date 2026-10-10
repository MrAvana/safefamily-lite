"""Shared Class Mode helpers for SafeFamily Lite."""
from __future__ import annotations

import json
import logging

from .alarms import DAY_NAMES, days_to_weeks, weeks_to_days

_LOGGER = logging.getLogger(__name__)

CLASS_MODE_CODE = "0117"


def parse_class_mode_json(raw: str) -> list[dict]:
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("Could not parse Class Mode JSON: %r", raw[:200])
        return []
    if not isinstance(parsed, list):
        return []
    return [w for w in parsed if isinstance(w, dict)]


def _window_enabled(window: dict) -> bool:
    for key in ("MainSwitch", "IsEnable"):
        v = window.get(key)
        if v is None:
            continue
        try:
            if int(v) == 1:
                return True
        except (TypeError, ValueError):
            continue
    return False


def class_window_summary(window: dict) -> str:
    start = str(window.get("StartTime") or "00:00")
    end = str(window.get("EndTime") or "00:00")
    days = weeks_to_days(str(window.get("Weeks") or ""))
    if days == DAY_NAMES:
        return f"{start}-{end}"
    return f"{start}-{end} {','.join(days)}"


def make_class_window(
    start: str, end: str, days: list[str], enabled: bool = True
) -> dict:
    return {
        "EndTime": end,
        "Interval": 0,
        "IsEnable": 1 if enabled else 0,
        "MainSwitch": "0",
        "RemindType": 0,
        "StartTime": start,
        "Weeks": days_to_weeks(days),
    }


def normalize_window(window: dict) -> dict:
    return {
        "start": str(window.get("StartTime") or ""),
        "end": str(window.get("EndTime") or ""),
        "days": weeks_to_days(str(window.get("Weeks") or "")),
        "enabled": _window_enabled(window),
    }