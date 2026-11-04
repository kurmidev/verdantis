# Risks and Dependencies — Data-Quality Assistant (DQA)

## Purpose

List the technical, AI-specific, operational and delivery risks of DQA, and every external dependency with its expected failure behaviour, so that mitigations are planned, owned and traceable before implementation starts.

## Scope

Risks to the delivery and operation of the v1 system described in the [HLD](../hld/HLD.md) and [LLD](../lld/LLD.md). It consolidates HLD §11 and adds risks found while writing this documentation package (gaps in the HLD, brief-versus-HLD mismatches, missing inputs). Business risks outside the system (e.g. steward staffing) appear only where they gate delivery.

## Detailed explanation

### Rating scale

| Rating | Likelihood | Impact |
|---|---|---|
| H | Likely during build or first year of operation | Wrong data reaches procurement/stock, security/privacy incident, or outage of the review workflow |
| M | Plausible | Degraded service, missed NFR target, significant rework |
| L | Unlikely | Minor rework or inconvenience |

Owners are role names; named owners are **not known** and are an open question (OQ-600). Linked ADR and OQ ids point to the defining documents.

### 1. Technical risks

| ID | Risk | L | I | Mitigation | Owner | Links |
|---|---|---|---|---|---|---|
| R-TECH-01 | Duplicate detection scales poorly or misses cross-chunk duplicates because the HLD chunks at 50 records but duplicate checks need the whole batch | H | H | Separate batch-scope pass (ADR-013); blocking keys; perf test at 100k records; stage timeout | Engineering lead | ADR-013, OQ-119, OQ-129 |
| R-TECH-02 | Inconsistent source formats break parsing (encodings, header aliases, nested JSON, huge files) | M | M | Tolerant streaming parser, malformed/incomplete-row findings instead of errors, alias map, 100k-row cap with guidance | Engineering | LLD 01, OQ-03, OQ-104 |
| R-TECH-03 | Postgres connection exhaustion: KEDA-scaled workers and the API share one RDS; the HLD specifies no pooler | M | H | RDS Proxy or PgBouncer, cap max pods per queue, connection budget in capacity plan | Platform | OQ-504, ADR-009 |
| R-TECH-04 | pgvector contention with OLTP load; HNSW build/query latency at scale | M | M | Read replica for retrieval, partitions, trigger to dedicated store (> 10M vectors or p95 > 100 ms) | Engineering | ADR-003, LLD 10, OQ-232 |
| R-TECH-05 | Hash-chained audit becomes a write bottleneck or a corruption point | M | H | Per-chain scope, verification job, SIEM copy, DB permissions deny UPDATE/DELETE | Engineering/Security | ADR-011, OQ-114, OQ-403, OQ-546 |
| R-TECH-06 | Celery SQS transport limits (no results backend, 900 s delay cap, weak introspection); ElasticMQ differs from SQS | M | M | State in Postgres, idempotent handlers, sweepers, staging smoke against real SQS | Engineering | ADR-005, LLD 06, A-522 |
| R-TECH-07 | Access-control gap: role or batch-ownership check missing on a route, or over-broad DB grants (no RLS backstop in a single-entity design) | M | H | RBAC matrix tests per endpoint, Uploader own-batch tests, least-privilege grants tested per table and role, Platform Admin metadata-only view | Security | ADR-016, OQ-401, OQ-405 |
| R-SEC-OPEN | **Unauthenticated access (ADR-023):** anyone who can reach the service can read item data and approve, reject or export; audit actor is `anonymous`; four-eyes void | H | H | Private network/VPN and WAF allow-list, no public exposure, rate and upload limits, MDM verifies change files before applying, `Authenticator` slot to reintroduce SSO | Security + platform | ADR-023, OQ-820, OQ-821 |
| R-TECH-08 | Reference data (taxonomy, UoM, keyword map, aliases, generic terms) is outdated, empty at launch, or has no write path | H | M | Versioned reference data, steward ownership, write path and role defined, quarterly review; initial content sourced before build | Data Owner / Product | OQ-05, OQ-22, OQ-223 |
| R-TECH-09 | Framework churn (Celery, Presidio, provider SDK versions) breaks workflows or progress tracking (no LangGraph, ADR-019) | M | M | Pin versions, wrapper interfaces, characterisation tests, planned upgrade windows | Engineering | ADR-002 |
| R-TECH-10 | Similarity scale ambiguity (0–1 vs 0–100) and scorer choice produce wrong duplicates, e.g. token-set scoring flags 1001/1002 as duplicates | M | M | Specify the scorer and scale in LLD, test on the brief sample and a labelled set | Engineering | OQ-11, OQ-102 |
| R-TECH-11 | Migration on very large tables (`finding` at ~500M rows) causes downtime | L | M | Expand → migrate → contract; partition by month before the threshold | Platform | ADR-009 |

