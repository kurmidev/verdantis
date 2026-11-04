# Business Requirements Document (BRD) — Enterprise Item Data-Quality Assistant (DQA)

| Field | Value |
|---|---|
| Version | 1.0-draft |
| Status | Draft, awaiting review and approval (documentation-first approval gate) |
| Source | `docs/HLD — Enterprise Item Data-Quality Assistant.pdf` (Nov 4, 2026, @CP) and the brief sample supplied by the project owner |
| Conventions | `A-xx` = Assumption, `OQ-xx` = Open Question (see [OPEN_QUESTIONS.md](../project/OPEN_QUESTIONS.md)), `BR-xx` = Business Requirement, `FR-xx`/`NFR-xx` = functional / non-functional requirement |

## 1. Purpose

Define **what the business needs** from the Data-Quality Assistant (DQA) and why, independent of the solution design. This document is the business anchor for the [HLD](../hld/HLD.md): every functional requirement in the HLD traces back to a business requirement here.

## 2. Scope

**In scope (v1)** — taken from the source HLD §1.3:

- Upload of item-master batches as JSON or CSV.
- Deterministic, heuristic and AI-assisted detection of data-quality issues.
- A review queue with approve / reject / investigate decisions (including bulk actions).
- Audit trail, metrics, and export of approved changes as a **change file**.

**Out of scope (v1):**

- Write-back to source ERPs.
- Automatic merge of duplicates.
- Supplier master, BOM and pricing data.
- Real-time / streaming ingestion.
- Multi-tenancy: DQA serves a single entity (one organisation); there is no tenant concept (ADR-016).

**UI (ADR-022, project owner decision):** the Steward UI is **in scope**. First version = Steward core: upload batch, batch status, findings review queue with filters, approve/reject/investigate/edit-and-approve, bulk actions, export of the change file. Auditor audit-log view and the Needs-investigation tab follow only if the API provides them (OQ-809). UI code starts after the backend API exists; design in [LLD module 13](../lld/modules/13-steward-ui.md).

## 3. Detailed explanation

### 3.1 Background

Item records originate in several source systems (ERP-A, ERP-B, …). They are inconsistent, incomplete, duplicated and poorly described. The source HLD's own examples: a "bearing" with no part number, a bearing filed under *Electrical*, and `6205-ZZ` / `6205 ZZ` entered as two items.

### 3.2 Business problem

1. Manual review by data stewards does not scale across the volume of item records.
2. Fully automatic correction is unsafe: a wrong merge or re-categorisation propagates into purchasing, stock and analytics.
3. Poor item data reaches procurement, inventory and analytics before it is caught.

### 3.3 Business objectives

| ID | Objective | Measure (see §8) |
|---|---|---|
| BO-1 | Cut steward time spent *finding* bad item records by surfacing ranked, explained candidates instead of raw spreadsheets | Steward throughput KPI |
| BO-2 | Raise item-master quality (complete part numbers, correct categories, no duplicates) before data reaches procurement, inventory and analytics | Precision / recall KPIs |
| BO-3 | Use AI assistance while keeping humans as the final decision-maker and keeping a complete audit trail | Zero automatic writes; 100 % decisions audited |

### 3.4 Goals and non-goals

- **Goals:** explainable review candidates; deterministic results that never depend on AI availability; every finding ends in a human decision; full traceability for 7 years.
- **Non-goals:** DQA never changes production data; DQA never claims to have "fixed", "corrected" or "auto-approved" anything.

### 3.5 Stakeholders and target users

| Role | Who they are | What they need from DQA | Source |
|---|---|---|---|
| Uploader | Person who supplies an item batch | Upload a file, see status and findings for *own* batches | HLD §5.2 |
| Data Steward | Owns day-to-day item quality; maintains UoM list, generic terms, taxonomy (§1.3) | Ranked, explained findings; approve / reject / investigate; bulk action; export | HLD §1.3, §4.9, §5.2 |
| Data Owner | Accountable for a data domain | Second approval on high-impact actions (four-eyes); escalation target | HLD §4.10, §5.2, §10.8 |
| Auditor | Compliance / audit | Read-only view of all findings and the audit log | HLD §5.2 |
| Platform Admin | Operates the platform | Configuration only; **metadata only**, no item data | HLD §5.2 |
| Source-system owner | Owns an ERP's data | Receives an "Investigate" ticket with evidence | HLD §2.7, §10.8 |
| MDM team | Applies approved changes via the normal change process | Receives the change file | HLD §4.10 |
| AI governance owner | Approves models and prompts | Evidence from evaluations before production use | HLD §5.8 |

