# LLD 02 — Rule Engine (Deterministic Checks)

**Status:** DRAFT. HLD refs: FR-2, FR-3, FR-4, FR-9; §2.2 Rule Engine; §6.1 step 3; §6.2; §6.3; §6.8; maintainability NFR ("new rule without touching the engine").
Shared models: [LLD.md](../LLD.md).

## 1. Purpose
Produce certain findings (confidence is a constant) from records using pure functions registered in a rule registry, so a new rule is added without changing the engine.

## 2. Scope
- In: rule registry, `Context`, the three deterministic rules (`missing_part_number`, `unsupported_uom`, `duplicate_item_id`), severity policy lookup, finding construction, `dedupe_key`.
- Out: row validation findings (module 01), heuristics (03), explanation wording rules (09), persistence (05/06).

## 3. Detailed explanation

### 3.1 Responsibilities
1. Register checks with `rule_id`, `rule_version`, `issue_type`, `layer`, `scope`, `enabled`.
2. Execute applicable checks over records/chunks/batches.
3. Return draft `Finding` objects with evidence, `suggested_action`, `source = deterministic_rule`.
4. Guarantee determinism: same input + same `ctx` ⇒ identical findings (ordered by `(row_number, rule_id)`).

### 3.2 Inputs and outputs

| | |
|---|---|
| Input | `records: Sequence[Record]` (chunk, or whole batch for batch-scope rules), `ctx: Context` |
| Output | `list[Finding]` (not yet persisted; `finding_id`/`created_at` assigned by the writer) |

### 3.3 Registry design
```
RuleSpec:
  rule_id        str      # stable; e.g. "missing_part_number"
  rule_version   str      # semver; bump on any behaviour change
  issue_type     enum
  layer          "deterministic" | "heuristic"
  scope          "record" | "batch"   # record: runs per chunk; batch: runs in the batch-scope pass (OQ-119)
  fn             check(records, ctx) -> list[Finding]
  enabled_param  optional config key to disable
```
Registration is by decorator at import of modules under `checks/`; the engine iterates the registry — adding a rule is adding a file. The registry is loaded once and exposes `list_rules(scope)` to the worker. Rules never call the database or network; any lookup data comes through `ctx.reference`.

`rule_id` ↔ `issue_type` map: `row_validation → malformed_row|incomplete_row`, `missing_part_number`, `unsupported_uom`, `duplicate_item_id`, `weak_description`, `possible_duplicate`, `category_mismatch → category_mismatch_candidate`, `conflicting_source_values`, `suspicious_content` (the HLD example uses `category_mismatch` for rule_id and `category_mismatch_candidate` for issue type).

### 3.4 Rules (step by step)

**R1 `missing_part_number` (FR-2), scope record, v1.0.0**
1. If `is_blank(manufacturer)` → no finding (nothing to compare).
2. If `not is_blank(manufacturer)` and `is_blank(manufacturer_part_number)` → finding.
3. Severity = policy(`missing_part_number`) = `medium` (HLD 6.1). Confidence = **1.0** (HLD) — brief expects 0.95 (OQ-100); the value is a registry constant, not hard-coded in the function.
4. Evidence: `{"manufacturer": <raw>, "manufacturer_part_number": <raw>}`. Explanation key `missing_part_number` → "Manufacturer 'SKF' is present but manufacturer part number is blank." Action: "Request manufacturer part number from the source owner." (wording from brief).
5. `suggested_value = null` (no invention of part numbers; supplier enrichment is a future enhancement).

**R2 `unsupported_uom` (FR-3), scope record, v1.0.0**
1. If `is_blank(unit_of_measure)` → no finding here (blank is handled by `incomplete_row` if required; whether blank should also be "suspicious" is OQ-108).
2. `k = norm.uom_key` (trim, upper, strip trailing `.`).
3. If `k ∈ allowed_uom` → no finding.
4. Else look up `uom_aliases[k]` (case-insensitive; e.g. `EACH → EA`, `EA. → EA`). Mapped value must be in `allowed_uom`; if so → no finding (normalised value is recorded for matching only; the raw value is untouched).
5. Else → finding, severity `high`, confidence 1.0; evidence `{"unit_of_measure": <raw>, "normalised": k, "allowed_uom": [...], "allowed_uom_version": n}`; action "Confirm the correct unit of measure with the source owner."
6. Alias map content (is `pcs → PC`? is `EACH` supported?) and the meaning of "suspicious" in FR-3 are not defined → OQ-108.

**R3 `duplicate_item_id` (FR-4), scope batch, v1.0.0**
1. Group records by `(source_system, item_id)` using trimmed, case-sensitive comparison; skip groups where either part is blank (OQ-112 confirms case/whitespace policy).
2. For every group with ≥2 members → one finding **per member** (each row needs its own reviewable item), severity `high`, confidence 1.0.
3. Evidence: `{"source_system", "item_id", "occurrences": [{"row_number", "record_key"}...]}`.
4. Input comes from an indexed SQL pass over `record_snapshot` (module 06 batch-scope step), not from an in-memory chunk, because duplicates may be in different chunks (OQ-119).

### 3.5 Severity and confidence
`ctx.reference.severity_policy` maps `issue_type → severity`. HLD says "policy table by issue type and business impact" but gives neither the table nor the impact input (OQ-106). PROVISIONAL defaults: `missing_part_number=medium`, `unsupported_uom=high`, `duplicate_item_id=high` (stated in HLD 6.1); others in modules 01/03. Confidence for deterministic rules is a per-rule constant exposed in the registry.

