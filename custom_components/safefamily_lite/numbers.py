"""Turning a typed phone number into the strings the watch compares.

The watch matches the caller ID as a *string*. A number stored in one
presentation and presented in another is a stranger, and with "Protect from
Stranger Calls" on a stranger's call is rejected -- so both presentations have
to be in the phonebook.

Producing them by string surgery means guessing a country code and a trunk
prefix, and a wrong guess fails silently: the entry looks fine and never rings.
libphonenumber knows the numbering plan of every country, so this module asks
it for the canonical forms and whether the number is real at all.

There are deliberately no Home Assistant imports here. These rules are the part
that can quietly lock a child out, so they are testable on their own.
"""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

# Characters a person or a contact card may add around the digits. Removing
# them is not interpreting the number, it is discarding what a screen drew.
_NOISE = re.compile(r"[\s\-()./]")

# A number with fewer digits than this cannot be a subscriber in any plan; it
# is a short code, an extension or half a number. libphonenumber rejects these
# per country already, but this keeps the message honest when a region is not
# configured and parsing therefore never runs.
_MIN_DIGITS = 6


def normalize(number: str) -> str:
    """Strip presentation characters and the `00` international prefix.

    `00` is how most of the world writes `+`, and libphonenumber only
    recognises the latter. Nothing else is rewritten.
    """
    text = _NOISE.sub("", str(number or ""))
    if text.startswith("00"):
        text = "+" + text[2:]
    return text


def parse(number: str, region: str | None):
    """Parse `number`, using `region` only for a number typed in national form.

    An international number carries its own country, so it parses even when
    Home Assistant's country is unset. A national number cannot: there is
    nothing to distinguish `0340000000` from an arbitrary string of digits.

    Returns None when the number cannot be read at all, which includes the
    "no region and no `+`" case.
    """
    text = normalize(number)
    if not text:
        return None
    try:
        return phonenumbers.parse(text, region or None)
    except NumberParseException:
        return None


def number_forms(number: str, region: str | None) -> list[str]:
    """The presentations of `number` worth storing, or `[]` if it is not real.

    International first: that is the one worth marking as SOS, and a second SOS
    entry would dial the same person twice.

    A number from another country comes back in one form only. Inbound
    international calls present the `+` form, and that country's domestic form
    would spend one of the 13 slots on a string the caller's network is not
    going to produce.

    `[]` is the refusal path: the caller turns it into a message rather than
    storing something that would never ring.
    """
    parsed = parse(number, region)
    if parsed is None or not phonenumbers.is_valid_number(parsed):
        return []

    e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    home = phonenumbers.region_code_for_number(parsed)
    if region and home and home != region.upper():
        return [e164]

    national = re.sub(
        r"\D", "", phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
    )
    return [form for form in dict.fromkeys((e164, national)) if form]


def explain(number: str, region: str | None) -> str:
    """Why `number` was refused, in terms of what was typed.

    The point is to make the fix obvious: a missing country code, a typo, or a
    Home Assistant setting that was never filled in all look like the same
    failure otherwise.
    """
    text = normalize(number)
    if not text:
        return "the number is empty"
    if re.sub(r"\D", "", text) and len(re.sub(r"\D", "", text)) < _MIN_DIGITS:
        return (
            f"{number} is too short to be a phone number; short codes cannot "
            "ring the watch, so they do not belong in its phonebook"
        )
    if not text.startswith("+") and not region:
        return (
            f"{number} does not start with a country code, and Home Assistant's "
            "country is not set, so it cannot be read as a local number; set the "
            "country under Settings > System > General > Country, or enter the "
            "number starting with + and its country code"
        )

    parsed = parse(number, region)
    if parsed is None:
        return (
            f"{number} is not a number this could read; include the country "
            "code, for example +261 followed by the number without its leading 0"
        )

    where = phonenumbers.region_code_for_number(parsed) or region
    return (
        f"{number} is not a valid phone number for {where}. Check the digits; "
        "if it belongs to another country, start with + and its country code "
        "instead of typing it in local form."
    )