### 3.6 Use cases

| ID | Use case | Primary actor | Outcome |
|---|---|---|---|
| UC-01 | Upload an item batch (JSON/CSV) | Uploader / Steward | `batch_id` returned immediately; processing is asynchronous |
| UC-02 | Process malformed / empty / null-heavy files | System | Findings (`malformed_row`, `incomplete_row`) or an empty result; never a server error |
| UC-03 | Review findings (filter by type, severity, source, status) | Steward | Ranked queue with explanation, evidence, confidence, source badge |
| UC-04 | Decide on a finding (approve / reject with reason / investigate / edit-and-approve) | Steward | Decision audited; finding status updated |
| UC-05 | Bulk decision | Steward | Per-item results (max 500 per request) |
| UC-06 | High-impact approval (duplicate merges; category changes above threshold) | Steward + Data Owner | Second approval recorded |
| UC-07 | Export approved findings as a change file | Steward / Data Owner | File handed to MDM; nothing written to records |
| UC-08 | Investigate | Steward | Ticket opened to the source owner (ServiceNow / Jira); finding returns to review when resolved |
| UC-09 | Audit review | Auditor | Read-only trace of every finding, decision, model and prompt version |
| UC-10 | Maintain reference data (UoM, taxonomy, generic terms) | Steward | Versioned reference data used by checks |

> Gap: no requirement in the source HLD covers who lists/searches batches (Uploader "own batches"). UI scope is resolved by ADR-022 (OQ-25); the batch-list endpoint is OQ-810.

## 4. Business requirements

Each BR maps to the functional requirements (FR) of the source HLD §1.4.

| BR | Business requirement | Maps to | Priority |
|---|---|---|---|
| BR-01 | The business can submit item batches in JSON or CSV; bad input is reported, never crashes the service | FR-1 | Must |
| BR-02 | Items with a manufacturer but no manufacturer part number are flagged | FR-2 | Must |
| BR-03 | Unsupported or suspicious units of measure are flagged | FR-3 | Must |
| BR-04 | Duplicate `item_id` within one source system is flagged | FR-4 | Must |
| BR-05 | Weak or vague descriptions are flagged | FR-5 | Must |
| BR-06 | Possible duplicates across systems are surfaced for a human, never merged automatically | FR-6 | Must |
| BR-07 | Items whose category does not fit the description are surfaced | FR-7 | Must |
| BR-08 | A better, normalised description is suggested | FR-8 | Should |
| BR-09 | Every finding is explainable: issue type, severity, confidence, explanation, evidence, suggested action, source | FR-9 | Must |
| BR-10 | Stewards can approve, reject, investigate or bulk-act; every decision is audited | FR-10 | Must |
| BR-11 | Approved suggestions leave DQA only as a change file; nothing is written to records automatically | FR-11 | Must |
| BR-12 | The product keeps working when the AI service is unavailable or switched off | NFR Availability | Must |

## 5. Non-functional business requirements

| ID | Area | Target (from source HLD §1.5) |
|---|---|---|
| NFR-1 | Latency | Deterministic + heuristic pass: 10 k records < 30 s. AI pass: asynchronous, 10 k records < 15 min |
| NFR-2 | Availability | 99.5 % for UI/API; AI layer may degrade without blocking rule results |
| NFR-3 | Safety | Zero automatic writes to item data; forbidden wording ("fixed", "corrected", "auto-approved") blocked in all output |
| NFR-4 | Explainability | 100 % of findings carry a human-readable explanation and evidence fields |
| NFR-5 | Security | SSO, RBAC, batch-ownership access control, PII masked before any LLM call |
| NFR-6 | Auditability | Every finding, decision, model and prompt version traceable for 7 years |
| NFR-7 | Cost | AI cost per 1 k records within agreed budget (target < USD 0.50). Approach: only uncertain records go to AI, one provider, two small model tiers, caching, per-batch budget guard (ADR-017..020; cost model in LLM_MANAGEMENT.md) |
| NFR-8 | Maintainability | New rule added without touching the engine; ≥ 85 % test coverage on checks |
| NFR-9 | Data volume | Batches up to 100 k records; typical 1 k – 20 k |

