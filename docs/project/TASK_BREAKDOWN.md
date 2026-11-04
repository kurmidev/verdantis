# Task Breakdown

**Status:** DRAFT for review. Documentation only. Tasks describe future work and **must not be started before the approval gate** in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (section 3.1).

## Purpose
Break the project into implementable tasks grouped by the ten workstreams, each with ID, description, dependencies, expected deliverable, acceptance criteria, complexity, risks, parallelism and traceability to LLD modules and FR/NFR.

## Scope
Backend, workers, AI access layer (in-process), AI task handlers, data layer, security, testing/evaluation, observability, deployment and production validation. Steward UI tasks are in WS11 (ADR-022). Estimates are relative only; no dates (team size unknown, OQ-500, OQ-514).

## Detailed explanation

### Conventions
- **Task id prefixes:** F = WS1 Foundation, CA = WS2 Core application, AI = WS3 AI/LLM integration, G = WS4 Agents, W = WS5 Workflow, S = WS6 Security, T = WS7 Testing, O = WS8 Observability, D = WS9 Deployment, V = WS10 Production validation. (`CA-` and `AI-` were chosen so task ids never collide with assumption ids `A-xx`.)
- **Complexity:** S = small, a focused unit with clear spec; M = a module part, a few interacting pieces; L = a full module or cross-module feature; XL = multi-module / needs external coordination. Relative sizing only (S about 1, M about 3, L about 8, XL about 20 units).
- **Par:** `P` = can run in parallel with siblings once dependencies are met; `S` = sequential/critical path.
- **Blocked by:** `OQ-xx` ids that need an owner answer before the task starts. Ids come from [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) and the module documents; none are invented here. A task with a blocker may start only after the answer or after the provisional choice in the module doc is approved.
- **TDD:** every code task writes its tests first (RED), then implements (GREEN), then refactors (HLD 7.1; testing doc). Test tasks in WS7 provide shared harnesses; unit tests belong to the task that owns the code.
- **Module refs:** LLD 01-12 are in [lld/modules/](../lld/modules/). **Requirements:** FR/NFR per [BRD](../business/BRD.md).
- Acceptance criteria below are the task's *own* check; the phase gates in the plan combine them.

### WS1 Foundation and infrastructure

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| F-01 | Repository tooling and conventions: package layout per LLD 3.2, lint/format, strict typing, test runner, pre-commit, coverage config | Approval gate | Repo skeleton with tooling configs | CI-equivalent local run passes on empty project; layout matches LLD 3.2 | S | Coverage basis unclear | S | LLD 3.2-3.3 | NFR-8; OQ-418, OQ-523 |
| F-02 | CI skeleton: lint, type check, unit/integration, security scans (SAST, dependency, container, secrets), coverage gate | F-01 | CI pipeline definition | Pipeline runs all stages on a sample change; fails on a seeded vulnerability | M | Tool choice unconfirmed | P | ENV 8.7 | NFR-5, NFR-8; OQ-417 |
| F-03 | Local dev environment (compose): Postgres 16 + pgvector, ElasticMQ, Redis, Unleash, S3-compatible store, local OIDC stub, StubSuggester hook | F-01 | Local environment definition and runbook | One command starts all services; health checks pass; parity table matches staging | M | Local OIDC/object store choice | P | ENV 3 | OQ-521, OQ-522 |
| F-04 | Shared domain models: Record, Finding, enums (issue types, source, states), error taxonomy, fixture loader for brief sample | F-01 | Typed models + fixtures wired | Models validate the two brief records; unknown fields rejected on Finding; vocabulary matches LLD 3.3 | M | `source` enum unresolved | S | LLD 3.3 | FR-9; OQ-18, OQ-130, OQ-310, OQ-433 |
| F-05 | Settings and parameter loader with startup validation of required secrets/config (HLD 6.2 defaults, owners) | F-01 | Config loading spec implemented | Missing required secret fails startup with clear error; defaults match 6.2 table | S | Threshold scale ambiguity | P | 12 | OQ-11, OQ-248, OQ-246 |
| F-06 | Terraform baseline: accounts/regions layout, VPC, subnets, KMS, VPC endpoints | Approval gate | Reviewed infra modules | `plan` clean in dev account; private subnets only for data tier | L | Account/region undecided; lead time | P | INFRA | OQ-500, OQ-501, OQ-512 |
| F-07 | Terraform data tier: RDS Postgres 16 Multi-AZ + pgvector, ElastiCache, S3 (versioned, KMS), SQS + DLQs | F-06 | Data-tier modules | Instances reachable only from cluster; DLQ redrive configured | L | Pooler and redrive values unset | P | INFRA, 05, 06 | OQ-504, OQ-505, OQ-508 |
| F-08 | EKS namespace `dqa`, Helm charts for api, rule-worker, ai-worker (same worker image; no ai-gateway, ADR-017), KEDA scalers, External Secrets Operator | F-06 | Charts and cluster add-ons | Pods start; KEDA scales on queue depth in staging | L | mTLS mechanism; node group sizing | P | INFRA | OQ-502, OQ-503 |
| F-09 | Staging environment and GitOps (Argo CD) wiring | F-07, F-08 | Staging live | Deploy of a hello image via GitOps; rollback tested | M | Staging topology open | S | ENV | OQ-520 |
| F-10 | Secrets management and rotation (DB 30 d, provider keys 90 d), gitleaks in CI | F-07, F-02 | Rotation policy implemented | Rotation rehearsed in staging with no downtime; no secrets in repo/images | M | None (Azure credential removed, ADR-017) | P | INFRA | NFR-5; OQ-513 (resolved) |

