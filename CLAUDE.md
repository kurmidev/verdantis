# CLAUDE.md — Project rules for the Data-Quality Assistant (DQA)

## Purpose
Working rules for any Claude Code session in this repository. The architecture is documented in `docs/`. On 2026-11-04 the user instructed "start the implementation" (treated as approval of the documented architecture, with provisional choices and open questions still governed by section 3). Implementation proceeds phase by phase per [docs/project/IMPLEMENTATION_PLAN.md](docs/project/IMPLEMENTATION_PLAN.md). Read this file before touching anything.

## Scope
Applies to every file in the repo. The documentation lives in [docs/](docs/README.md); the single source input is the original HLD PDF (`docs/HLD — Enterprise Item Data-Quality Assistant.pdf`).

## Detailed explanation

### 1. Approval gate (status: passed 2026-11-04 by user instruction "start the implementation")
Before that instruction the following were forbidden; they remain forbidden for anything outside the current phase's tasks, and for architectural changes without an ADR (section 2):
- Do **not** write application source code, API implementations or agents.
- Do **not** create database migrations, Terraform/Helm/compose/CI files, Dockerfiles.
- Do **not** install dependencies or create/modify dependency manifests (`pyproject.toml`, `package.json`, lock files).
- Allowed now: code, manifests and tests for the tasks of the phase currently being implemented (P0, P1 first), written test-first. Infrastructure code (Terraform/Helm), migrations and agents wait for their phase.
After approval, implementation proceeds module by module following [docs/project/TASK_BREAKDOWN.md](docs/project/TASK_BREAKDOWN.md) and the acceptance criteria in each LLD.

### 2. Architecture changes need an ADR
Any change to an architectural decision (technology, data model, workflow, security control) must first be written up in [docs/project/ARCHITECTURE_DECISIONS.md](docs/project/ARCHITECTURE_DECISIONS.md) (new or superseding ADR) and approved by the user, then reflected in the affected docs.

### 2b. Open access
No authentication or roles (ADR-023, user decision 2026-11-04). Do not add login, tokens or role checks without a new ADR; keep the `Authenticator` slot.

### 3. Never invent
Unknown business or technical facts are recorded as **Assumptions (A-xx)** or **Open Questions (OQ-xx)**, never silently decided. The consolidated register is [docs/project/OPEN_QUESTIONS.md](docs/project/OPEN_QUESTIONS.md). Where a provisional choice is needed to keep the design coherent, mark it `PROVISIONAL` and cite the OQ id. Technologies named in the HLD PDF are *proposals*, not user decisions, except those listed as "Decided by user" in the ADRs (custom thin AI gateway realised in-process, simplified minimum-infrastructure AI layer, Unleash, Celery with SQS in prod / ElasticMQ locally / Redis for cache, full-system scope, no UI design).

### 4. Canonical vocabulary
Names are fixed across documents; use them exactly. Authoritative lists: [docs/lld/LLD.md](docs/lld/LLD.md) (tables, keys, states, enums, queues, flags) and [docs/hld/HLD.md](docs/hld/HLD.md). Input field is `unit_of_measure`. Finding `source` enum is PROVISIONAL (`deterministic_rule | heuristic | ai_suggestion`, OQ-18). LLM call cap is 2 per task (initial + one repair, no escalation tier; ADR-018, OQ-20 resolved).

### 5. Document conventions
- Markdown only; diagrams in Mermaid.
- Every document has: Purpose, Scope, Detailed explanation, Architecture decisions (where applicable), Dependencies, Risks and edge cases, Related documents.
- Id ranges: OQ-01..29 BRD/HLD, OQ-1xx LLD 01–06, OQ-2xx LLD 07–12, OQ-3xx AI docs, OQ-4xx security/testing, OQ-5xx infra/operations, OQ-6xx project docs, OQ-7xx AI-layer simplification. A-xx follow the same ranges. decisions ADR-001..015; risks R-*; tasks by workstream prefix in TASK_BREAKDOWN.
- Never contradict another document: when a fact changes, update every document that states it (grep for it).

### 6. Where things live
| Need | File |
|---|---|
| Business requirements | [docs/business/BRD.md](docs/business/BRD.md) |
| HLD (Markdown, supersedes the PDF) | [docs/hld/HLD.md](docs/hld/HLD.md) |
| Component designs | [docs/lld/LLD.md](docs/lld/LLD.md), `docs/lld/modules/` |
| Agents, LLM management, guardrails | `docs/ai/` |
| Security and governance | [docs/security/SECURITY_AND_GOVERNANCE.md](docs/security/SECURITY_AND_GOVERNANCE.md) |
| Testing and AI evaluation, golden fixtures | [docs/testing/TESTING_AND_EVALUATION.md](docs/testing/TESTING_AND_EVALUATION.md), `docs/testing/fixtures/` |
| Infrastructure, environments, deployment | `docs/infra/` |
| Observability and operations | [docs/operations/OBSERVABILITY_AND_OPERATIONS.md](docs/operations/OBSERVABILITY_AND_OPERATIONS.md) |
| Decisions, plan, tasks, risks, open questions, review | `docs/project/` |

## Architecture decisions
This file introduces none; it enforces the ADR process in §2.

## Dependencies
[docs/README.md](docs/README.md) (index), [docs/project/ARCHITECTURE_DECISIONS.md](docs/project/ARCHITECTURE_DECISIONS.md), [docs/project/OPEN_QUESTIONS.md](docs/project/OPEN_QUESTIONS.md).

## Risks and edge cases
- Drift between documents: mitigated by the vocabulary rule (§4) and the review in [docs/project/DOCUMENTATION_REVIEW.md](docs/project/DOCUMENTATION_REVIEW.md).
- Premature coding: prevented by the approval gate (§1).

## Related documents
[README.md](README.md) · [docs/README.md](docs/README.md) · [docs/project/IMPLEMENTATION_PLAN.md](docs/project/IMPLEMENTATION_PLAN.md)