## 6. Constraints

- Humans are always the final decision-makers; DQA has no write access to ERPs.
- LLM traffic must go through one controlled exit and use enterprise endpoints; the system must still work when zero-retention is not available.
- Reference data (allowed UoM, category taxonomy) is *owned by stewards*, not by engineering.
- `item_id` is unique only within a `source_system`.

## 7. Assumptions

| ID | Assumption | Status |
|---|---|---|
| A-01 | Cloud is AWS (as proposed in the source HLD) | Unconfirmed — OQ-14 |
| A-02 | Item records carry the seven fields of the brief sample: `item_id`, `item_description`, `manufacturer`, `manufacturer_part_number`, `category`, `unit_of_measure`, `source_system` | Based on user-supplied sample; required/optional rules unknown — OQ-03 |
| A-03 | Source ERP data arrives as files supplied by users (no ERP connector in v1) | From HLD §2.7 |
| A-04 | Corporate IdP (Okta / Entra ID) provides SSO and group claims that map to roles | From HLD §2.7 |
| A-05 | Initial language is English; non-English coverage is limited at first | From HLD §11.6 |
| A-06 | DQA serves a single entity (one organisation); there is no multi-tenancy | Decided by user — ADR-016 |

## 8. Success metrics and acceptance criteria

### 8.1 KPIs

| KPI | Target | Note |
|---|---|---|
| Precision of findings (steward-approved ÷ reviewed) | ≥ 85 % rules, ≥ 70 % AI suggestions | Needs steward decision data |
| Steward throughput | 2× records reviewed/hour vs manual baseline | **No baseline or measurement method defined — OQ-13** |
| Duplicate recall on a labelled set | ≥ 80 % | Labelled set must be created |
| AI schema-valid output rate | ≥ 99 %; hallucinated-evidence rate < 1 % | |
| AI cost per 1 k records | < USD 0.50 | See cost conflict, OQ-15 |

### 8.2 Business acceptance criteria

1. The brief sample (below) yields `missing_part_number` for item 1001 and `category_mismatch_candidate` for item 1002.
2. Empty, malformed and null-heavy files produce findings or an empty list, never a server error.
3. Input records are byte-identical before and after processing.
4. No output contains forbidden wording.
5. With the LLM disabled, every deterministic and heuristic finding is still produced.
6. Every steward decision appears in the audit log with user, time and reason.

### 8.3 Golden example (verbatim from the brief)

Input: [brief-sample-input.json](../testing/fixtures/brief-sample-input.json). Expected: [brief-expected-output.json](../testing/fixtures/brief-expected-output.json).

| item_id | issue_type | severity | confidence | source (as written in the brief) |
|---|---|---|---|---|
| 1001 | `missing_part_number` | medium | 0.95 | `deterministic_rule` |
| 1002 | `category_mismatch_candidate` | low | 0.70 | `ai_or_heuristic_candidate` |

The brief's output is a *minimal projection*. The full finding object required by FR-9 (evidence, status, ids) is defined in the [HLD](../hld/HLD.md). Differences between the brief and the source HLD (0.95 vs 1.0 confidence; `source` vocabulary; whether record 1001 should *also* raise `weak_description`; whether 1001/1002 should be flagged `possible_duplicate`) are recorded as OQ-12, OQ-18 and OQ-19.

## 9. Dependencies

