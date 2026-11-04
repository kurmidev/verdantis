import logging

from checks_helpers import CTX, rec

from dqa.checks import engine, registry
from dqa.models import IssueType


def test_run_checks_sorted_by_row_then_rule_and_scoped():
    rs = [rec(row=2, item_id="9", mpn="", uom="X", key="a"),
          rec(row=1, item_id="9", key="b")]
    rec_scope = engine.run_checks(rs, CTX, "record")
    assert [(f.record_key, f.rule_id) for f in rec_scope] == [
        ("a", "missing_part_number"), ("a", "unsupported_uom")]
    batch_scope = engine.run_checks(rs, CTX, "batch")
    assert [f.record_key for f in batch_scope] == ["b", "a"]
    all_scopes = engine.run_checks(rs, CTX)
    assert len(all_scopes) == len(rec_scope) + len(batch_scope)


def test_run_checks_deterministic():
    rs = [rec(row=i, item_id=str(i % 2), mpn="") for i in range(1, 6)]
    assert engine.run_checks(rs, CTX) == engine.run_checks(rs, CTX)


def test_failing_rule_does_not_suppress_others(caplog):
    saved = dict(registry._REGISTRY)
    try:
        @registry.rule("boom", "1.0.0", IssueType.WEAK_DESCRIPTION,
                       layer="heuristic", scope="record")
        def boom(records, ctx):
            raise RuntimeError("x")

        errors = []
        with caplog.at_level(logging.ERROR):
            out = engine.run_checks([rec(mpn="")], CTX, "record", on_error=errors.append)
        assert any(f.rule_id == "missing_part_number" for f in out)
        assert [e.rule_id for e in errors] == ["boom"]
        assert "rule_error" in caplog.text
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


def test_new_rule_needs_no_engine_change():
    saved = dict(registry._REGISTRY)
    try:
        @registry.rule("dummy", "0.1.0", IssueType.WEAK_DESCRIPTION,
                       layer="heuristic", scope="record")
        def dummy(records, ctx):
            return []

        assert "dummy" in [s.rule_id for s in registry.list_rules("record")]
        assert engine.run_checks([rec()], CTX, "record") == []
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)
