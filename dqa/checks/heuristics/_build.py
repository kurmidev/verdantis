"""Local finding builder and record helpers for heuristics.

Swap `make_finding` for dqa.checks.base.make_finding once it exists (worker B).
"""
import hashlib
from typing import Any

from dqa.models import Context, Finding, IssueType, Record, Severity, Source
from dqa.normalize import normalize_mpn, tokenize

VERSION = "1.0.0"


def tokens(rec: Record) -> tuple[str, ...]:
    return rec.norm.description_tokens or tokenize(rec.item_description)


def mpn_key(rec: Record) -> str | None:
    return rec.norm.mpn_key or normalize_mpn(rec.manufacturer_part_number)


def mfr_key(rec: Record, ctx: Context) -> str | None:
    """Canonical manufacturer: alias lookup (case-insensitive), else lowercase trimmed raw."""
    raw = (rec.manufacturer or "").strip().lower()
    if not raw or raw in {"n/a", "null"}:
        return None
    aliases = {k.strip().lower(): v.strip().lower() for k, v in ctx.reference.manufacturer_aliases.items()}
    return aliases.get(raw, raw)


def severity(ctx: Context, issue: IssueType, default: Severity) -> Severity:
    # PROVISIONAL(OQ-106): policy table incomplete; reference override else local default.
    return ctx.reference.severity_policy.get(issue.value, default)


def make_finding(
    rec: Record, ctx: Context, *, issue_type: IssueType, rule_id: str, sev: Severity,
    confidence: float, explanation: str, evidence: dict[str, Any], action: str,
    suggested_value: dict[str, Any] | None = None, discriminator: str = "",
) -> Finding:
    # PROVISIONAL(OQ-109): dedupe_key derivation, discriminator = counterpart key for pairs.
    raw = f"{ctx.batch_id}|{rec.record_key}|{issue_type.value}|{rule_id}|{VERSION}|{discriminator}"
    return Finding(
        batch_id=ctx.batch_id, record_key=rec.record_key, item_id=rec.item_id,
        issue_type=issue_type, severity=sev, confidence=confidence, explanation=explanation,
        evidence=evidence, suggested_action=action, suggested_value=suggested_value,
        source=Source.HEURISTIC, rule_id=rule_id, rule_version=VERSION,
        dedupe_key=hashlib.sha256(raw.encode()).hexdigest(),
    )