| Dependency | Needed for | Owner |
|---|---|---|
| Corporate IdP (OIDC/SAML) | Login, roles | IT / Security |
| Enterprise LLM endpoint(s) | AI suggestions | AI governance / Platform |
| Reference data (UoM list, taxonomy, generic terms, manufacturer aliases, abbreviation dictionary) | Rules, heuristics, AI context | Data Stewards — contents/source unknown (OQ-05) |
| ServiceNow / Jira | "Investigate" tickets | Source-system owners |
| MDM team process | Applying change files | MDM team |
| SIEM (Splunk) | Security/audit event forwarding | Security |
| Labelled golden dataset (300–500 records per AI task) | AI evaluation and go-live gates | Stewards + Engineering |

## 10. Risks and edge cases

| Risk / edge case | Business impact | Mitigation (see [RISKS_AND_DEPENDENCIES.md](../project/RISKS_AND_DEPENDENCIES.md)) |
|---|---|---|
| Steward over-trust in AI (automation bias) | Wrong changes approved | Source badges, no default "approve all" for AI, sampled QA, four-eyes on high impact |
| Quality drift after a provider model update | Silent precision loss | Pinned model versions, monthly golden-set re-run, approval-rate alerts |
| Reference data outdated | False positives | Steward-owned, versioned, quarterly review |
| Very small descriptions ("valve") | Ambiguous results | `weak_description` + AI normalisation suggestion |
| Same item in different systems with conflicting values | Missed duplicates | `possible_duplicate`, `conflicting_source_values` — never auto-merged |
| Throughput KPI cannot be proven | Success cannot be demonstrated | Establish baseline before pilot (OQ-13) |
| Brief and HLD disagree on expected output details | Failed acceptance test | Decide in OQ-12 / OQ-18 / OQ-19 before implementation |

## 11. Business requirement traceability

| BR | HLD section | Component(s) | LLD module |
|---|---|---|---|
| BR-01 | §2.2 Ingestion & Validator | Ingestion | [01-ingestion-validator](../lld/modules/01-ingestion-validator.md) |
| BR-02–BR-04 | §2.2 Rule Engine | Rule Engine | [02-rule-engine](../lld/modules/02-rule-engine.md) |
| BR-05–BR-07 | §2.2 Heuristic Engine (+ Agent Orchestrator for AI-assisted) | Heuristic Engine, Agent Orchestrator | [03-heuristic-engine](../lld/modules/03-heuristic-engine.md), [08-agent-orchestrator](../lld/modules/08-agent-orchestrator.md) |
| BR-08 | §3 AI architecture | AI task pipeline, AI access layer | [08](../lld/modules/08-agent-orchestrator.md), [07](../lld/modules/07-ai-gateway.md) |
| BR-09 | §2.4 Finding contract | DQA API, Finding Store | [04](../lld/modules/04-api-service.md), [05](../lld/modules/05-data-layer.md) |
| BR-10–BR-11 | §4 Approval workflow | Review workflow, Export | [11-review-workflow-and-export](../lld/modules/11-review-workflow-and-export.md) |
| BR-12 | §3, §6 | AI access layer (rule-only degradation), feature flags | [07](../lld/modules/07-ai-gateway.md), [12](../lld/modules/12-config-flags-and-prompts.md) |

## 12. Architecture decisions

This business document makes no technology decisions. Business-level constraints that shape them (human-in-the-loop, no write-back, single-entity deployment, user-directed choices of custom AI gateway, Unleash and Celery with SQS; plus the owner's direction for a simplified, minimum-infrastructure, cost-effective AI layer) are recorded as ADRs in [ARCHITECTURE_DECISIONS.md](../project/ARCHITECTURE_DECISIONS.md) (ADR-005, ADR-006, ADR-007 decided by the user; the others proposed in the HLD and pending confirmation).

## 13. Related documents

- [HLD](../hld/HLD.md)
- [LLD index](../lld/LLD.md)
- [Testing and evaluation](../testing/TESTING_AND_EVALUATION.md)
- [Open questions](../project/OPEN_QUESTIONS.md) · [Risks and dependencies](../project/RISKS_AND_DEPENDENCIES.md)
- [Architecture decisions](../project/ARCHITECTURE_DECISIONS.md)