### 3.6 `dedupe_key` (OQ-109)
HLD-PDF 4.7 gives uniqueness `(batch_id, record_key, issue_type, rule_id, rule_version)`; 6.5 has one `dedupe_key UNIQUE` column. PROVISIONAL: `dedupe_key = SHA-256("{batch_id}|{record_key}|{issue_type}|{rule_id}|{rule_version}|{discriminator}")`, `discriminator = ""` except pair findings (module 03: the counterpart `record_key`).

### 3.7 API contracts
None (library). The worker calls `engine.run(records, ctx, scope)` and receives findings. Registry listing is exposed to operators via a read-only admin endpoint in module 04 (`GET /api/v1/admin/rules`) — PROVISIONAL, requires Platform Admin config role and is not in HLD-PDF 6.4.

### 3.8 Walk-through: brief sample

| Record | R1 | R2 | R3 | Result |
|---|---|---|---|---|
| 1001 (`bearing`, SKF, MPN blank, EA) | **fires** (medium, 1.0) | EA allowed → none | unique | 1 finding |
| 1002 (SKF, `6205-ZZ`, EA) | MPN present → none | none | unique | 0 findings |

Produced vs brief: `missing_part_number` for 1001, severity `medium` ✔, explanation/action ✔, `source = deterministic_rule` ✔, **confidence 1.0 vs 0.95 ✘** (OQ-100). Module 03 adds further findings (see its walk-through).

### 3.9 Database interactions
None inside the rule functions. Workers persist findings via repository: `INSERT … ON CONFLICT (dedupe_key) DO NOTHING`. Transaction/consistency: each chunk's findings are inserted in one transaction by the rule worker (module 06); re-delivery is a no-op via `dedupe_key`. Audit: the worker writes one `audit_event` per finding created (module 05, hash-chained); the rule functions themselves have no side effects. Batch-scope rule input is read through `record_snapshot` index `(batch_id, source_system, item_id)`.

### 3.10 External dependencies
Reference data (`allowed_uom`, `uom_aliases`, `severity_policy`) via `ctx`, versioned; explanation templates (module 09).

### 3.11 Error handling
A rule raising an exception is isolated: engine catches per rule per chunk, logs `rule_error{rule_id, rule_version}` and a security-neutral `component=rule_engine`, marks the chunk `failed` after retries (module 06). Other rules' findings for the chunk are still written (a failing rule must not suppress other results). Invalid reference data (e.g. empty `allowed_uom`) fails fast at `ctx` construction, not per record.

### 3.12 Retry strategy
Rules are pure and idempotent: retry is the worker's chunk retry (3×, delayed re-queue); duplicates are prevented by `dedupe_key`.

### 3.13 Edge cases
`each`/`EACH`/`ea.` aliasing; manufacturer present as `N/A` (blank by A-105 → R1 silent); MPN `0` or `-` (not blank → no finding; plausibility check is out of v1 scope); UoM with trailing spaces; item_id differing only by case (not a duplicate unless OQ-112 says otherwise); three rows sharing one key → 3 findings each listing all rows.

### 3.14 Logging
Per run: `rules_executed`, `findings_by_rule`, `duration_ms` per rule. No raw values in logs.

### 3.15 Security
No I/O ⇒ no egress. `evidence` stores raw values (they may contain PII by accident); API masks nothing here but responses are role-scoped; logs exclude evidence.

### 3.16 Performance
O(n) per chunk. Batch-scope duplicate-id pass is a single indexed `GROUP BY … HAVING count(*) > 1` per batch. Part of the 10k < 30 s budget (with 01 and 03).

### 3.17 Test requirements
Unit (positive/negative/edge for every rule): null, whitespace, `N/A`, Unicode, alias, unknown UoM, duplicates across chunks. Property: determinism and idempotence of `engine.run`. Invariant: input deep-equal before/after; every finding has non-empty `explanation`, `evidence`, `source`. Golden: brief sample → `missing_part_number` for 1001 (assert issue type, severity, action, source; confidence assertion blocked on OQ-100). Registry test: adding a dummy rule module requires no engine change. Coverage ≥85% on `checks/`.

## 4. Architecture decisions
D-02-1 pure-function + registry (HLD-defined); D-02-2 one finding per duplicate member; D-02-3 confidence is registry data (so OQ-100 is a one-line change); ADR-009 for persistence.

## 5. Dependencies
01 (Record/norm), 05 (persistence), 06 (scheduling), 09 (templates), 10 (reference data).

## 6. Risks and edge cases
Policy-table gaps (OQ-106); alias map incomplete → false `unsupported_uom` (noise); chunk/batch mismatch for duplicates if OQ-119 is ignored.

## 7. Related documents
[LLD.md](../LLD.md) · [01](01-ingestion-validator.md) · [03](03-heuristic-engine.md) · [05](05-data-layer.md) · [06](06-queue-and-workers.md) · [Testing](../../testing/TESTING_AND_EVALUATION.md)

## Open questions (this module)

| ID | Question |
|---|---|
| OQ-100 | `missing_part_number` confidence: HLD says deterministic = 1.0; brief expects 0.95. Which is authoritative? |
| OQ-106 | Complete severity policy table and the "business impact" input; severities for `weak_description`, `possible_duplicate`, `conflicting_source_values`, `malformed_row`, `incomplete_row`, `suspicious_content`. |
| OQ-108 | UoM alias map contents; meaning of "suspicious" UoM (FR-3); treatment of blank UoM. |
| OQ-109 | `dedupe_key` derivation (4.7 vs 6.5), including pair findings. |
| OQ-112 | `duplicate_item_id`: case/whitespace sensitivity; flag every occurrence or only later ones. |
