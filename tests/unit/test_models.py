import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dqa.models import Context, Finding, IssueType, NormView, Record, Severity, Source

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _finding(**over):
    base = {
        "batch_id": "b_1", "record_key": "ERP-A:1001", "item_id": "1001",
        "issue_type": IssueType.MISSING_PART_NUMBER, "severity": Severity.MEDIUM, "confidence": 1.0,
        "explanation": "x", "evidence": {"manufacturer": "SKF"}, "suggested_action": "y",
        "source": Source.DETERMINISTIC_RULE, "rule_id": "missing_part_number", "rule_version": "1.0.0",
        "dedupe_key": "k",
    }
    return Finding(**{**base, **over})


def test_finding_is_frozen():
    with pytest.raises(ValidationError):
        _finding().confidence = 0.5  # type: ignore[misc]


def test_finding_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _finding(unexpected=1)


def test_finding_requires_non_empty_evidence():
    with pytest.raises(ValidationError):
        _finding(evidence={})


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_finding_confidence_in_unit_interval(bad):
    with pytest.raises(ValidationError):
        _finding(confidence=bad)


def test_finding_defaults_status_needs_review():
    assert _finding().status == "needs_review"


def test_context_defaults_match_hld_parameters():
    p = Context(batch_id="b_1").params
    assert p.min_description_tokens == 3
    assert p.dup_similarity_threshold == 0.88
    assert p.ai_uncertain_band == (0.75, 0.88)
    assert p.chunk_size == 50
    assert set(Context(batch_id="b_1").reference.allowed_uom) == {
        "EA", "PC", "BOX", "KG", "M", "L", "SET", "PR"}


def test_record_validates_brief_sample():
    rows = json.loads((FIXTURES / "brief-sample-input.json").read_text())
    rec = Record(row_number=1, record_key="ERP-A:1001", raw=rows[0], norm=NormView(), **rows[0])
    assert rec.manufacturer == "SKF"
    assert rec.unit_of_measure == "EA"