### WS2 Core application development

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| CA-01 | Normalisation utilities: `is_blank`, `normalize_mpn`, UoM alias mapping, token utils (property-tested) | F-04 | `normalize/` module | `6205-ZZ`, `6205 ZZ`, `6205ZZ` normalise equal; None/""/whitespace/"N/A"/"null" are blank; inputs never mutated | M | UoM alias map content; blank markers | P | 01 | FR-1..FR-4; OQ-103, OQ-108 |
| CA-02 | Ingestion parser: JSON/CSV, header aliases (`mfr_part_no` to canonical), streaming, 100 k row cap with split guidance | F-04, CA-01 | `ingest/` parser | Empty file gives empty result; bad encoding gives 422 with position and partial rows kept; > 100 k rejected with guidance | L | CSV dialect, upload limits, empty-file contract | P | 01 | FR-1, NFR-9; OQ-03, OQ-104, OQ-17, OQ-111, OQ-118 |
| CA-03 | Row validation: `malformed_row` / `incomplete_row` findings; record still checked for other issues | CA-02 | Validator | Null-heavy file yields findings, never exception; MPN-blank row is not `incomplete_row` | M | Required vs optional fields | P | 01 | FR-1; OQ-103 |
| CA-04 | Immutable raw snapshot writer and `record_key` derivation including duplicate-key suffix | CA-02 | Snapshot writer | Re-reading snapshot is byte-identical to input; duplicate `(source_system,item_id)` get distinct `record_key` | M | `#n` suffix proposal unapproved | S | 01, 05 | FR-1, FR-4; OQ-124 |
| CA-05 | Rule registry and `check(records, ctx) -> list[Finding]` contract (id + version, pure, no I/O) | F-04 | `checks/` registry | New rule added without touching engine; registry lists id and version | M | None | S | 02 | NFR-8 |
| CA-06 | Rule `missing_part_number` (manufacturer present AND MPN blank) | CA-05, CA-01 | Rule | 1001 flagged with severity medium; confidence per approved constant; explanation uses template | S | 1.0 vs 0.95 | P | 02 | FR-2; OQ-100, OQ-19, OQ-216 |
| CA-07 | Rule `unsupported_uom` (alias map first, then allow-list) | CA-05, CA-01 | Rule | `each`->`EA` accepted; `EACH`, `pcs` per alias map; unknown flagged high | S | "Suspicious" undefined | P | 02 | FR-3; OQ-108, OQ-437 |
| CA-08 | Rule `duplicate_item_id` within `(source_system,item_id)` | CA-05, CA-04 | Rule | Two rows same key flagged high; different systems not flagged | S | Case/whitespace handling | P | 02 | FR-4; OQ-112 |
| CA-09 | Heuristic `weak_description` (< 3 tokens, generic terms, no attribute tokens) | CA-05 | Heuristic | "valve" flagged; "SKF Bearing 6205 ZZ" not flagged; threshold from config | S | Fires on 1001, brief expects 2 findings | P | 03 | FR-5; OQ-101, OQ-222, OQ-434 |
| CA-10 | Heuristic `possible_duplicate`: blocking by `normalize_mpn` + manufacturer alias, then fuzzy within manufacturer; group cap | CA-05, CA-01 | Heuristic | Exact block = 0.9; fuzzy >= threshold = 0.7; near O(n) on 100 k; never auto-merged | L | Scorer/scale, block size, scope | P | 03 | FR-6, NFR-1; OQ-102, OQ-113, OQ-129, OQ-11, OQ-248 |
| CA-11 | Heuristic `category_mismatch_candidate` via keyword to expected category map | CA-05 | Heuristic | 1002 flagged low 0.70 with keyword evidence | M | Map content and owner | P | 03 | FR-7; OQ-107, OQ-5 |
| CA-12 | Heuristic `conflicting_source_values` across systems | CA-10 | Heuristic | Each system's value listed in evidence | S | Compared fields undefined | P | 03 | FR-6; OQ-123 |
| CA-13 | Input scanner and `suspicious_content` flag (routes record to rule-only) | CA-05 | Scanner | Seeded "ignore previous instructions" text flagged; record skipped for AI | M | Pattern list | P | 03, 01 | NFR-5; OQ-121, OQ-407, OQ-315 |
| CA-14 | Severity/confidence policy table and explanation templates (approved wording only, forbidden words blocked) | CA-06, CA-07, CA-08, CA-09, CA-11 | Policy + templates | Every finding has explanation, evidence, suggested action, source; zero forbidden terms | M | Severity table incomplete | S | 02, 09 | FR-9, NFR-3, NFR-4; OQ-4, OQ-106, OQ-217, OQ-221, OQ-219 |
| CA-15 | Golden fixture test using brief sample (assertion mode agreed) | CA-14 | Acceptance test | Matches approved assertion mode for 1001 and 1002; input unchanged | S | Acceptance semantics | S | 02, 03 | FR-2, FR-7; OQ-12, OQ-432 |
| CA-16 | Database schema, forward-only migrations (expand/contract), DB roles/grants, hash-chained audit table design | F-07, CA-04 | Schema + migration set | Migration applies and rolls forward on empty DB; uniqueness on dedupe key; grants deny UPDATE/DELETE on append-only tables | L | Extra tables (`batch_chunk`, `export`) unapproved | S | 05 | NFR-5, NFR-6; OQ-126, OQ-27, OQ-109, OQ-114, OQ-243 |
| CA-17 | Repository layer and DB session helper | CA-16 | Repositories | All queries parameterised; session helper opens one transaction per unit of work; `ON CONFLICT DO NOTHING` inserts idempotent | M | None identified | S | 05 | NFR-5 |
| CA-18 | API: `POST /api/v1/batches` with idempotency key + file SHA-256, store raw file, enqueue | CA-17, W-01 | Endpoint | Same file returns existing `batch_id`; 202 with `batch_id`; bad file gives 422 with position | L | Empty-file code; limits; conflict code | S | 04 | FR-1; OQ-17, OQ-110, OQ-111, OQ-118 |
| CA-19 | API: batch status and cursor-paginated findings with filters | CA-17 | Endpoints | Filters by type/severity/source/status; `next_cursor` stable; findings carry all FR-9 fields | M | None | P | 04 | FR-9; OQ-103 |
| CA-20 | Batch and chunk state machine and completion (`done`/`ai_partial`/`empty`/`failed`) | CA-16, W-01 | State logic | Batch completes only when all chunks done or ai_partial; failed chunks handled per policy | M | Partial-failure outcome | S | 05, 06 | NFR-2; OQ-139 |

