import json
from pathlib import Path

import pytest

from dqa.checks.heuristics.weak_description import weak_description
from dqa.models import Context, IssueType, Record, Severity, Source

CTX = Context(batch_id="b_1")


@pytest.mark.parametrize("desc", ["valve", "SKF Bearing 6205 ZZ", "Hex bolt M8 zinc"])
def test_valve_flagged_and_good_description_not(rec, desc):
    out = weak_description([rec(desc=desc)], CTX)
    assert bool(out) == (desc == "valve")


def test_valve_hits_all_three_triggers(rec):
    (f,) = weak_description([rec(desc="valve")], CTX)
    assert f.issue_type == IssueType.WEAK_DESCRIPTION and f.source == Source.HEURISTIC
    assert f.evidence["triggers"] == ["T1", "T2", "T3"]
    assert f.confidence == 0.9 and f.severity == Severity.MEDIUM


def test_single_trigger_is_low_and_0_7(rec):
    # 4 tokens, not all generic, but no digit -> only T3
    (f,) = weak_description([rec(desc="SKF Bearing Deep Groove")], CTX)
    assert f.evidence["triggers"] == ["T3"]
    assert f.confidence == 0.7 and f.severity == Severity.LOW


def test_blank_description_not_flagged(rec):
    assert weak_description([rec(desc="  ")], CTX) == []
    assert weak_description([rec(desc=None)], CTX) == []


def test_threshold_comes_from_params(rec):
    ctx = Context(batch_id="b", params={"min_description_tokens": 5})
    (f,) = weak_description([rec(desc="Hex bolt M8")], ctx)
    assert f.evidence["triggers"] == ["T1"]


def test_brief_1001_is_flagged_documented_behaviour():  # OQ-101 / OQ-222
    rows = json.loads((Path(__file__).parents[2] / "fixtures/brief-sample-input.json").read_text())
    recs = [Record(row_number=i + 1, record_key=f"{r['source_system']}:{r['item_id']}", raw=r, **r)
            for i, r in enumerate(rows)]
    out = weak_description(recs, CTX)
    assert [f.item_id for f in out] == ["1001"]


def test_input_not_mutated_and_deterministic(rec):
    r = rec(desc="valve")
    before = r.model_dump()
    a = weak_description([r], CTX)
    b = weak_description([r], CTX)
    assert r.model_dump() == before and a == b
