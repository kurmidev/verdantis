"""Row validation and Record construction (LLD 01 steps 5-9). Input is never mutated."""
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from dqa.ingest.keys import KeyAssigner
from dqa.ingest.parser import MAX_ROWS, ParsedRow
from dqa.models import Finding, IssueType, Record, Severity, Source
from dqa.normalize.build import build_norm
from dqa.normalize.core import is_blank
from dqa.normalize.scanner import MAX_AI_FIELD_LENGTH

FIELDS = (
    "item_id", "item_description", "manufacturer", "manufacturer_part_number",
    "category", "unit_of_measure", "source_system",
)
RULE_ID, RULE_VERSION = "row_validation", "1.0.0"
# PROVISIONAL(OQ-106): severities for row-level findings are not defined in the HLD.
SEVERITY = {IssueType.MALFORMED_ROW: Severity.HIGH, IssueType.INCOMPLETE_ROW: Severity.MEDIUM}
_UNUSABLE = ("not_an_object", "decode_error", "blank_row")


@dataclass(frozen=True)
class IngestConfig:
    # PROVISIONAL(OQ-103): manufacturer_part_number must NOT be required (brief record 1001 expects no incomplete_row).
    required_fields: tuple[str, ...] = ("item_id", "source_system", "item_description")
    max_rows: int = MAX_ROWS
    max_field_length: int = 10_000  # PROVISIONAL(OQ-103)
    max_ai_field_length: int = MAX_AI_FIELD_LENGTH  # PROVISIONAL(OQ-103)
    # PROVISIONAL(OQ-104): only the alias named in the HLD; full list pending.
    alias_map: Mapping[str, str] = field(default_factory=lambda: {"mfr_part_no": "manufacturer_part_number"})


def canonical_key(key: str, alias_map: Mapping[str, str]) -> str:
    k = re.sub(r"[\s\-]+", "_", key.strip().lower())
    return alias_map.get(k, k)


def _extract(
    raw: Any, problems: tuple[str, ...], cfg: IngestConfig
) -> tuple[dict[str, str | None], dict[str, Any], list[str], list[str]]:
    """-> (typed fields, raw to store, malformed reasons, alias conflicts)."""
    fields: dict[str, str | None] = dict.fromkeys(FIELDS)
    malformed: list[str] = []
    conflicts = [p.split(":", 1)[1] for p in problems if p.startswith("duplicate_header:")]
    malformed += ["overflow"] if "overflow" in problems else []
    malformed += [p for p in problems if p.startswith("decode_error")]
    if not isinstance(raw, dict):
        return fields, {"_value": raw}, ["not_an_object", *malformed], conflicts
    seen: set[str] = set()
    for k, v in raw.items():
        ck = canonical_key(k, cfg.alias_map) if isinstance(k, str) else None
        if ck not in FIELDS:
            continue
        if ck in seen:
            conflicts.append(ck)
            continue
        seen.add(ck)
        if isinstance(v, (dict, list)):
            malformed.append(f"unsupported_type:{ck}")
        elif v is not None:
            s = v if isinstance(v, str) else str(v)
            if len(s) > cfg.max_field_length:
                malformed.append(f"field_too_long:{ck}")
            fields[ck] = s
    if all(is_blank(v) for v in raw.values()):
        malformed.append("blank_row")
    return fields, raw, malformed, conflicts


def _finding(batch_id: str, rec: Record, issue: IssueType, explanation: str, action: str,
             evidence: dict[str, Any]) -> Finding:
    return Finding(
        batch_id=batch_id, record_key=rec.record_key, item_id=rec.item_id, issue_type=issue,
        severity=SEVERITY[issue], confidence=1.0, explanation=explanation, evidence=evidence,
        suggested_action=action, source=Source.DETERMINISTIC_RULE, rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        # PROVISIONAL(OQ-109): dedupe_key derivation
        dedupe_key=f"{batch_id}:{rec.record_key}:{issue.value}:{RULE_ID}:{RULE_VERSION}",
    )


def validate_row(
    parsed: ParsedRow, keys: KeyAssigner, batch_id: str, cfg: IngestConfig
) -> tuple[Record, list[Finding]]:
    fields, raw, malformed, conflicts = _extract(parsed.raw, parsed.problems, cfg)
    rec = Record(
        row_number=parsed.row_number,
        record_key=keys.assign(parsed.row_number, fields["source_system"], fields["item_id"]),
        raw=raw,
        norm=build_norm(fields, max_ai_len=cfg.max_ai_field_length),
        **fields,
    )
    n = parsed.row_number
    out: list[Finding] = []
    if malformed:
        out.append(_finding(
            batch_id, rec, IssueType.MALFORMED_ROW,
            f"Row {n} could not be read reliably ({', '.join(malformed)}).",
            "Ask the source owner to correct the row and upload it again.",
            {"row_number": n, "reasons": malformed},
        ))
    blank = [f for f in cfg.required_fields if is_blank(fields.get(f))]
    short = "short_row" in parsed.problems
    if not any(m.split(":", 1)[0] in _UNUSABLE for m in malformed) and (blank or short or conflicts):
        evidence: dict[str, Any] = {
            "row_number": n, "blank_fields": blank, "raw": {f: fields.get(f) for f in blank},
        }
        if short:
            evidence["short_row"] = True
        if conflicts:
            evidence["alias_conflict"] = conflicts
        reason = (
            f"Required field '{blank[0]}' is blank." if len(blank) == 1
            else f"Required fields {', '.join(repr(b) for b in blank)} are blank." if blank
            else f"Row {n} is incomplete or has conflicting column names."
        )
        out.append(_finding(batch_id, rec, IssueType.INCOMPLETE_ROW, reason,
                            "Request the missing value from the source owner.", evidence))
    return rec, out