### WS3 AI / LLM integration

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| AI-01 | AI Access Layer module skeleton (in-process, ADR-017): `complete()` interface, request schema validation, kill-switch check, structure test forbidding other provider-SDK imports | S-01, F-08 | In-process module | Rejects calls when `ai_layer_enabled` false; build fails if another module imports a provider SDK | M | None (no service, no mTLS hop) | S | 07 | NFR-2, NFR-5; OQ-250 |
| AI-02 | PII and sensitive data masking, per-task field allow-list, opaque keys for `item_id` | AI-01 | Masking stage | Seeded emails/phones/pricing absent from LLM request logs; only allow-listed fields sent | L | PII patterns vs part numbers | S | 07 | NFR-5; OQ-406, OQ-206, OQ-306 |
| AI-03 | Single-provider adapter (Bedrock proposed) behind a small interface, one configured model per task (small/fast, mid), retry with backoff; no failover, no escalation | AI-01 | Adapter + config | 5xx/429/timeout retried then `provider_error`; model IDs pinned from registry | M | Model IDs unset (OQ-700) | P | 07 | NFR-2; OQ-207, OQ-301, OQ-700, OQ-511 |
| AI-04 | Token budgets, rate limits, circuit breaker, per-batch and daily caps | AI-03 | Budget enforcement | Over-budget call blocked with `policy_block`; daily cap blocks at 100 % | M | Budget values undecided | P | 07 | NFR-7; OQ-204, OQ-205, OQ-304, OQ-543, OQ-15 |
| AI-05 | `embed()` and batched embedding pipeline (one embedding model; only taxonomy nodes and approved items) | AI-03 | Embedding function | Vector dimension consistent with the `vector(1024)` index; `model_id` stored per row | S | None (dimension conflict resolved, ADR-017) | P | 07, 10 | FR-6; OQ-21, OQ-208, OQ-302 (resolved) |
| AI-06 | Response cache keyed by `task_key`  | AI-03 | Cache | Retries and replays do not call the provider again | S | Scope/TTL | P | 07 | NFR-7; OQ-312, OQ-409 |
| AI-07 | AI call metadata logging to `ai_task` (model, prompt version, tokens, latency, retries, cache hit) | AI-03 | Logging | One metadata record per call; no raw text/PII | S | None | P | 07 | NFR-6 |
| AI-08 | Reference data service: versioned UoM, taxonomy, generic terms, aliases; read and approved write path | CA-17 | Service | Findings store version used; unauthorised write refused | M | Write path/role missing | P | 10, 12 | FR-3, FR-7; OQ-135, OQ-22, OQ-223, OQ-225, OQ-226, OQ-526 |
| AI-09 | Retrieval indexes (`taxonomy`, `approved_items`, `abbreviations`), Postgres full-text + vector with rank fusion (no reranker), top-5, on-change refresh + nightly delta (ADR-020) | AI-05, AI-08 | Retrieval service | Retrieval reads only the approved indexes; every result returned with id | M | Fusion parameters; HNSW params | S | 10 | FR-6, FR-7; OQ-228, OQ-230, OQ-232 (OQ-227, OQ-311 resolved) |
| AI-10 | Prompt registry and file format (`prompts/<task>/<version>.yaml`), active version per environment, canary percentage | F-05 | Registry | Promotion is a config change; every finding stores prompt version | M | Registry storage, naming | P | 12 | NFR-6; OQ-252, OQ-253, OQ-254, OQ-255 |

