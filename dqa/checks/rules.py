"""Deterministic rules (LLD 02 3.4). Pure functions registered in the rule registry."""
from collections import defaultdict
from collections.abc import Sequence

from dqa.checks.base import make_finding
from dqa.checks.registry import rule
from dqa.models import Context, Finding, IssueType, Record, Source
from dqa.normalize import is_blank, normalize_uom

# One-line change point for OQ-100 (brief expects 0.95 for missing_part_number; HLD says 1.0).
RULE_CONFIDENCE: dict[str, float] = {
    "missing_part_number": 1.0,
    "unsupported_uom": 1.0,
    "duplicate_item_id": 1.0,
}
_V = "1.0.0"


@rule("missing_part_number", _V, IssueType.MISSING_PART_NUMBER, layer="deterministic",
      scope="record")
def missing_part_number(records: Sequence[Record], ctx: Context) -> list[Finding]:
    return [
        make_finding(
            rule_id="missing_part_number", rule_version=_V,
            issue_type=IssueType.MISSING_PART_NUMBER, record=r, ctx=ctx,
            evidence={"manufacturer": r.manufacturer,
                      "manufacturer_part_number": r.manufacturer_part_number},
            source=Source.DETERMINISTIC_RULE,
            confidence=RULE_CONFIDENCE["missing_part_number"])
        for r in records
        if not is_blank(r.manufacturer) and is_blank(r.manufacturer_part_number)
    ]


@rule("unsupported_uom", _V, IssueType.UNSUPPORTED_UOM, layer="deterministic", scope="record")
def unsupported_uom(records: Sequence[Record], ctx: Context) -> list[Finding]:
    ref = ctx.reference
    allowed = {u.upper() for u in ref.allowed_uom}
    aliases = {k.upper(): v.upper() for k, v in ref.uom_aliases.items()}
    out: list[Finding] = []
    for r in records:
        k = normalize_uom(r.unit_of_measure)
        # PROVISIONAL(OQ-108): blank UoM is not flagged here; "suspicious" UoM undefined.
        if k is None or k in allowed or aliases.get(k) in allowed:
            continue
        out.append(make_finding(
            rule_id="unsupported_uom", rule_version=_V, issue_type=IssueType.UNSUPPORTED_UOM,
            record=r, ctx=ctx,
            evidence={"unit_of_measure": r.unit_of_measure, "normalised": k,
                      "allowed_uom": list(ref.allowed_uom), "allowed_uom_version": ref.version},
            source=Source.DETERMINISTIC_RULE, confidence=RULE_CONFIDENCE["unsupported_uom"]))
    return out


@rule("duplicate_item_id", _V, IssueType.DUPLICATE_ITEM_ID, layer="deterministic",
      scope="batch")
def duplicate_item_id(records: Sequence[Record], ctx: Context) -> list[Finding]:
    # PROVISIONAL(OQ-112): trimmed, case-sensitive; blank parts skipped; every member flagged.
    groups: defaultdict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        if is_blank(r.source_system) or is_blank(r.item_id):
            continue
        groups[(str(r.source_system).strip(), str(r.item_id).strip())].append(r)
    out: list[Finding] = []
    for (system, item_id), members in groups.items():
        if len(members) < 2:
            continue
        occurrences = [{"row_number": m.row_number, "record_key": m.record_key}
                       for m in sorted(members, key=lambda m: m.row_number)]
        out.extend(
            make_finding(
                rule_id="duplicate_item_id", rule_version=_V,
                issue_type=IssueType.DUPLICATE_ITEM_ID, record=m, ctx=ctx,
                evidence={"source_system": system, "item_id": item_id,
                          "occurrences": occurrences},
                source=Source.DETERMINISTIC_RULE,
                confidence=RULE_CONFIDENCE["duplicate_item_id"])
            for m in members)
    return out
