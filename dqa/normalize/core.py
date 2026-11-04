"""Pure normalisation helpers (LLD 01 step 7). Raw values are never modified."""
import re

# A-105: only these markers are blank until confirmed (OQ-103).
_BLANK_MARKERS = frozenset({"n/a", "null"})
_MPN_STRIP = re.compile(r"[\s.\-‐-―−]+")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def is_blank(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    s = value.strip()  # str.strip handles NBSP and other Unicode spaces
    return s == "" or s.lower() in _BLANK_MARKERS


def normalize_mpn(value: str | None) -> str | None:
    if value is None or is_blank(value):
        return None
    key = _MPN_STRIP.sub("", value).upper()
    return key or None


def normalize_uom(value: str | None) -> str | None:
    if value is None or is_blank(value):
        return None
    return value.strip().upper().rstrip(".").strip() or None


def tokenize(text: str | None) -> tuple[str, ...]:
    if text is None:
        return ()
    return tuple(t.lower() for t in _TOKEN.findall(text))