### 2. AI-specific risks

| ID | Risk | L | I | Mitigation | Owner | Links |
|---|---|---|---|---|---|---|
| R-AI-01 | Hallucinated categories or evidence | M | H | Taxonomy check, grounding check on `evidence_fields` and retrieved ids, `unsure` option; target 0 out-of-taxonomy after validation, < 1 % hallucinated evidence | AI lead | AI_GUARDRAILS, LLD 09 |
| R-AI-02 | Over-confident wrong suggestions | M | H | Calibration from steward outcomes; findings < 0.5 shown only as Investigate; false-confident rate < 2 % on adversarial set | AI lead | OQ-303, OQ-428 |
| R-AI-03 | **Calibration cold start**: no steward outcomes exist before go-live, so the calibration table the HLD requires cannot be built | H | M | Use hand-labelled golden set for initial calibration, ship AI hidden in shadow mode, recalibrate weekly from decisions; owner for initial table | AI lead / Data Owner | OQ-09, OQ-215, OQ-313, OQ-435 |
| R-AI-04 | Automation bias: stewards rubber-stamp AI findings | M | H | Source badges, no default "approve all" for AI, sampled QA audit of 50 accepted findings/week, four-eyes for high impact | Product | HLD §11.2, OQ-10 |
| R-AI-05 | Prompt injection through item descriptions | M | H | Delimited record tags, input scanner routes suspicious records to rule-only, read-only tools, output validation; injection corpus is a release gate | Security | LLD 08, SECURITY, OQ-315, OQ-407 |
| R-AI-06 | Silent quality drift after a provider model update | M | H | Pinned versions, monthly golden-set re-run, approval-rate drop alerts (> 10 pts warning, > 20 pts critical) | AI lead | ADR-001, OBSERVABILITY |
| R-AI-07 | Bias toward English text and well-known brands; non-English coverage limited | M | M | Multilingual test sets and per-language metrics, abbreviation dictionary growth, low confidence → Investigate | AI lead | BRD A-05, OQ-305 |
| R-AI-08 | Cap of 2 LLM calls per task (no escalation, ADR-018) leaves hard cases to humans, so more Investigate items | M | M | Measure Investigate rate on the golden set; mid tier quality gate before go-live; a new ADR can add a tier | Architect | OQ-20 (resolved), ADR-018 |
| R-AI-09 | Source label mismatch with the brief (`ai_or_heuristic_candidate` vs `ai_suggestion`) causes acceptance failure | H | M | Decide enum and golden-assertion mode before tests are written | Product / Architect | ADR-012, OQ-18, OQ-432, OQ-433 |
| R-AI-10 | Masking degrades quality (part numbers masked as phone numbers) or leaks PII | M | H | Exemption patterns for part numbers, residual scan fail-closed, PII-leak tests | Security | ADR-014, OQ-206, OQ-406 |
| R-AI-11 | Cost growth from large uploads and re-runs; the cost target (< USD 0.50 per 1k records) and the budget cap (USD 25 per batch) disagree (up to USD 50 for 100k) | M | M | Triage keeps AI to < 30 % of records, `task_key` caching, per-batch and daily budgets enforced in the AI access layer, prompt caching where supported, optional batch/off-peak inference, monthly review | Finance / Product | OQ-15, OQ-204, OQ-243 |
| R-AI-12 | **Single-provider dependency and vendor lock-in** (ADR-017): outage or throttling removes AI, price or terms change | M | M | Rule-only degradation, small adapter interface, pinned versions, monthly golden-set re-run, open-weight option for normalisation (HLD 11.3); embedding dimension conflict resolved (OQ-21, OQ-208) | AI lead | ADR-017, OQ-700 |

### 3. Operational risks

