"""Rule registry (LLD 02 3.3): adding a rule = adding a decorated function; the engine is untouched."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from dqa.models import Context, Finding, IssueType, Record

Layer = Literal["deterministic", "heuristic"]
Scope = Literal["record", "batch"]
CheckFn = Callable[[Sequence[Record], Context], list[Finding]]


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    rule_version: str
    issue_type: IssueType
    layer: Layer
    scope: Scope
    fn: CheckFn


_REGISTRY: dict[str, RuleSpec] = {}


def rule(
    rule_id: str, rule_version: str, issue_type: IssueType, *, layer: Layer, scope: Scope
) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        if rule_id in _REGISTRY:
            raise ValueError(f"rule_id already registered: {rule_id}")
        _REGISTRY[rule_id] = RuleSpec(rule_id, rule_version, issue_type, layer, scope, fn)
        return fn

    return deco


def list_rules(scope: Scope | None = None) -> list[RuleSpec]:
    specs = sorted(_REGISTRY.values(), key=lambda s: s.rule_id)
    return [s for s in specs if scope is None or s.scope == scope]


def clear_registry() -> None:  # test helper
    _REGISTRY.clear()
