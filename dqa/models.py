"""Shared domain models (LLD 3.3-3.5). Frozen: functions return new objects, never mutate."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IssueType(StrEnum):
    MALFORMED_ROW = "malformed_row"
    INCOMPLETE_ROW = "incomplete_row"
    MISSING_PART_NUMBER = "missing_part_number"
    UNSUPPORTED_UOM = "unsupported_uom"
    DUPLICATE_ITEM_ID = "duplicate_item_id"
    WEAK_DESCRIPTION = "weak_description"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    CATEGORY_MISMATCH_CANDIDATE = "category_mismatch_candidate"
    CONFLICTING_SOURCE_VALUES = "conflicting_source_values"
    SUSPICIOUS_CONTENT = "suspicious_content"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# PROVISIONAL (OQ-18/OQ-130): brief uses other labels.
class Source(StrEnum):
    DETERMINISTIC_RULE = "deterministic_rule"
    HEURISTIC = "heuristic"
    AI_SUGGESTION = "ai_suggestion"


class FindingStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    INVESTIGATING = "investigating"
    IN_CHANGE_FILE = "in_change_file"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"


class ErrorCode(StrEnum):
    PARSE_ERROR = "parse_error"
    PROVIDER_ERROR = "provider_error"
    AI_INVALID_OUTPUT = "ai_invalid_output"
    POLICY_BLOCK = "policy_block"
    LOOP_GUARD_TRIGGERED = "loop_guard_triggered"
    TIMEOUT = "timeout"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NormView(_Frozen):
    """Normalised view computed by normalize/; raw values stay on Record."""

    description_tokens: tuple[str, ...] = ()
    mpn_key: str | None = None
    uom_key: str | None = None
    manufacturer_key_raw: str | None = None
    suspicious: tuple[str, ...] = ()


class Record(_Frozen):
    row_number: int = Field(ge=1)
    record_key: str
    source_system: str | None = None
    item_id: str | None = None
    item_description: str | None = None
    manufacturer: str | None = None
    manufacturer_part_number: str | None = None
    category: str | None = None
    unit_of_measure: str | None = None
    raw: dict[str, Any]
    norm: NormView = NormView()


class Finding(_Frozen):
    finding_id: str | None = None  # assigned at persistence
    batch_id: str
    record_key: str
    item_id: str | None
    issue_type: IssueType
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    evidence: dict[str, Any]
    suggested_action: str
    suggested_value: dict[str, Any] | None = None
    source: Source
    also_detected_by: tuple[Source, ...] = ()
    rule_id: str
    rule_version: str
    model_id: str | None = None
    prompt_version: str | None = None
    status: FindingStatus = FindingStatus.NEEDS_REVIEW
    dedupe_key: str
    created_at: datetime | None = None  # stamped at persistence (checks are pure)

    @field_validator("evidence")
    @classmethod
    def _evidence_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("evidence must be non-empty (FR-9)")
        return v


class Params(_Frozen):
    """HLD 6.2 parameters."""

    min_description_tokens: int = 3
    dup_similarity_threshold: float = 0.88
    ai_uncertain_band: tuple[float, float] = (0.75, 0.88)
    ai_min_confidence_display: float = 0.5
    chunk_size: int = 50
    ai_budget_per_batch_usd: float = 25.0
    four_eyes_threshold_items: int = 10


class Reference(_Frozen):
    """Steward-owned reference data (versioned)."""

    version: int = 1
    allowed_uom: tuple[str, ...] = ("EA", "PC", "BOX", "KG", "M", "L", "SET", "PR")
    uom_aliases: dict[str, str] = {}
    generic_terms: tuple[str, ...] = ("bearing", "valve", "part", "item", "misc", "spare")
    category_keywords: dict[str, str] = {}
    taxonomy: tuple[str, ...] = ()
    manufacturer_aliases: dict[str, str] = {}
    severity_policy: dict[str, Severity] = {}


class Context(_Frozen):
    batch_id: str
    params: Params = Params()
    reference: Reference = Reference()