| ID | Risk | L | I | Mitigation | Owner | Links |
|---|---|---|---|---|---|---|
| R-OP-01 | Provider rate limits (429) cap AI throughput below the 1k records/min target | M | M | Concurrency caps per provider, quota increases ahead of onboarding, batch APIs for non-urgent work | Platform / AI lead | OQ-211, OQ-511 |
| R-OP-02 | **RPO 15 min is not met cross-region by the HLD design** (backups are PITR within region and a *daily* snapshot copy cross-region, about 24 h of loss) | M | H | Cross-region read replica or continuous backup replication; or restate the objective; DR drill twice a year | Platform | OQ-515, ADR-008 |
| R-OP-03 | Unleash outage on cold start or during an incident impairs the AI kill-switch | L | H | Fail-safe default AI-off (A-08), cached flags in SDK, HA deployment, tested kill-switch | Platform | ADR-007, OQ-516, OQ-250 |
| R-OP-04 | DLQ growth or poison messages go unnoticed; replay lacks authorisation controls | M | M | DLQ alerts (> 10/h warn, > 100/h critical), reason codes, replay tool with RBAC | Platform / Engineering | OQ-505, OQ-506 |
| R-OP-05 | Retention conflicts: raw records kept 2 years but findings traceable 7 years; right to erasure vs immutable audit | M | H | Decide retention per data class, legal review, redaction strategy that preserves chain integrity | Security / Legal | OQ-26, OQ-402, OQ-508 |
| R-OP-06 | Alert fatigue or missing alerts for AI quality drift | M | M | Thresholds from HLD §10.6, twice-daily dashboard review for 72 h after release, weekly review | On-call | OBSERVABILITY, OQ-544 |
| R-OP-07 | Masked prompt/response store is sensitive data itself; telemetry may leak PII | L | H | 10 % production sampling, 30-day retention, restricted access, no raw text in logs | Security | OQ-541 |
| R-OP-08 | Ticketing integration failure leaves findings stuck in `investigating` | M | L | Retry with backoff, keep state, alert; "ticket resolved" signal defined | Engineering | A-07, OQ-29, OQ-242 |
| R-OP-09 | Four-eyes bottleneck: Data Owners are not available, high-impact approvals pile up | M | M | Define N, escalation, ageing alerts | Product | OQ-10, OQ-238, OQ-545 |

### 4. Delivery and project risks

| ID | Risk | L | I | Mitigation | Owner | Links |
|---|---|---|---|---|---|---|
| R-DEL-01 | Many requirement gaps (severity table, reject codes, change-file format, reference data content) block detailed build tasks | H | H | Resolve blocking OQs before the approval gate closes; mark blocked tasks in TASK_BREAKDOWN | Product / Architect | OPEN_QUESTIONS |
| R-DEL-02 | HLD stack not confirmed by the user; late change forces rework | M | H | ADRs flag unconfirmed choices; confirm before Foundation phase | Architect | ADR-001..004, 008, 009; OQ-16 |
| R-DEL-03 | Brief sample vs HLD mismatches (confidence 0.95 vs 1.0, `weak_description` on 1001, duplicate scoring) cause acceptance disputes | H | M | Decide acceptance semantics (exact vs required-set) first | Product | OQ-12, OQ-19, OQ-222, OQ-432, OQ-434 |
| R-DEL-04 | No UI LLD and no UI requirements while the steward workflow depends on a UI | M | M | API-only scope confirmed; UI requirements and its own design as a separate effort | Product | OQ-25, OQ-420 |
| R-DEL-05 | Infrastructure ownership and AWS account/region layout undefined, delaying environments | M | H | Name platform owner and confirm AWS before Foundation phase | Platform | OQ-500, OQ-501, OQ-512 |
| R-DEL-06 | Shadow-mode goal (2-week precision gate) has no labelled data and no mechanism to hide AI findings | M | M | Shadow flag, labelling plan, golden-set owner | AI lead | OQ-28, OQ-435 |
| R-DEL-07 | Throughput KPI (2× steward speed) has no baseline | H | L | Measure a baseline during pilot | Product | OQ-13, OQ-431 |
| R-DEL-08 | Coverage rule conflict (80 % project rule vs 85 % on core modules) | L | L | Use the higher threshold on core modules, 80 % elsewhere, confirm | Engineering | OQ-523 |
| R-DEL-09 | Scale of documentation set makes inconsistencies likely | M | M | Phase-10 cross-document review ([DOCUMENTATION_REVIEW](DOCUMENTATION_REVIEW.md)) | Architect | — |
| R-DEL-UI | UI built against an API that does not exist yet; contract shifts in P2/P3, missing endpoints (OQ-810..812) and unconfirmed visual direction (OQ-807) cause rework | M | M | UI code paused until P3 gate; LLD 13 revised before U-tasks start; typed client from the contract; ADR-022 | UI lead (TBD) | [13-steward-ui.md](../lld/modules/13-steward-ui.md) |

