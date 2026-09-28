"""Chat / emoji helpers for SafeFamily Lite.

The watch supports exactly four emoji codes:
    k01em0, k01em1, k01em2, k01em3

Wire codes must stay as-is. Edit the labels below to match what each
sticker actually shows.
"""
from __future__ import annotations

EMOJI_CODES: tuple[str, ...] = ("k01em0", "k01em1", "k01em2", "k01em3")

EMOJI_MAP: dict[str, str] = {
    "k01em0": "Sticker 1",
    "k01em1": "Sticker 2",
    "k01em2": "Sticker 3",
    "k01em3": "Sticker 4",
}

EMOJI_URL_BASE = "/safefamily_lite/emojis"

NAME_TO_CODE: dict[str, str] = {code: code for code in EMOJI_MAP}
NAME_TO_CODE.update({name: code for code, name in EMOJI_MAP.items()})
for _n, _code in enumerate(EMOJI_CODES):
    NAME_TO_CODE.setdefault(str(_n), _code)


def is_emoji_code(content: str) -> bool:
    return content in EMOJI_MAP


def emoji_label(content: str) -> str | None:
    return EMOJI_MAP.get(content)


def emoji_filename(code: str) -> str | None:
    if code in EMOJI_MAP:
        return f"{code}.png"
    return None


def emoji_url(code: str) -> str | None:
    fn = emoji_filename(code)
    if fn is None:
        return None
    return f"{EMOJI_URL_BASE}/{fn}"


def resolve_emoji(value: str) -> str | None:
    s = str(value).strip()
    if s in EMOJI_MAP:
        return s
    if s in NAME_TO_CODE:
        return NAME_TO_CODE[s]
    for name, code in NAME_TO_CODE.items():
        if name.lower() == s.lower():
            return code
    return None


def index_of(code: str) -> int | None:
    try:
        return EMOJI_CODES.index(code)
    except ValueError:
        return None