### WS4 Agent development

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| G-01 | Typed pipeline state and code-based triage (weak descriptions, ambiguous categories, uncertain duplicate pairs) | CA-14, AI-10 | Triage step | AI sees < 30 % of records on sample sets; records with `suspicious_content` never selected | M | Whether 1002 goes to AI | S | 08 | FR-6..FR-8, NFR-7; OQ-127, OQ-209, OQ-213, OQ-314 |
| G-02 | Read-only tool layer: `taxonomy_lookup`, `similar_items`, `manufacturer_alias`, `abbreviation_dictionary` (Pydantic args, limits, timeouts) | AI-09 | Tools | Unknown tool name or bad args logged as security event; max 3 calls per step | M | None | P | 08 | NFR-5 |
| G-03 | Category task handler: prompt, output schema, evidence fields, `unsure` option | G-01, G-02, AI-03 | Handler | Output schema-valid; cites input fields and retrieved ids | L | Model IDs; example curation | P | 08, AI docs | FR-7; OQ-301, OQ-307 |
| G-04 | Normalisation task handler: description normalisation and attribute extraction | G-01, G-02, AI-03 | Handler | Attributes grounded in the input text; abbreviation dictionary lookup exact | M | Extra grounding rule; issue type for FR-8 | P | 08 | FR-8; OQ-122, OQ-305, OQ-308 |
| G-05 | Duplicate task handler: `same_item`/`different`/`unsure` for candidate pairs | G-01, G-02, AI-03 | Handler | Differing attributes listed; `unsure` honoured | M | Pair cap | P | 08 | FR-6; OQ-213, OQ-314 |
| G-06 | Validation pipeline (schema, reference check, grounding, consistency, policy, calibration) | CA-14, AI-08 | `validation/` module | Hallucinated category rejected; fake evidence field rejected; forbidden wording rejected | L | Forbidden-term list; PII in rationale | S | 09 | FR-9, NFR-3; OQ-219, OQ-415 |
| G-07 | Rule/AI merge, confidence calibration and explanation composer | G-06 | Merge + composer | Agreement yields one finding with both sources; disagreement keeps both and flags; confidence < 0.5 shows as Investigate only | L | `source` model; calibration cold start | S | 09 | FR-9, NFR-4; OQ-18, OQ-218, OQ-215, OQ-303, OQ-313, OQ-214, OQ-23 |
| G-08 | Progress recording in `ai_task`/chunk status, resume, replay, loop guards (single repair, step counter, cap 2 calls; no escalation, ADR-018/019) | G-03 | Pipeline control | Crash resumes without repeating completed calls; replay does not touch live findings; `loop_guard_triggered` abort works | M | None (cap resolved) | S | 08 | NFR-2; OQ-211; OQ-300, OQ-20, OQ-210, OQ-421 (resolved) |
| G-09 | AI worker: consume `ai_task`, run the pipeline, write `ai_task` rows and final findings | G-08, G-07, W-03 | AI worker | Retry or replay does not double-bill (task_key); invalid output dropped, rule findings kept | L | Draft vs final findings table | S | 06, 08 | NFR-1, NFR-7; OQ-212, OQ-138, OQ-24 |