### 5. External dependencies

Failure behaviour must keep rule and heuristic findings flowing; only the AI layer may degrade (HLD NFR Availability). Timeout and retry values come from HLD §4.6 unless noted; others are open.

| Dependency | Used for | Direction | Failure behaviour | Timeout / retry reference |
|---|---|---|---|---|
| Corporate IdP (Okta / Entra ID) | SSO, group claims for roles, MFA | Inbound auth | New logins fail; existing 15-min JWTs expire; no unauthenticated fallback | Token validation settings: OQ-408; JWT 15 min with refresh (HLD §5.1) |
| Amazon Bedrock (single LLM + embeddings provider, proposed) | Category, normalisation, adjudication; embeddings | Outbound via the in-process AI access layer | Retry with backoff; on failure AI layer skipped for the chunk, batch `ai_partial`, rule-only mode | LLM 30 s, 2 retries, backoff 1–8 s with jitter; embeddings 10 s, 3 retries (HLD §4.6) |
| ~~Azure OpenAI (secondary)~~ | Removed by ADR-017 | — | — | OQ-509, OQ-513, OQ-208 resolved |
| Ticketing (ServiceNow / Jira) | Investigate decisions open a ticket | Outbound webhook | Finding stays `investigating`, retried, alert raised (A-07) | Retry/backoff values undefined (OQ-244); auth and return path (OQ-242) |
| SIEM (Splunk) | Security and audit event forwarding | Outbound | Buffer and retry; DB audit remains the source; alert on lag | Not specified in HLD (OQ-510) |
| Source ERPs (SAP, Oracle, …) | File-based extracts (read-only in v1) | Inbound files | Bad files produce findings or a 422; no connector failure mode in v1 | File limits: 100k rows (HLD §6.3), OQ-104 |
| MDM team / process | Applies the approved change file | Outbound file | None automatically (DQA has no write access); export is complete when signed URL exists | URL expiry OQ-241; consumption confirmation not in scope |
| Sentry / PagerDuty / Slack (Langfuse dropped, ADR-021) | Observability and alerting | Outbound | Loss of telemetry must not block processing; fall back to logs and metrics | Not specified (OQ-549) |
| Unleash | Feature flags | Internal | Flags cached by SDK; cold-start default AI-off (A-08) | HA and polling interval OQ-516, OQ-250 |
| AWS services (RDS, SQS, S3, KMS, Secrets Manager, EKS) | Platform | Internal | Per-service behaviour in INFRASTRUCTURE; DR RTO 4 h | OQ-505 (redrive), OQ-515 (RPO) |

## Architecture decisions

Risk handling choices are recorded in [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md): ADR-005 (broker limits), ADR-006/017 (in-process AI access layer as single exit), ADR-011 (audit), ADR-012/013 (provisional models), ADR-014 (masking).

## Dependencies

[HLD](../hld/HLD.md) §11, [SECURITY_AND_GOVERNANCE](../security/SECURITY_AND_GOVERNANCE.md), [INFRASTRUCTURE](../infra/INFRASTRUCTURE.md), [OBSERVABILITY_AND_OPERATIONS](../operations/OBSERVABILITY_AND_OPERATIONS.md), [TESTING_AND_EVALUATION](../testing/TESTING_AND_EVALUATION.md); [OPEN_QUESTIONS](OPEN_QUESTIONS.md) for the consolidated list.

## Open questions introduced here

| ID | Question |
|---|---|
| OQ-600 | Who are the named owners for each risk category and each external dependency (IdP, Bedrock, ticketing, SIEM, source ERPs, MDM)? |
| OQ-601 | What are the contractual SLAs and technical contacts for each external dependency, and what rate/quota limits apply? |
| OQ-602 | What is the risk appetite for going live without a calibration table: is a hidden-AI shadow period with hand-labelled data acceptable as the substitute? |
| OQ-603 | Is a failure of the ticketing system after `investigate` acceptable as "retry and alert", or must the steward see a visible failed-ticket state? |

## Risks and edge cases

- Ratings are architectural judgement, not measured data; re-rate after the first performance and evaluation runs.
- Several risks have the same root cause (missing reference data, undefined acceptance semantics, unconfirmed stack); closing the blocking open questions retires multiple risks at once.
- A risk with no named owner (OQ-600) is not mitigated until an owner is assigned.

## Related documents

- [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
- [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
