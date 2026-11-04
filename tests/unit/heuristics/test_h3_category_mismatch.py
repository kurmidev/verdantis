import pytest

from dqa.checks.heuristics.category_mismatch import category_mismatch
from dqa.models import Context, IssueType, Severity, Source

CTX = Context(batch_id="b_1")


def test_brief_1002_bearing_under_electrical(rec):
    r = rec(item_id="1002", source="ERP-B", cat="Electrical")
    (f,) = category_mismatch([r], CTX)
    assert f.issue_type == IssueType.CATEGORY_MISMATCH_CANDIDATE
    assert f.severity == Severity.LOW and f.confidence == 0.70 and f.source == Source.HEURISTIC
    assert f.suggested_value == {"category": "Mechanical"}
    assert f.evidence["item_description"] == "SKF Bearing 6205 ZZ"
    assert f.evidence["category"] == "Electrical"
    assert f.suggested_action == "Review category assignment before approval."


def test_matching_category_no_finding(rec):
    assert category_mismatch([rec(cat="Mechanical")], CTX) == []
    assert category_mismatch([rec(cat="mechanical ")], CTX) == []


@pytest.mark.parametrize("cat", [None, "", "N/A"])
def test_blank_category_no_finding(rec, cat):
    assert category_mismatch([rec(cat=cat)], CTX) == []


def test_no_keyword_no_finding(rec):
    assert category_mismatch([rec(desc="Widget 42", cat="Electrical")], CTX) == []


def test_ambiguous_keywords_lower_confidence_no_suggested_value(rec):
    ctx = Context(batch_id="b", reference={"category_keywords": {"bearing": "Mechanical",
                                                                 "cable": "Electrical"}})
    (f,) = category_mismatch([rec(desc="Bearing cable guide", cat="Plumbing")], ctx)
    assert f.confidence == 0.6 and f.suggested_value is None


def test_reference_map_overrides_default(rec):
    ctx = Context(batch_id="b", reference={"category_keywords": {"widget": "Hardware"}})
    assert category_mismatch([rec(desc="SKF Bearing", cat="Electrical")], ctx) == []
    (f,) = category_mismatch([rec(desc="Widget", cat="Electrical")], ctx)
    assert f.suggested_value == {"category": "Hardware"}
