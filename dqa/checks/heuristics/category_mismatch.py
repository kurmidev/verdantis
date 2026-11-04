from collections.abc import Sequence

from dqa.checks.heuristics._build import VERSION, make_finding, severity, tokens
from dqa.checks.heuristics.defaults import DEFAULT_CATEGORY_KEYWORDS
from dqa.checks.registry import rule
from dqa.models import Context, Finding, IssueType, Record, Severity
from dqa.normalize import is_blank

RULE_ID = "category_mismatch"


@rule(RULE_ID, VERSION, IssueType.CATEGORY_MISMATCH_CANDIDATE, layer="heuristic", scope="record")
def category_mismatch(records: Sequence[Record], ctx: Context) -> list[Finding]:
    kw = {k.lower(): v for k, v in (ctx.reference.category_keywords or DEFAULT_CATEGORY_KEYWORDS).items()}
    out: list[Finding] = []
    for r in records:
        if is_blank(r.category) or is_blank(r.item_description):
            continue
        hits = {t: kw[t] for t in tokens(r) if t in kw}
        expected = sorted(set(hits.values()), key=str.casefold)
        current = (r.category or "").strip().casefold()
        if not expected or all(e.casefold() == current for e in expected):
            continue
        # PROVISIONAL(OQ-106): 0.7 for one expected category, 0.6 when keywords disagree.
        one = len(expected) == 1
        out.append(make_finding(
            r, ctx, issue_type=IssueType.CATEGORY_MISMATCH_CANDIDATE, rule_id=RULE_ID,
            sev=severity(ctx, IssueType.CATEGORY_MISMATCH_CANDIDATE, Severity.LOW),
            confidence=0.7 if one else 0.6,
            explanation=f"Description suggests {', '.join(expected)}, but category is {r.category}.",
            evidence={"item_description": r.item_description, "category": r.category,
                      "matched_keywords": hits},
            action="Review category assignment before approval.",
            suggested_value={"category": expected[0]} if one else None,
        ))
    return sorted(out, key=lambda f: f.record_key)