### WS5 Workflow orchestration

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| W-01 | Task app, queues `dqa-ingest`, `dqa-ai-tasks`, `dqa-export` with DLQs and visibility timeout, local ElasticMQ parity | F-03 | Worker app | Message carries `task_key`; non-retryable errors go to DLQ with reason | M | `maxReceiveCount` values | S | 06 | NFR-2; OQ-505, OQ-139 |
| W-02 | Rule-worker pipeline: chunking (50), per-chunk stages, batch-scope pass for cross-chunk checks, publish findings | W-01, CA-14, CA-17 | Rule worker | 10 k records < 30 s; chunk retry produces no duplicates; cross-chunk duplicates found | XL | Chunk vs batch-scope design | S | 06 | FR-1..FR-7, NFR-1; OQ-119 |
| W-03 | AI task fan-out: enqueue `ai_task` for uncertain records only; concurrency caps per provider | W-02 | Producer + consumer limits | Cap respected; no AI tasks when flag off; batch `ai_partial` when skipped | M | Priority when budget is hit | S | 06 | NFR-2, NFR-7; OQ-304, OQ-309 |
| W-04 | Finding state machine and decision API (approve/reject with reason code/investigate/edit-and-approve), one active decision per finding | CA-17, CA-19 | Decisions endpoint | Illegal transitions rejected; resubmission is a no-op; decision in audit log | L | Reason codes; display boundary | S | 11 | FR-10; OQ-6, OQ-133, OQ-23 |
| W-05 | Bulk decisions (max 500, 207 per-item) behind flag `bulk_approve_enabled` | W-04 | Bulk endpoint | Mixed results reported per item; flag off blocks | M | High-impact items in bulk | P | 11 | FR-10; OQ-236, OQ-245 |
| W-06 | Four-eyes: second approver for high-impact actions | W-04 | Approval rule | Same user cannot self-approve; threshold from config | M | Definition of impact, N, state | P | 11 | FR-10; OQ-10, OQ-233, OQ-238, OQ-239, OQ-404 |
| W-07 | Export job: change file of approved findings to S3, signed URL, audit event | W-04 | Export | Contains only approved findings; no write to records; URL expiry enforced | L | Format, URL mechanism | S | 11 | FR-11, NFR-3; OQ-07, OQ-134, OQ-240, OQ-241, OQ-132, OQ-237 |
| W-08 | "Investigate" ticket webhook (ServiceNow/Jira) and return path | W-04 | Webhook client | Failed webhook retried; finding stays `investigating`; secrets not in logs | M | Ticketing system unknown | P | 11 | FR-10; OQ-29, OQ-242, OQ-244, OQ-413 |
| W-09 | Batch completion notification (SSE or webhook) | CA-20 | Notification | Event delivered on completion; polling still works | S | Mechanism undecided | P | 04 | FR-1; OQ-08, OQ-117 |
| W-10 | DLQ replay tool and ops runbook | W-01 | Replay tool | Authorised replay processes a DLQ message once | M | Scope and authorisation | P | 06 | NFR-2; OQ-506 |
| W-11 | Re-run endpoint to trigger explicit re-analysis | CA-18 | Endpoint | Re-run creates a new run without violating SHA-256 uniqueness | M | Endpoint missing in HLD | P | 04, 06 | FR-1; OQ-125 |

