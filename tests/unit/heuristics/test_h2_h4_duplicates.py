import json
import logging
import time
from pathlib import Path

from dqa.checks.heuristics.conflicting_values import conflicting_source_values
from dqa.checks.heuristics.possible_duplicate import possible_duplicate
from dqa.models import Context, IssueType, Record, Source

CTX = Context(batch_id="b_1")


def test_exact_mpn_formats_block_together_across_systems(rec):
    recs = [rec("1", "ERP-A", mpn="6205-ZZ"), rec("2", "ERP-B", mpn="6205 ZZ"),
            rec("3", "ERP-C", mpn="6205ZZ")]
    out = possible_duplicate(recs, CTX)
    assert len(out) == 3  # one finding per cross-system pair
    assert {f.confidence for f in out} == {0.9}
    f = out[0]
    assert f.issue_type == IssueType.POSSIBLE_DUPLICATE and f.source == Source.HEURISTIC
    assert f.record_key == "ERP-A:1" and f.evidence["counterpart_record_key"] == "ERP-B:2"
    assert f.evidence["match"] == "exact_mpn" and f.evidence["mpn_key"] == "6205ZZ"
    assert "6205-ZZ" in str(f.evidence["fields"])  # raw values shown as evidence


def test_same_system_pair_not_flagged(rec):
    assert possible_duplicate([rec("1", "ERP-A"), rec("2", "ERP-A")], CTX) == []


def test_manufacturer_alias_blocks_together(rec):
    ctx = Context(batch_id="b", reference={"manufacturer_aliases": {"s.k.f.": "skf"}})
    out = possible_duplicate([rec("1", "ERP-A", mfr="SKF"), rec("2", "ERP-B", mfr="S.K.F.")], ctx)
    assert len(out) == 1


def test_blank_manufacturer_excluded(rec):
    assert possible_duplicate([rec("1", "ERP-A", mfr=""), rec("2", "ERP-B", mfr="")], CTX) == []


def test_description_similarity_within_manufacturer(rec):
    a = rec("1", "ERP-A", desc="SKF Deep Groove Ball Bearing 6205 ZZ", mpn=None)
    b = rec("2", "ERP-B", desc="Deep Groove Ball Bearing SKF 6205 ZZ", mpn=None)
    (f,) = possible_duplicate([a, b], CTX)
    assert f.confidence == 0.7 and f.evidence["match"] == "description_similarity"
    assert f.evidence["similarity"] >= 0.88


def test_different_manufacturer_not_compared(rec):
    a = rec("1", "ERP-A", desc="Deep Groove Ball Bearing 6205", mfr="SKF", mpn=None)
    b = rec("2", "ERP-B", desc="Deep Groove Ball Bearing 6205", mfr="FAG", mpn=None)
    assert possible_duplicate([a, b], CTX) == []


def test_brief_sample_1001_1002_not_duplicates():
    # token_set_ratio would score 100 here ("bearing" is a subset); token_sort_ratio must not.
    rows = json.loads((Path(__file__).parents[2] / "fixtures/brief-sample-input.json").read_text())
    recs = [Record(row_number=i + 1, record_key=f"{r['source_system']}:{r['item_id']}", raw=r, **r)
            for i, r in enumerate(rows)]
    assert possible_duplicate(recs, CTX) == []


def test_does_not_mutate_input(rec):
    recs = [rec("1", "ERP-A"), rec("2", "ERP-B")]
    before = [r.model_dump() for r in recs]
    possible_duplicate(recs, CTX)
    assert [r.model_dump() for r in recs] == before


def test_scale_20k_records_is_fast(rec):
    recs = []
    for i in range(20_000):
        mfr = f"mfr{i % 40}"
        recs.append(rec(str(i), "ERP-A" if i % 2 else "ERP-B", desc=f"part{i} widget size{i * 7}",
                        mfr=mfr, mpn=f"X{i}", row=i + 1))
    t = time.perf_counter()
    possible_duplicate(recs, CTX)
    assert time.perf_counter() - t < 60  # generous; guards against O(n^2) over the whole batch


def test_oversized_block_uses_index_and_warns_when_over_hard_cap(rec, caplog, monkeypatch):
    from dqa.checks.heuristics import possible_duplicate as mod

    monkeypatch.setattr(mod, "MAX_BLOCK_SIZE", 10)
    monkeypatch.setattr(mod, "HARD_BLOCK_CAP", 30)
    small = [rec(str(i), "ERP-A" if i % 2 else "ERP-B", desc=f"alpha{i} gamma{i}", mpn=None,
                 row=i + 1) for i in range(20)]
    dup = [rec("d1", "ERP-A", desc="Deep Groove Ball Bearing 6205 ZZ", mpn=None, row=99),
           rec("d2", "ERP-B", desc="Deep Groove Ball Bearing 6205 ZZ", mpn=None, row=100)]
    out = possible_duplicate(small + dup, CTX)  # 22 > MAX_BLOCK_SIZE: inverted-index path
    assert [f.record_key for f in out] == ["ERP-A:d1"]
    huge = [rec(str(i), "ERP-A" if i % 2 else "ERP-B", desc=f"a{i}", mpn=None, row=i + 1)
            for i in range(31)]
    with caplog.at_level(logging.WARNING):
        assert possible_duplicate(huge, CTX) == []
    assert "block_too_large" in caplog.text


def test_conflicting_values_across_systems(rec):
    a = rec("1", "ERP-A", cat="Mechanical", uom="EA", mpn="6205-ZZ")
    b = rec("2", "ERP-B", cat="Electrical", uom="EA", mpn="6205 ZZ")
    out = conflicting_source_values([a, b], CTX)
    assert len(out) == 2 and {f.record_key for f in out} == {"ERP-A:1", "ERP-B:2"}
    f = out[0]
    assert f.issue_type == IssueType.CONFLICTING_SOURCE_VALUES and f.confidence == 0.9
    assert f.evidence["conflicts"]["category"] == {"ERP-A": "Mechanical", "ERP-B": "Electrical"}
    assert "unit_of_measure" not in f.evidence["conflicts"]


def test_conflicting_values_none_when_equal_or_single_system(rec):
    a = rec("1", "ERP-A", cat="Mechanical", mpn="6205-ZZ")
    b = rec("2", "ERP-B", cat="mechanical", mpn="6205ZZ")
    assert conflicting_source_values([a, b], CTX) == []
    assert conflicting_source_values([a, rec("3", "ERP-A", cat="Electrical", mpn="6205ZZ")], CTX) == []


def test_conflicting_uom_uses_alias_map(rec):
    ctx = Context(batch_id="b", reference={"uom_aliases": {"EACH": "EA"}})
    a = rec("1", "ERP-A", uom="EACH", mpn="X1")
    b = rec("2", "ERP-B", uom="EA", mpn="X1")
    assert conflicting_source_values([a, b], ctx) == []
