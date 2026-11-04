"""Finding construction shared by all checks. Pure: never stamps time or assigns ids."""
import hashlib
from typing import Any

from dqa.checks.policy import severity_for
from dqa.checks.templates import render
from dqa.models import Context, Finding, IssueType, Record, Source


def dedupe_key(batch_id: str, record_key: str, issue_type: IssueType, rule_id: str,
               rule_version: str, discriminator: str = "") -> str:
    # PROVISIONAL(OQ-109): HLD 4.7 five-column key vs single dedupe_key column (6.5).
    raw = f"{batch_id}|{record_key}|{issue_type}|{rule_id}|{rule_version}|{discriminator}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_finding(*, rule_id: str, rule_version: str, issue_type: IssueType, record: Record,
                 ctx: Context, evidence: dict[str, Any], source: Source, confidence: float,
                 suggested_value: dict[str, Any] | None = None,
                 discriminator: str = "") -> Finding:
    explanation, action = render(issue_type, {**record.raw, "record_key": record.record_key,
                                              **evidence})
    return Finding(
        batch_id=ctx.batch_id, record_key=record.record_key, item_id=record.item_id,
        issue_type=issue_type, severity=severity_for(ctx, issue_type), confidence=confidence,
        explanation=explanation, evidence=evidence, suggested_action=action,
        suggested_value=suggested_value, source=source, rule_id=rule_id,
        rule_version=rule_version,
        dedupe_key=dedupe_key(ctx.batch_id, record.record_key, issue_type, rule_id,
                              rule_version, discriminator),
    )
