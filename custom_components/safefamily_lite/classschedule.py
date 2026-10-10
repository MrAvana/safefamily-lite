"""Class Schedule (timetable) parsing for SafeFamily Lite."""
from __future__ import annotations

import json
import logging

_LOGGER = logging.getLogger(__name__)

CLASS_SCHEDULE_CODE = "4004"

DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
DAY_ALIASES = {
    "mon": 1, "monday": 1,
    "tue": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3,
    "thu": 4, "thursday": 4,
    "fri": 5, "friday": 5,
    "sat": 6, "saturday": 6,
    "sun": 7, "sunday": 7,
}

DEFAULT_PERIOD_PLACEHOLDER = "12:00-12:00"


def parse_schedule_json(raw: str) -> list[dict]:
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("Could not parse Class Schedule JSON: %r", raw[:200])
        return []
    if not isinstance(parsed, list):
        return []
    return [w for w in parsed if isinstance(w, dict)]


def parse_periods(week0_subject: str) -> list[str]:
    s = str(week0_subject or "").strip()
    if not s or s == "0":
        return []
    ranges = [x.strip() for x in s.split(",") if x.strip()]
    if len(ranges) == 1 and ranges[0] == DEFAULT_PERIOD_PLACEHOLDER:
        return []
    return ranges


def encode_periods(periods: list[str]) -> str:
    if not periods:
        return DEFAULT_PERIOD_PLACEHOLDER
    return ",".join(periods)


def parse_subject_entry(entry: str) -> str | None:
    s = str(entry or "").strip()
    if not s or s == "0":
        return None
    if s.startswith("1") and len(s) > 1:
        return s[1:]
    return s


def parse_day_subjects(subject_str: str, period_count: int) -> list[str | None]:
    s = str(subject_str or "").strip()
    if not s:
        return [None] * period_count
    parts = [x.strip() for x in s.split(",")]
    result = [parse_subject_entry(p) for p in parts]
    if len(result) < period_count:
        result.extend([None] * (period_count - len(result)))
    return result[:period_count]


def encode_subject(name: str | None) -> str:
    if not name:
        return "0"
    return f"1{name}"


def encode_day_subjects(subjects: list[str | None]) -> str:
    return ",".join(encode_subject(s) for s in subjects)


def parse_schedule(raw: str) -> dict:
    windows = parse_schedule_json(raw)
    if not windows:
        return {"periods": [], "days": {}}

    week0 = next((w for w in windows if w.get("Week") == 0), {})
    periods = parse_periods(week0.get("Subject", ""))

    days: dict[str, list[str | None]] = {}
    for w in windows:
        week = w.get("Week")
        if week == 0 or week not in DAY_NAMES:
            continue
        days[DAY_NAMES[week]] = parse_day_subjects(
            w.get("Subject", ""), len(periods)
        )

    return {"periods": periods, "days": days}


def normalize_day_param(value) -> int:
    if isinstance(value, int):
        if 1 <= value <= 7:
            return value
        raise ValueError(f"Day must be 1-7, got {value}")
    s = str(value).strip().lower()
    if s.isdigit():
        n = int(s)
        if 1 <= n <= 7:
            return n
    if s in DAY_ALIASES:
        return DAY_ALIASES[s]
    raise ValueError(f"Unknown day {value!r}")


def _blank_schedule() -> list[dict]:
    return [{"Week": 0, "Subject": DEFAULT_PERIOD_PLACEHOLDER}] + [
        {"Week": i, "Subject": ""} for i in range(1, 8)
    ]


def add_period(
    raw: str,
    start: str,
    end: str,
    position: int | None = None,
) -> list[dict]:
    windows = parse_schedule_json(raw)
    if not windows:
        windows = _blank_schedule()

    week0 = next((w for w in windows if w.get("Week") == 0), None)
    if week0 is None:
        week0 = {"Week": 0, "Subject": DEFAULT_PERIOD_PLACEHOLDER}
        windows.insert(0, week0)

    periods = parse_periods(week0.get("Subject", ""))
    new_range = f"{start}-{end}"
    if position is None or position < 1 or position > len(periods) + 1:
        insert_at = len(periods)
    else:
        insert_at = position - 1

    periods.insert(insert_at, new_range)
    week0["Subject"] = encode_periods(periods)

    sched = parse_schedule(json.dumps(windows))
    for day_idx in range(1, 8):
        day_name = DAY_NAMES[day_idx]
        subjects = list(sched["days"].get(day_name, []))
        while len(subjects) < len(periods) - 1:
            subjects.append(None)
        subjects.insert(insert_at, None)
        subjects = subjects[: len(periods)]

        day_entry = next((w for w in windows if w.get("Week") == day_idx), None)
        if day_entry is None:
            day_entry = {"Week": day_idx, "Subject": ""}
            windows.append(day_entry)
        day_entry["Subject"] = encode_day_subjects(subjects)

    windows.sort(key=lambda w: w.get("Week", 0))
    return windows


def delete_period(raw: str, position: int) -> list[dict]:
    windows = parse_schedule_json(raw)
    if not windows:
        raise ValueError("No schedule exists")

    week0 = next((w for w in windows if w.get("Week") == 0), None)
    if week0 is None:
        raise ValueError("Schedule has no period definitions")

    periods = parse_periods(week0.get("Subject", ""))
    if position < 1 or position > len(periods):
        raise ValueError(f"Period {position} out of range 1-{len(periods)}")

    sched = parse_schedule(json.dumps(windows))
    periods.pop(position - 1)
    week0["Subject"] = encode_periods(periods)

    for day_idx in range(1, 8):
        day_name = DAY_NAMES[day_idx]
        subjects = list(sched["days"].get(day_name, []))
        while len(subjects) < position:
            subjects.append(None)
        subjects.pop(position - 1)
        subjects = subjects[: len(periods)]

        day_entry = next((w for w in windows if w.get("Week") == day_idx), None)
        if day_entry is None:
            day_entry = {"Week": day_idx, "Subject": ""}
            windows.append(day_entry)
        day_entry["Subject"] = encode_day_subjects(subjects) if subjects else ""

    windows.sort(key=lambda w: w.get("Week", 0))
    return windows