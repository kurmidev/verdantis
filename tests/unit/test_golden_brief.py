import copy
import json
from pathlib import Path

import pytest

from dqa.checks import engine
from dqa.checks.templates import FORBIDDEN
from dqa.models import Context, NormView, Record
from dqa.normalize import normalize_mpn, normalize_uom, tokenize

FIX = Path(__file__).parent.parent / "fixtures"


def _records():
    rows = json.loads((FIX / "brief-sample-input.json").read_text())
    return [
        Record(row_number=i, record_key=f"{r['source_system']}:{r['item_id']}", raw=r,
               norm=NormView(description_tokens=tokenize(r["item_description"]),
                             mpn_key=normalize_mpn(r["manufacturer_part_number"]),
                             uom_key=normalize_uom(r["unit_of_measure"])), **r)
        for i, r in enumerate(rows, 1)
    ]


def _findings():
    return engine.run_checks(_records(), Context(batch_id="b_1"))


def test_1001_yields_missing_part_number_medium_from_rule():
    f = [x for x in _findings() if x.item_id == "1001" and x.issue_type == "missing_part_number"]
    assert len(f) == 1
    assert f[0].severity == "medium" and f[0].source == "deterministic_rule"
    assert f[0].suggested_action == "Request manufacturer part number from the source owner."


def test_input_unchanged_by_processing():
    recs = _records()
    before = copy.deepcopy(recs)
    engine.run_checks(recs, Context(batch_id="b_1"))
    assert recs == before


def test_every_finding_is_explainable_and_clean():
    out = _findings()
    assert out
    for f in out:
        assert f.explanation and f.evidence and f.suggested_action and f.source
        assert not any(w in f.explanation.lower() + f.suggested_action.lower() for w in FORBIDDEN)


def test_required_set_mode_deterministic_part():
    # Known documented difference (OQ-100): brief expects confidence 0.95, HLD/code says 1.0.
    # Only the deterministic expected finding is checkable here; 1002 category mismatch comes
    # from the heuristic layer (worker C) and is asserted in the heuristics tests.
    expected = json.loads((FIX / "brief-expected-output.json").read_text())[0]
    got = next(x for x in _findings() if x.item_id == "1001" and x.issue_type == expected["issue_type"])
    assert (got.severity, got.source) == (expected["severity"], expected["source"])
    assert got.suggested_action == expected["suggested_action"]
    assert got.confidence != expected["confidence"]  # 1.0 vs 0.95, OQ-100


@pytest.mark.xfail(reason="OQ-12/OQ-432: exact-match vs required-set mode undecided; "
                   "confidence 0.95 vs 1.0 (OQ-100), extras (OQ-101/OQ-222)", strict=False)
def test_exact_match_mode():
    expected = json.loads((FIX / "brief-expected-output.json").read_text())
    got = [(f.item_id, f.issue_type, f.severity, f.confidence) for f in _findings()]
    assert got == [(e["item_id"], e["issue_type"], e["severity"], e["confidence"]) for e in expected]