### WS6 Security implementation

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| S-01 | Removed — superseded by ADR-023 (open access). Was: OIDC/SAML SSO token validation, 15-minute JWT, refresh, role claims | F-03 | Auth layer | Expired token refused; roles from IdP groups | L | IdP group mapping; SAML scope | S | 04, SEC | NFR-5; OQ-401, OQ-408 |
| S-02 | Removed — superseded by ADR-023 (open access). Was: RBAC matrix enforcement per endpoint (Uploader, Data Steward, Data Owner, Auditor, Platform Admin) | S-01, CA-19 | Authorisation | Every role x endpoint test passes; Uploader sees own batches only | M | Admin "metadata only" meaning | P | 04, SEC | NFR-5; OQ-400, OQ-405 |
| S-03 | Access-control grants and ownership tests: per-role DB grants on every table, Uploader own-batch, Platform Admin metadata-only, S3 bucket policies | CA-16, S-01 | Access control | Unauthorised access attempts (another user's batch, Admin reading content, UPDATE/DELETE on append-only tables) are denied and raise a security event | M | Security-event definition | P | 05, SEC | NFR-5; OQ-409 |
| S-04 | Hash-chained `audit_event` writer, verification job, SIEM forwarding | CA-16 | Audit | Tampering detected by verification; all events listed in HLD 5.7 recorded | L | Chain scope, cadence | P | 05, SEC | NFR-6; OQ-403, OQ-114, OQ-546 |
| S-05 | Prompt-injection protections integration: delimiters, scanner routing, output policy filter | CA-13, G-06 | Protections | Injection corpus cannot alter schema or produce approvals | M | Pattern coverage | P | 07, 09, SEC | NFR-5; OQ-407, OQ-315 |
| S-06 | Least-privilege DB roles for AI task handlers/workers (read-only reference data and snapshot, write to `ai_task` and draft findings) | CA-16 | DB roles | AI worker role cannot write other tables; verified by tests | M | Draft vs final findings tables | P | 05, 08 | NFR-5; OQ-24, OQ-212, OQ-138 |
| S-07 | API rate limiting, upload limits, WAF rules at edge | F-08 | Limits | Limits enforced and documented | M | Numeric limits unset | P | 04 | NFR-5; OQ-414 |
| S-08 | Data retention and deletion jobs (raw 2 y, audit 7 y) incl. erasure handling | CA-16 | Retention | Retention executed by policy; audit immutability preserved | M | Erasure vs immutability | P | 05, SEC | NFR-6; OQ-26, OQ-402, OQ-508, OQ-115 |
| S-09 | Model registry and governance record (approved models, versions, terms, evals, owner) | AI-10 | Registry | New model/prompt version cannot reach production without passing evals and approval | M | Owner and storage | P | 12, SEC | NFR-6; OQ-410, OQ-256, OQ-527 |
| S-10 | Security test pipeline: SAST, DAST, dependency/container scan, RBAC matrix, prompt-injection, PII leak tests | F-02, S-02 | Security CI | No critical/high open findings | M | Tool choice | P | SEC | NFR-5; OQ-416 |

### WS7 Testing and evaluation

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| T-01 | Unit test suites and coverage gates (85 % on `checks/`, `validation/`, `normalize/`) | F-02 | Gates | Gate fails below threshold; measurement basis documented | S | Coverage basis; 80 % vs 85 % rule | P | 02, 03, 09 | NFR-8; OQ-418, OQ-523 |
| T-02 | Invariant tests: no mutation, forbidden wording, explanation + evidence + source on every finding | CA-14 | Invariants | Fail if any finding lacks a field or output mutates input | S | Forbidden list | P | 02, 09 | NFR-3, NFR-4; OQ-415 |
| T-03 | Integration tests with real Postgres/queue containers: upload to findings, idempotent re-upload, grants | CA-18, W-02 | Integration suite | Runs in CI; re-upload returns same batch | M | CI runtime | P | 04, 05, 06 | FR-1; OQ-417 |
| T-04 | Golden two-record acceptance and edge-case fixtures (empty, malformed, null-heavy, > 100 k) | CA-15 | Fixture suite | Never a 500; matches approved assertion mode | S | Semantics unresolved | P | 01..03 | FR-1, FR-2, FR-7; OQ-12, OQ-432, OQ-434 |
| T-05 | Golden evaluation datasets (300-500 labelled records per AI task), labelling procedure | Approval gate | Datasets | Agreement target met; rare classes covered | L | Labelling capacity | P | AI, TEST | FR-6..FR-8; OQ-435 |
| T-06 | StubSuggester and recorded-response (cassette) harness for deterministic AI CI | AI-01 | Harness | AI-layer tests run in CI without network or cost | M | None | P | 07, 08 | NFR-7 |
| T-07 | Prompt regression gate in CI (F1 drop <= 1 point per class, schema-valid rate, cost/latency) | T-05, T-06 | Gate | Seeded regression fails the PR; results posted on PR | M | Tool choice, eval settings | S | 12, TEST | NFR-7; OQ-524, OQ-426 |
| T-08 | RAG evaluation: recall@5, MRR, faithfulness, answer relevance | AI-09, T-05 | RAG evals | recall@5 >= 0.9 target measured | M | Targets for MRR/faithfulness unset | P | 10, TEST | FR-7; OQ-427 |
| T-09 | Hallucination, adversarial and prompt-injection evaluation sets | T-05, G-06 | Adversarial suite | False-confident rate < 2 %; out-of-taxonomy suggestions = 0 after validation | M | Scanner false positives | P | 09, TEST | NFR-5; OQ-429 |
| T-10 | Performance and load tests: 10 k < 30 s, 100 k end to end, 50 concurrent uploads, findings p95 < 300 ms, AI >= 1 k records/min, 8 h soak | P2 exit | Perf suite | Targets met at 2x expected peak | L | Peak undefined; tool | P | 06, TEST | NFR-1, NFR-9; OQ-424, OQ-430, OQ-514, OQ-438 |
| T-11 | API and RBAC end-to-end tests: upload, approve, reject, investigate, export, audit log | W-07, S-02 | E2E | Audit log shows all events | M | UI absent (API-level only) | P | 04, 11 | FR-10, FR-11; OQ-420 |
| T-12 | Shadow-mode comparison harness (AI findings vs steward decisions) | G-09 | Comparison tooling | Precision per source and issue type computable | M | Hidden-findings flag | P | 11, TEST | HLD 1.6; OQ-28, OQ-249 |

### WS8 Observability

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| O-01 | Structured logging with `trace_id`, `batch_id`, `record_key`, `component`; no raw text or PII | CA-17 | Logging standard | A single trace id follows upload to decision; log scan finds no PII | M | None | P | OPS | NFR-6 |
| O-02 | Distributed tracing: spans per pipeline step and tool call | G-01 | Tracing | Spans carry `task_key`, attempt, outcome, drop reason | M | Sampling rate | P | 08, OPS | NFR-6; OQ-540 |
| O-03 | Metrics and dashboards: service health, batch pipeline, AI quality, AI cost, steward workflow | O-01 | Dashboards | Panels match HLD 9.8 list | M | Ageing threshold | P | OPS | NFR-1; OQ-545 |
| O-04 | LLM tracing (prompt-level) and masked prompt/response store (30 days, sampled) | AI-07 | LLM observability | 10 % prod / 100 % staging sampling; restricted access | M | Personal-data status | P | 07, OPS | NFR-6; OQ-541, OQ-549 |
| O-05 | Cost tracking: tokens x versioned price table per task,, per batch | AI-04 | Cost reporting | Cost per 1 k records and per approved finding reported | M | Price-table owner | P | 07, OPS | NFR-7; OQ-542, OQ-543 |
| O-06 | Alerts and runbooks per HLD 10.6 table; incident severities and escalation | O-03 | Alerts | Each alert has a runbook, route (Slack/PagerDuty) | M | Extra alert priorities; incident roles | P | OPS | NFR-2; OQ-544, OQ-547, OQ-548 |
| O-07 | Error tracking and DLQ alarms with taxonomy tags | W-01 | Error tracking | DLQ > thresholds alert; errors tagged by taxonomy | S | None | P | OPS | NFR-2 |

### WS9 Deployment

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| D-01 | Container images, SBOM, signing; admission check | F-02 | Image pipeline | Only signed images deploy | M | Admission controller choice | P | ENV | NFR-5; OQ-525 |
| D-02 | CD: staging deploy, E2E + smoke, manual promotion, canary 10 % to 50 % to 100 %, automatic abort on SLO breach | D-01, F-09 | CD pipeline | Aborted canary rolls back in < 5 min | L | Canary sample size | S | ENV | NFR-2; OQ-530 |
| D-03 | Feature flags wiring (Unleash): `ai_layer_enabled`, `ai_task.<task>.enabled`, `prompt.<task>.canary_pct`, `bulk_approve_enabled` | F-05 | Flags | Flipping a flag takes effect without deploy; cold-start default safe | M | Hosting/HA; propagation | P | 12 | NFR-2; OQ-516, OQ-250, OQ-249 |
| D-04 | Rollback and kill-switch rehearsal: app, prompt/model, AI layer, bad findings withdrawal | D-02, D-03 | Rehearsal record | Prompt flip < 1 min; AI kill-switch immediate; bulk withdrawal by version audited | M | Infra rollback procedure | S | ENV, 11 | NFR-2; OQ-528 |
| D-05 | Backups, cross-region copy and restore test; DR drill | F-07 | DR evidence | RPO 15 min and RTO 4 h demonstrated or gap raised | L | Daily snapshot vs 15 min RPO | P | INFRA | NFR-2; OQ-515, OQ-529 |
| D-06 | Production environment provisioning and handover | F-09, D-02 | Prod live (AI off) | Smoke suite passes in prod synthetic test data set | L | Account/regions; approvals | S | INFRA | OQ-501, OQ-512 |

### WS10 Production validation

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| V-01 | Production smoke suite with synthetic test data set: health, golden file, empty/malformed file, approve + export, one AI call per provider | D-06 | Smoke report | Exact expected findings within 2 minutes; graceful errors | M | Assertion semantics | S | TEST | HLD 10.2; OQ-12 |
| V-02 | Shadow mode (two weeks), AI findings hidden and compared with steward decisions | V-01, G-09, T-12 | Shadow report | Precision rules >= 85 %, AI >= 70 %, no critical/high security findings | L | Steward participation | S | all | HLD 1.6; OQ-28, OQ-249 |
| V-03 | Pilot group onboarding with canary AI | V-02 | Pilot | No SEV1/SEV2; budget burn within plan | L | Pilot group selection | S | all | HLD 10 |
| V-04 | 72-hour heightened post-release monitoring, twice daily dashboard reviews | V-03 | Monitoring log | No regression vs previous week | S | On-call ownership | S | OPS | OQ-547 |
| V-05 | Ongoing AI quality audit: weekly sample of 50 accepted AI findings; monthly golden re-run against production prompts | V-03 | Audit routine | Drift alerts defined and tested | S | None | P | OPS | HLD 10.4 |
| V-06 | Throughput baseline and measurement of 2x steward throughput metric | V-03 | Baseline report | Method and baseline agreed with owner | M | No baseline exists | P | BRD | HLD 1.6; OQ-13, OQ-431 |
| V-07 | GA gate review and sign-off | V-02, V-04, D-04 | Sign-off record | On-call engineer and product owner sign; rollback and kill-switch rehearsed | S | Named owners | S | all | OQ-423 |

### WS11 Steward UI (ADR-022; starts after the P3 API gate)

| ID | Description | Deps | Deliverable | Acceptance | Cx | Risks | Par | LLD | Req / Blockers |
|---|---|---|---|---|---|---|---|---|---|
| U-01 | Scaffold and design tokens: Vite + React + TS app, feature folders, CSS custom-property tokens, lint/format/strict TS | P3 API gate | Front-end skeleton | Builds; tokens defined once; no hard-coded palette/spacing; JS budget check wired | S | Token direction unconfirmed | S | 13 | OQ-807 |
| U-02 | Typed API client from the LLD 04/11 contract with error-body mapping and idempotency keys | U-01 | Client module | Types match contract JSON examples; errors map to the taxonomy | M | Contract drift in P2/P3 | P | 13, 04 | OQ-810..812 |
| U-03 | Removed — superseded by ADR-023 (open access). Was: Authentication: OIDC code + PKCE, token handling, role-based route/action visibility | U-02 | Auth module | Unauthenticated redirected; Uploader sees only own batches; no token in storage beyond decision | M | SPA token exposure | S | 13, security 3.2 | OQ-800, OQ-812 |
| U-04 | Upload screen with Idempotency-Key and 422/202 handling | U-03 | Upload feature | Brief sample upload shows queued then findings; malformed file shows position | M | Empty-file contract | P | 13, 04 | OQ-17, OQ-118 |
| U-05 | Batch status screen (polling baseline) with counts and ai_status | U-03 | Batch feature | Status and findings_by_type update without reload; ai_partial shown | S | SSE undecided | P | 13 | OQ-801 |
| U-06 | Findings table: cursor pagination, virtualised rows, source badge, confidence, severity ordering | U-03 | Table feature | 1M-row simulation scrolls without layout jank; all FR-9 fields visible | L | Performance at scale | S | 13 | OQ-811 |
| U-07 | Filters/sort/page/tab in the URL (type, severity, source, status) | U-06 | URL-state hooks | Shareable URL restores view; back/forward works | M | None | P | 13 | - |
| U-08 | Finding detail drawer: explanation, highlighted evidence, suggested value, decision history | U-06 | Drawer | Evidence fields highlighted; keyboard and focus managed | M | History endpoint missing | P | 13 | OQ-811 |
| U-09 | Decisions: approve/reject (reason code)/investigate/edit-and-approve; bulk with 207 per-item results | U-08 | Decision feature | Per-item failures shown; same decision twice is a no-op; four-eyes state shown | L | Reason codes, four-eyes state | S | 13, 11 | OQ-802..804, OQ-233 |
| U-10 | Export change file action and signed-URL download | U-09 | Export feature | Approved findings exported; link expiry handled | S | Format undecided | P | 13, 11 | OQ-7, OQ-240 |
| U-11 | Accessibility, visual-regression (320/768/1024/1440) and keyboard/reduced-motion tests | U-06 | UI test suite | axe clean; screenshots stable; full keyboard review flow | M | Flaky visuals | P | 13, testing | OQ-815 |
| U-12 | Playwright E2E: upload to findings to decide to export against staging | U-10 | E2E suite | Brief sample journey passes; audit log shows decision | M | Needs staging | S | 13, testing | - |
| U-13 | Performance budget and CSP: JS < 300 kB gz, CWV targets, strict CSP, no innerHTML | U-01 | Budget + CSP config | CI fails over budget; CSP blocks inline script; Lighthouse targets met | M | Hosting undecided | P | 13, security | OQ-808, OQ-813 |

## Task count summary

| Workstream | Tasks |
|---|---|
| WS1 Foundation and infrastructure | 10 |
| WS2 Core application development | 20 |
| WS3 AI/LLM integration | 10 |
| WS4 Agent development | 9 |
| WS5 Workflow orchestration | 11 |
| WS6 Security implementation | 10 |
| WS7 Testing and evaluation | 12 |
| WS8 Observability | 7 |
| WS9 Deployment | 6 |
| WS10 Production validation | 7 |
| WS11 Steward UI | 13 |
| **Total** | **115** (3 removed by ADR-023: S-01, S-02, U-03; 112 active) |

### Parallelism notes
- After F-04: CA-05, CA-01, CA-02 start together; CA-06..CA-13 are independent once CA-05 exists.
- F-06..F-10 (infra) run beside all application work until F-09.
- S-02..S-10 mostly parallel after S-01 and CA-16.
- AI-03..AI-07 parallel after AI-01; AI-08 can start right after CA-17.
- G-03, G-04, G-05 parallel after G-01/G-02; G-06 and G-07 are sequential.
- T-05 (labelling) starts at once and never blocks code until T-07.

## Architecture decisions
Task design follows ADR-001..ADR-010 ([ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)). Any task that would change one of them requires an ADR first. Tasks blocked by an OQ that concerns a technology choice (OQ-16, OQ-549) need the owner's confirmation at the approval gate.

## Dependencies
Same as [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): owner approval, answered blocking open questions, cloud and provider access, IdP, ticketing system, steward labelling capacity. "Approval gate" as a dependency means the written owner approval of the HLD, LLD, AI architecture and roadmap.

## Risks and edge cases
- Tasks with provisional choices (`PROVISIONAL` in the module docs) may change shape after owner answers; treat their acceptance text as a draft until the OQ is closed.
- Complexity is relative, unvalidated by a team; re-estimate after the approval gate.
- WS7 tasks T-05 and T-12 depend on steward time, which is outside engineering control.
- WS11 UI tasks depend on API endpoints that do not exist yet (batch list, finding detail, current user: OQ-810..812); UI code stays paused until P2/P3.
- The open-question list in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) is authoritative for ids; if an id cited here is missing there, the module document that introduced it is the source.

## Related documents
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) · [RISKS_AND_DEPENDENCIES.md](RISKS_AND_DEPENDENCIES.md) · [LLD index](../lld/LLD.md) · [TESTING_AND_EVALUATION.md](../testing/TESTING_AND_EVALUATION.md) · [OBSERVABILITY_AND_OPERATIONS.md](../operations/OBSERVABILITY_AND_OPERATIONS.md)
