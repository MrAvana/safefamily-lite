"""Contacts (SOS / phonebook) helpers for SafeFamily Lite.

The watch stores a list of contacts under CmdCode 9016. The app always
sends the full list when adding/editing/removing.

Wire format (what we send):
    [{"icon": 1, "name": "Dad", "number": "+261...",
      "relation": "", "shortNumber": "", "sosFlag": 1}]

Stored format (what CommandList returns):
    [{"Icon": "1", "Name": "Dad", "Number": "+261...",
      "Relation": null, "ShortNumber": "", "SosFlag": 1,
      "DevicePhoneNumber": null, "AskNumber": null}]

Icon values map to built-in avatars on the watch:

    0 = Father      3 = Grandpa     6 = Other
    1 = Mother      4 = Granny      7 = Other (alias)
    2 = Sister      5 = Brother     8 = Other (alias, used for SOS)
"""
from __future__ import annotations

import json
import logging

_LOGGER = logging.getLogger(__name__)

CONTACTS_CODE = "9016"

# Wire icon value → friendly name. Values 6, 7, 8 all render the same
# image on the watch (ic_apex_other); we surface them as "Other" here.
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

# Unique names for the dropdown selector.
CONTACT_ICON_OPTIONS: list[str] = [
    "Father",
    "Mother",
    "Sister",
    "Grandpa",
    "Granny",
    "Brother",
    "Other",
]

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


def icon_to_name(value: int | str | None) -> str:
    """0 → 'Father', 6 → 'Other', unknown → 'Other'."""
    try:
        n = int(value) if value is not None else 6
    except (TypeError, ValueError):
        n = 6
    return CONTACT_ICONS.get(n, "Other")


def resolve_icon(value: int | str | None, default: int = 6) -> int:
    """Normalize an icon input to a wire value (0-8).

    Accepts an integer, a numeric string, or a friendly name (case-insensitive).
    """
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value if 0 <= value <= 8 else default
    s = str(value).strip()
    if s.isdigit():
        n = int(s)
        return n if 0 <= n <= 8 else default
    return _ICON_ALIASES.get(s.lower(), default)


def parse_contacts_json(raw: str) -> list[dict]:
    """Parse the CmdValue JSON from a CommandList 9016 entry."""
    raw = (raw or "").strip()
    if not raw or raw == "null":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("Could not parse contacts JSON: %r", raw[:200])
        return []
    if not isinstance(parsed, list):
        return []
    return [c for c in parsed if isinstance(c, dict)]


def normalize_contact(contact: dict) -> dict:
    """Read a contact from either format into a canonical dict."""

    def _get(*keys, default=None):
        for k in keys:
            v = contact.get(k)
            if v is not None:
                return v
        return default

    name = str(_get("name", "Name", default="") or "")
    number = str(_get("number", "Number", default="") or "")

    try:
        icon = int(_get("icon", "Icon", default=6) or 6)
    except (TypeError, ValueError):
        icon = 6

    try:
        sos = bool(int(_get("sosFlag", "SosFlag", default=0) or 0))
    except (TypeError, ValueError):
        sos = False

    short_number = str(_get("shortNumber", "ShortNumber", default="") or "")
    relation = str(_get("relation", "Relation", default="") or "")

    return {
        "name": name,
        "number": number,
        "icon": icon,
        "icon_name": icon_to_name(icon),
        "sos": sos,
        "short_number": short_number,
        "relation": relation,
    }


def normalize_contacts(contacts: list[dict]) -> list[dict]:
    return [normalize_contact(c) for c in contacts if isinstance(c, dict)]


def to_wire_contact(contact: dict) -> dict:
    """Canonical dict → wire format (lowercase keys, numeric icon/sosFlag)."""
    return {
        "icon": resolve_icon(contact.get("icon")),
        "name": str(contact.get("name") or ""),
        "number": str(contact.get("number") or ""),
        "relation": str(contact.get("relation") or ""),
        "shortNumber": str(contact.get("short_number") or ""),
        "sosFlag": 1 if contact.get("sos") else 0,
    }


def contacts_to_wire_json(contacts: list[dict]) -> str:
    return json.dumps(
        [to_wire_contact(c) for c in contacts], separators=(",", ":")
    )


def find_contact(
    contacts: list[dict],
    *,
    name: str | None = None,
    number: str | None = None,
) -> int | None:
    """Return the index of the first matching contact, or None.

    Matching is case-insensitive for name. Number is compared as strings,
    with a small normalization (strip spaces, keep leading +).
    """

    def _norm_number(n: str) -> str:
        return "".join(ch for ch in str(n or "") if ch.isdigit() or ch == "+")

    target_number = _norm_number(number) if number else None
    target_name = name.strip().lower() if name else None

    for idx, c in enumerate(contacts):
        if target_name and str(c.get("name") or "").strip().lower() == target_name:
            return idx
        if target_number and _norm_number(c.get("number") or "") == target_number:
            return idx
    return None