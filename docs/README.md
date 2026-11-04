# Documentation Index

## Purpose
Single entry point to every document in `docs/`, with reading order and status.

## Scope
All Markdown documents plus the source PDF and test fixtures. Status of every document: **Draft, pending user review** (approval gate in [../CLAUDE.md](../CLAUDE.md)).

## Detailed explanation

### Suggested reading order
BRD → HLD → LLD index → modules in numeric order (incl. 13 Steward UI) → AI docs → security → testing → infra → operations → ADRs → risks → open questions → plan and tasks → documentation review.

### Business and high-level design
| Document | Purpose |
|---|---|
| [business/BRD.md](business/BRD.md) | Business objective, users, use cases, requirements, KPIs, assumptions |
| [hld/HLD.md](hld/HLD.md) | Corrected high-level design with Mermaid diagrams |
| [HLD — Enterprise Item Data-Quality Assistant.pdf](<HLD — Enterprise Item Data-Quality Assistant.pdf>) | Original source HLD (unchanged) |

### Low-level design
| Document | Purpose |
|---|---|
| [lld/LLD.md](lld/LLD.md) | LLD index, conventions, shared models, cross-module sequences |
| [lld/modules/01-ingestion-validator.md](lld/modules/01-ingestion-validator.md) | Parsing, normalisation, row validation, snapshots |
| [lld/modules/02-rule-engine.md](lld/modules/02-rule-engine.md) | Deterministic rules and registry |
| [lld/modules/03-heuristic-engine.md](lld/modules/03-heuristic-engine.md) | Weak description, duplicates, category mismatch, suspicious content |
| [lld/modules/04-api-service.md](lld/modules/04-api-service.md) | REST contracts, idempotency, pagination, bulk decisions |
| [lld/modules/05-data-layer.md](lld/modules/05-data-layer.md) | Reference schema, grants, hash-chained audit |
| [lld/modules/06-queue-and-workers.md](lld/modules/06-queue-and-workers.md) | Queues, chunking, retries, DLQ, batch state |
| [lld/modules/07-ai-gateway.md](lld/modules/07-ai-gateway.md) | AI Access Layer (in-process): masking, budgets, retries, single provider |
| [lld/modules/08-agent-orchestrator.md](lld/modules/08-agent-orchestrator.md) | Plain-Python AI task pipeline: triage, handlers, tools, progress, loop guards |
| [lld/modules/09-ai-validation-and-explanation.md](lld/modules/09-ai-validation-and-explanation.md) | Output validation, calibration, composer |
| [lld/modules/10-rag-and-reference-data.md](lld/modules/10-rag-and-reference-data.md) | Indexes, hybrid retrieval, reference data |
| [lld/modules/11-review-workflow-and-export.md](lld/modules/11-review-workflow-and-export.md) | Decisions, four-eyes, export, ticket webhook |
| [lld/modules/12-config-flags-and-prompts.md](lld/modules/12-config-flags-and-prompts.md) | Flags, prompt registry, parameters |
| [lld/modules/13-steward-ui.md](lld/modules/13-steward-ui.md) | Steward UI: screens, state, API mapping, design direction, tests |

### AI architecture
| Document | Purpose |
|---|---|
| [ai/AI_ARCHITECTURE.md](ai/AI_ARCHITECTURE.md) | Agent pattern, models, RAG, embeddings, memory |
| [ai/AGENT_DESIGN.md](ai/AGENT_DESIGN.md) | Per-agent cards incl. draft system prompts |
| [ai/AGENT_WORKFLOW.md](ai/AGENT_WORKFLOW.md) | Execution paths, failure and resume |
| [ai/LLM_MANAGEMENT.md](ai/LLM_MANAGEMENT.md) | Versioning, budgets, routing, caching, cost |
| [ai/AI_GUARDRAILS.md](ai/AI_GUARDRAILS.md) | Injection, hallucination, limits, approvals |

### Security, testing, infrastructure, operations
| Document | Purpose |
|---|---|
| [security/SECURITY_AND_GOVERNANCE.md](security/SECURITY_AND_GOVERNANCE.md) | Open access (ADR-023; authN/Z and RBAC superseded), PII, isolation, audit, governance, threat model |
| [testing/TESTING_AND_EVALUATION.md](testing/TESTING_AND_EVALUATION.md) | 14 test types, metrics, thresholds, traceability |
| [testing/fixtures/brief-sample-input.json](testing/fixtures/brief-sample-input.json) | Brief sample input (verbatim) |
| [testing/fixtures/brief-expected-output.json](testing/fixtures/brief-expected-output.json) | Brief expected output (verbatim) |
| [infra/INFRASTRUCTURE.md](infra/INFRASTRUCTURE.md) | Cloud, data, queue, network, DR |
| [infra/ENVIRONMENTS_AND_DEPLOYMENT.md](infra/ENVIRONMENTS_AND_DEPLOYMENT.md) | Environments, CI/CD, rollback, backup |
| [operations/OBSERVABILITY_AND_OPERATIONS.md](operations/OBSERVABILITY_AND_OPERATIONS.md) | Logging, tracing, alerts, incidents, post-live checks |

### Project management
| Document | Purpose |
|---|---|
| [project/ARCHITECTURE_DECISIONS.md](project/ARCHITECTURE_DECISIONS.md) | ADR-001..021 |
| [project/IMPLEMENTATION_PLAN.md](project/IMPLEMENTATION_PLAN.md) | Phases, gates, critical path |
| [project/TASK_BREAKDOWN.md](project/TASK_BREAKDOWN.md) | Task list with dependencies and acceptance |
| [project/RISKS_AND_DEPENDENCIES.md](project/RISKS_AND_DEPENDENCIES.md) | Risks and external dependencies |
| [project/OPEN_QUESTIONS.md](project/OPEN_QUESTIONS.md) | Consolidated open questions and assumptions |
| [project/DOCUMENTATION_REVIEW.md](project/DOCUMENTATION_REVIEW.md) | Phase 10 review and completeness report |

## Architecture decisions
Recorded in [project/ARCHITECTURE_DECISIONS.md](project/ARCHITECTURE_DECISIONS.md).

## Dependencies
Each document lists its own dependencies; the LLD dependency map is in [lld/LLD.md](lld/LLD.md).

## Risks and edge cases
Stale links when files move: the review re-runs a link check ([project/DOCUMENTATION_REVIEW.md](project/DOCUMENTATION_REVIEW.md)).

## Related documents
[../README.md](../README.md) · [../CLAUDE.md](../CLAUDE.md)
