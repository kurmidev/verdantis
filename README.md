# Data-Quality Assistant (DQA)

## Purpose
DQA scans uploaded item-master records (JSON/CSV from several ERPs) and produces ranked, explainable **review candidates** for a human data steward: missing part numbers, unsupported units of measure, duplicate IDs, weak descriptions, possible cross-system duplicates and category mismatches. It never changes production data; every finding ends in a human decision, and approved changes leave as a change file.

## Scope
This repository currently holds the **architecture and engineering documentation only**. No application code exists, and none will be written until the documentation is reviewed and approved (see [CLAUDE.md](CLAUDE.md)).

## Detailed explanation

### Status
Documentation complete as a draft, **awaiting user review**. Open decisions are tracked in [docs/project/OPEN_QUESTIONS.md](docs/project/OPEN_QUESTIONS.md); the quality review is [docs/project/DOCUMENTATION_REVIEW.md](docs/project/DOCUMENTATION_REVIEW.md).

### Architecture in one paragraph
Three layers feed one review queue: deterministic rules, heuristics, and an asynchronous AI suggestion layer. Uploads flow through a FastAPI service into queues; rule workers publish findings straight to PostgreSQL; only records the rules cannot settle go to a plain-Python AI task pipeline whose every LLM call goes through one in-process AI access layer (PII masking, budgets, retries) to a single provider, with two model tiers and rule-only degradation when the provider is unavailable. Validators, templates and calibration ensure AI output is schema-valid, grounded and clearly labelled. See [docs/hld/HLD.md](docs/hld/HLD.md).

### Document map
Start at [docs/README.md](docs/README.md) (reading order and full index). Key entry points: [BRD](docs/business/BRD.md) → [HLD](docs/hld/HLD.md) → [LLD](docs/lld/LLD.md) → [AI architecture](docs/ai/AI_ARCHITECTURE.md) → [security](docs/security/SECURITY_AND_GOVERNANCE.md) → [testing](docs/testing/TESTING_AND_EVALUATION.md) → [infra](docs/infra/INFRASTRUCTURE.md) → [operations](docs/operations/OBSERVABILITY_AND_OPERATIONS.md) → [decisions](docs/project/ARCHITECTURE_DECISIONS.md) → [roadmap](docs/project/IMPLEMENTATION_PLAN.md) and [tasks](docs/project/TASK_BREAKDOWN.md).

## Architecture decisions
See [docs/project/ARCHITECTURE_DECISIONS.md](docs/project/ARCHITECTURE_DECISIONS.md) (ADR-001..016).

## Dependencies
Source input: `docs/HLD — Enterprise Item Data-Quality Assistant.pdf`; sample data in `docs/testing/fixtures/`.

## Risks and edge cases
See [docs/project/RISKS_AND_DEPENDENCIES.md](docs/project/RISKS_AND_DEPENDENCIES.md).

## Related documents
[CLAUDE.md](CLAUDE.md) · [docs/README.md](docs/README.md)

## Implementation status
Started 2026-11-04. Done (test-first, `uv run pytest`): P0 scaffold and shared models; P1 pure-logic core, namely normalisation, ingest/row validation/record keys, input scanner, rule registry, rules `missing_part_number`/`unsupported_uom`/`duplicate_item_id`, heuristics `weak_description`/`possible_duplicate`/`category_mismatch_candidate`/`conflicting_source_values`, and the golden brief test (required-set mode; exact-match is xfail pending OQ-12). Next: P2 (data layer, API, queue). Steward UI is out of scope.

Access: **open, no sign-in** (ADR-023). Run it only on a private network; see `docs/security/SECURITY_AND_GOVERNANCE.md` section 3.2.
