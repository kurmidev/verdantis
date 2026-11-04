import pytest

from dqa.checks import registry
from dqa.checks.registry import RuleSpec, clear_registry, list_rules, rule
from dqa.models import Context, IssueType


@pytest.fixture(autouse=True)
def _isolated():
    saved = dict(registry._REGISTRY)  # other modules register rules at import time
    clear_registry()
    yield
    clear_registry()
    registry._REGISTRY.update(saved)


def test_register_and_list_by_scope():
    @rule("r1", "1.0.0", IssueType.MISSING_PART_NUMBER, layer="deterministic", scope="record")
    def r1(records, ctx):
        return []

    @rule("r2", "1.0.0", IssueType.DUPLICATE_ITEM_ID, layer="deterministic", scope="batch")
    def r2(records, ctx):
        return []

    assert [s.rule_id for s in list_rules("record")] == ["r1"]
    assert [s.rule_id for s in list_rules("batch")] == ["r2"]
    assert isinstance(list_rules()[0], RuleSpec)
    assert r1([], Context(batch_id="b")) == []


def test_duplicate_rule_id_rejected():
    @rule("r1", "1.0.0", IssueType.MISSING_PART_NUMBER, layer="deterministic", scope="record")
    def a(records, ctx):
        return []

    with pytest.raises(ValueError):
        @rule("r1", "1.0.1", IssueType.MISSING_PART_NUMBER, layer="deterministic", scope="record")
        def b(records, ctx):
            return []
