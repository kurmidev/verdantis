import re
from collections import defaultdict
from collections.abc import Callable, Sequence

from dqa.checks.heuristics._build import VERSION, make_finding, mfr_key, mpn_key, severity
from dqa.checks.registry import rule
from dqa.models import Context, Finding, IssueType, Record, Severity
from dqa.normalize import is_blank, normalize_uom

RULE_ID = "conflicting_source_values"
CONFIDENCE = 0.9  # same basis as the exact-MPN block (LLD 03 H4)


def _uom(r: Record, ctx: Context) -> str | None:
    k = normalize_uom(r.unit_of_measure)
    aliases = {a.upper(): v.upper() for a, v in ctx.reference.uom_aliases.items()}
    return aliases.get(k, k) if k else None


def _alnum(v: str | None) -> str | None:
    return None if is_blank(v) else re.sub(r"[\W_]+", "", v or "").casefold()  # "S.K.F." == "SKF"


# PROVISIONAL(OQ-123): compared fields and how "same item" is decided (canonical manufacturer + MPN key).
_FIELDS: dict[str, Callable[[Record, Context], str | None]] = {
    "category": lambda r, c: None if is_blank(r.category) else (r.category or "").strip().casefold(),
    "unit_of_measure": _uom,
    "manufacturer": lambda r, c: _alnum(r.manufacturer),
}
_RAW: dict[str, Callable[[Record], str | None]] = {
    "category": lambda r: r.category,
    "unit_of_measure": lambda r: r.unit_of_measure,
    "manufacturer": lambda r: r.manufacturer,
}


@rule(RULE_ID, VERSION, IssueType.CONFLICTING_SOURCE_VALUES, layer="heuristic", scope="batch")
def conflicting_source_values(records: Sequence[Record], ctx: Context) -> list[Finding]:
    groups: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for r in records:
        mk, k = mfr_key(r, ctx), mpn_key(r)
        if mk is not None and k is not None:
            groups[(mk, k)].append(r)

    out: list[Finding] = []
    for (_, k), members in sorted(groups.items()):
        if len({m.source_system for m in members}) < 2:
            continue
        conflicts: dict[str, dict[str, str | None]] = {}
        for field, norm in _FIELDS.items():
            if len({v for m in members if (v := norm(m, ctx)) is not None}) > 1:
                conflicts[field] = {str(m.source_system): _RAW[field](m) for m in members}
        if not conflicts:
            continue
        out.extend(
            make_finding(
                m, ctx, issue_type=IssueType.CONFLICTING_SOURCE_VALUES, rule_id=RULE_ID,
                sev=severity(ctx, IssueType.CONFLICTING_SOURCE_VALUES, Severity.MEDIUM),
                confidence=CONFIDENCE,
                explanation="The same item has different values in different source systems.",
                evidence={"mpn_key": k, "conflicts": conflicts},
                action="Confirm the correct values with the source owners.",
            )
            for m in sorted(members, key=lambda r: r.record_key)
        )
    return sorted(out, key=lambda f: f.record_key)
