from collections.abc import Sequence

from dqa.checks.heuristics._build import VERSION, make_finding, severity, tokens
from dqa.checks.registry import rule
from dqa.models import Context, Finding, IssueType, Record, Severity
from dqa.normalize import is_blank

RULE_ID = "weak_description"


@rule(RULE_ID, VERSION, IssueType.WEAK_DESCRIPTION, layer="heuristic", scope="record")
def weak_description(records: Sequence[Record], ctx: Context) -> list[Finding]:
    generic = {g.lower() for g in ctx.reference.generic_terms}
    out: list[Finding] = []
    for r in records:
        if is_blank(r.item_description):
            continue
        toks = tokens(r)
        hit = [
            name for name, cond in (
                ("T1", len(toks) < ctx.params.min_description_tokens),
                ("T2", all(t in generic for t in toks)),
                ("T3", not any(any(c.isdigit() for c in t) for t in toks)),
            ) if cond
        ]
        if not hit:
            continue
        # PROVISIONAL(OQ-106): confidence 0.7 + 0.1 per extra trigger; medium when >= 2 triggers.
        conf = round(0.7 + 0.1 * (len(hit) - 1), 3)
        sev = severity(ctx, IssueType.WEAK_DESCRIPTION, Severity.MEDIUM if len(hit) >= 2 else Severity.LOW)
        out.append(make_finding(
            r, ctx, issue_type=IssueType.WEAK_DESCRIPTION, rule_id=RULE_ID, sev=sev, confidence=conf,
            explanation="Description is too short or generic to identify the item.",
            evidence={"item_description": r.item_description, "tokens": list(toks), "triggers": hit},
            action="Review the description and add identifying attributes such as size or type.",
        ))
    return sorted(out, key=lambda f: f.record_key)
