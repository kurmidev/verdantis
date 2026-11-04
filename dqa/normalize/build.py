"""Builds the NormView for a record from its (stringified) canonical fields. Never mutates input."""
import re
from collections.abc import Mapping

from dqa.models import NormView
from dqa.normalize.core import is_blank, normalize_mpn, normalize_uom
from dqa.normalize.scanner import MAX_AI_FIELD_LENGTH, scan_suspicious

# LLD 01 step 8: split on non-alphanumerics except '-' / '.' between alphanumerics ("6205-zz" stays one token).
_DESC_TOKEN = re.compile(r"[^\W_]+(?:[-.][^\W_]+)*")
_SCANNED = (
    "item_description", "manufacturer", "manufacturer_part_number", "category", "unit_of_measure",
)


def description_tokens(text: str | None) -> tuple[str, ...]:
    return tuple(t.lower() for t in _DESC_TOKEN.findall(text or ""))


def build_norm(fields: Mapping[str, str | None], *, max_ai_len: int = MAX_AI_FIELD_LENGTH) -> NormView:
    manufacturer = fields.get("manufacturer")
    suspicious = tuple(
        sorted(
            f"{name}:{reason}"
            for name in _SCANNED
            for reason in scan_suspicious(fields.get(name), max_len=max_ai_len)
        )
    )
    return NormView(
        description_tokens=description_tokens(fields.get("item_description")),
        mpn_key=normalize_mpn(fields.get("manufacturer_part_number")),
        uom_key=normalize_uom(fields.get("unit_of_measure")),
        # PROVISIONAL: upper-cased, whitespace-collapsed; manufacturer alias lookup happens in module 03.
        manufacturer_key_raw=(
            None if manufacturer is None or is_blank(manufacturer)
            else " ".join(manufacturer.split()).upper()
        ),
        suspicious=suspicious,
    )
