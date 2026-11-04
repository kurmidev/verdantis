import copy

from checks_helpers import CTX, rec

from dqa.checks import rules
from dqa.checks.registry import list_rules
from dqa.models import Context, IssueType, Reference, Severity, Source


def _run(fn, records, ctx=CTX):
    return fn(records, ctx)


# --- R1 missing_part_number ---
def test_r1_fires_when_manufacturer_present_and_mpn_blank():
    out = _run(rules.missing_part_number, [rec(item_id="1001", desc="bearing", mpn="")])
    assert len(out) == 1
    f = out[0]
    assert f.issue_type == IssueType.MISSING_PART_NUMBER
    assert f.severity == Severity.MEDIUM and f.source == Source.DETERMINISTIC_RULE
    assert f.confidence == rules.RULE_CONFIDENCE["missing_part_number"] == 1.0
    assert f.explanation == "Manufacturer 'SKF' is present but manufacturer part number is blank."
    assert f.evidence == {"manufacturer": "SKF", "manufacturer_part_number": ""}
    assert f.rule_id == "missing_part_number" and f.rule_version == "1.0.0"


def test_r1_blank_variants_of_mpn():
    for mpn in (None, "", "  ", "N/A", "null"):
        assert len(_run(rules.missing_part_number, [rec(mpn=mpn)])) == 1


def test_r1_silent_when_manufacturer_blank_or_mpn_present():
    assert _run(rules.missing_part_number, [rec(mfr="N/A", mpn="")]) == []
    assert _run(rules.missing_part_number, [rec(mfr=None, mpn=None)]) == []
    assert _run(rules.missing_part_number, [rec(mpn="6205-ZZ")]) == []
    assert _run(rules.missing_part_number, [rec(mpn="0")]) == []  # plausibility out of v1


# --- R2 unsupported_uom ---
def test_r2_allowed_uom_ok_case_insensitive_and_trailing_dot():
    for uom in ("EA", "ea", " Ea. ", "BOX"):
        assert _run(rules.unsupported_uom, [rec(uom=uom)]) == []


def test_r2_alias_map_first():
    ctx = Context(batch_id="b", reference=Reference(uom_aliases={"EACH": "EA", "pcs": "PC"}))
    assert _run(rules.unsupported_uom, [rec(uom="each"), rec(uom="PCS")], ctx) == []


def test_r2_unknown_flagged_high_with_evidence():
    out = _run(rules.unsupported_uom, [rec(item_id="7", uom="DOZEN")])
    assert len(out) == 1 and out[0].severity == Severity.HIGH
    assert out[0].evidence["unit_of_measure"] == "DOZEN"
    assert out[0].evidence["normalised"] == "DOZEN"
    assert "EA" in out[0].evidence["allowed_uom"]


def test_r2_alias_to_disallowed_value_still_flagged():
    ctx = Context(batch_id="b", reference=Reference(uom_aliases={"DOZ": "DZ"}))
    assert len(_run(rules.unsupported_uom, [rec(uom="doz")], ctx)) == 1


def test_r2_blank_uom_no_finding():  # PROVISIONAL(OQ-108)
    assert _run(rules.unsupported_uom, [rec(uom=None), rec(uom=" ")]) == []


# --- R3 duplicate_item_id ---
def test_r3_one_finding_per_member_high():
    rs = [rec(row=1, item_id="9", key="ERP-A:9"), rec(row=2, item_id="9", key="ERP-A:9#2"),
          rec(row=3, item_id="10")]
    out = _run(rules.duplicate_item_id, rs)
    assert sorted(f.record_key for f in out) == ["ERP-A:9", "ERP-A:9#2"]
    assert all(f.severity == Severity.HIGH for f in out)
    assert len({f.dedupe_key for f in out}) == 2
    occ = out[0].evidence["occurrences"]
    assert [o["row_number"] for o in occ] == [1, 2]


def test_r3_three_rows_three_findings():
    rs = [rec(row=i, item_id="9", key=f"ERP-A:9#{i}") for i in (1, 2, 3)]
    assert len(_run(rules.duplicate_item_id, rs)) == 3


def test_r3_different_system_or_case_not_duplicate():  # PROVISIONAL(OQ-112)
    rs = [rec(row=1, item_id="9", source="ERP-A"), rec(row=2, item_id="9", source="ERP-B"),
          rec(row=3, item_id="a1"), rec(row=4, item_id="A1", key="ERP-A:A1")]
    assert _run(rules.duplicate_item_id, rs) == []


def test_r3_whitespace_trimmed_and_blank_skipped():
    rs = [rec(row=1, item_id="9", key="a"), rec(row=2, item_id=" 9 ", key="b"),
          rec(row=3, item_id="", key="c"), rec(row=4, item_id="  ", key="d")]
    out = _run(rules.duplicate_item_id, rs)
    assert sorted(f.record_key for f in out) == ["a", "b"]


# --- cross-cutting ---
def test_rules_registered_with_scope_and_version():
    by_id = {s.rule_id: s for s in list_rules()}
    assert by_id["missing_part_number"].scope == "record"
    assert by_id["unsupported_uom"].scope == "record"
    assert by_id["duplicate_item_id"].scope == "batch"
    assert all(by_id[i].rule_version == "1.0.0" for i in
               ("missing_part_number", "unsupported_uom", "duplicate_item_id"))


def test_rules_do_not_mutate_input_and_are_deterministic():
    rs = [rec(row=1, item_id="9", mpn="", uom="x"), rec(row=2, item_id="9")]
    before = copy.deepcopy(rs)
    a = [f for fn in (rules.missing_part_number, rules.unsupported_uom, rules.duplicate_item_id)
         for f in fn(rs, CTX)]
    b = [f for fn in (rules.missing_part_number, rules.unsupported_uom, rules.duplicate_item_id)
         for f in fn(rs, CTX)]
    assert rs == before and a == b


def test_severity_policy_override_from_reference():
    ctx = Context(batch_id="b", reference=Reference(
        severity_policy={IssueType.MISSING_PART_NUMBER: Severity.HIGH}))
    assert _run(rules.missing_part_number, [rec(mpn="")], ctx)[0].severity == Severity.HIGH
