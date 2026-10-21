"""Contact-icon helpers for SafeFamily Lite.

The local backend stores the phonebook; this module only maps the friendly
avatar name used by the service UI to the numeric value the watch expects.
"""
from __future__ import annotations

# Wire icon values. 6, 7 and 8 all render the same "Other" avatar on the watch.
CONTACT_ICONS: dict[int, str] = {
    0: "Father",
    1: "Mother",
    2: "Sister",
    3: "Grandpa",
    4: "Granny",
    5: "Brother",
    6: "Other",
    7: "Other",
    8: "Other",
}

# Names → wire icon value. Accepts common English aliases.
_ICON_ALIASES: dict[str, int] = {
    "father": 0, "dad": 0, "papa": 0,
    "mother": 1, "mum": 1, "mom": 1, "mama": 1,
    "sister": 2, "sis": 2,
    "grandpa": 3, "grandfather": 3, "grandad": 3,
    "granny": 4, "grandma": 4, "grandmother": 4, "gran": 4,
    "brother": 5, "bro": 5,
    "other": 6, "default": 6, "sos": 6,
}


def resolve_icon(value: int | str | None, default: int = 6) -> int:
    """Normalize an icon input to a wire value (0-8).

    Accepts an integer, a numeric string, or a friendly name
    (case-insensitive).
    """
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value if 0 <= value <= 8 else default
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        return number if 0 <= number <= 8 else default
    return _ICON_ALIASES.get(text.lower(), default)
