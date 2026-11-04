"""Runs registered checks deterministically (LLD 02 3.1, 3.11)."""
import importlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dqa.checks.registry import Scope, list_rules
from dqa.models import Context, Finding, Record

log = logging.getLogger("dqa.checks.engine")


@dataclass(frozen=True)
class RuleError:
    rule_id: str
    rule_version: str
    error: Exception


def load_all() -> None:
    """Import rule modules so they register; heuristics is optional until it exists."""
    importlib.import_module("dqa.checks.rules")
    try:
        importlib.import_module("dqa.checks.heuristics")
    except ModuleNotFoundError as e:
        if e.name != "dqa.checks.heuristics":
            raise


def run_checks(records: Sequence[Record], ctx: Context, scope: Scope | None = None,
               on_error: Callable[[RuleError], None] | None = None) -> list[Finding]:
    load_all()
    out: list[Finding] = []
    for spec in list_rules(scope):
        try:
            out.extend(spec.fn(records, ctx))
        except Exception as e:  # a failing rule must not suppress other rules' findings
            # ponytail: chunk-failed marking/retry belongs to the worker (module 06).
            log.exception("rule_error rule_id=%s rule_version=%s", spec.rule_id,
                          spec.rule_version)
            if on_error:
                on_error(RuleError(spec.rule_id, spec.rule_version, e))
    row = {r.record_key: r.row_number for r in records}
    return sorted(out, key=lambda f: (row.get(f.record_key, 0), f.rule_id, f.dedupe_key))
