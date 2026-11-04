# Observability and Operations — Data-Quality Assistant (DQA)

| | |
|---|---|
| Status | Draft for approval (no dashboards, alerts or runbooks exist yet) |
| Source | HLD PDF §5.7, §9.1–9.8, §10.1–10.9; Markdown HLD in [../hld/HLD.md](../hld/HLD.md) |

## 1. Purpose

Specify how DQA is observed and operated in production: logs, traces, agent and LLM telemetry, token and cost tracking, dashboards, alerting, incident management, and the post-live verification and monitoring routine. The governing principle (HLD §9): **one trace id follows a batch from upload through every rule, agent step, tool call and LLM request to the steward's decision**, so any finding can be explained and costed after the fact.

## 2. Scope

In scope: telemetry design, metrics/alerts per component, dashboards, incident process, post-live routines. Out of scope: the infrastructure itself ([../infra/INFRASTRUCTURE.md](../infra/INFRASTRUCTURE.md)), deployment mechanics ([../infra/ENVIRONMENTS_AND_DEPLOYMENT.md](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md)), the audit-trail data model ([../lld/modules/05-data-layer.md](../lld/modules/05-data-layer.md)). Metric *names* below are proposals for consistency; the HLD defines signals, not names (A-540).

## 3. Detailed explanation

### 3.1 Structured logging

- JSON logs (structlog) with mandatory fields: `trace_id`, `batch_id`, `record_key`, `component`, `level` (HLD §9.1). Proposed additional fields: `timestamp`, `event`, `task_key`, `rule_id`, `rule_version`, `prompt_version`, `model_id`, `error_code` (A-541).
- **No raw record text or PII in logs.** Values are masked or hashed; `item_id` is replaced by the opaque `record_key` when logged outward (HLD §5.4 treats raw `item_id`s as not to be sent externally; logs follow the same rule, A-542).
- Error codes follow the taxonomy: `parse_error`, `provider_error`, `ai_invalid_output`, `policy_block`, `loop_guard_triggered`, `timeout`. Any new code needs a documented addition.
- Transport: Fluent Bit → CloudWatch / OpenSearch; 30 days hot, 1 year archive (HLD §9.1).
- Log-injection safety: record text is never interpolated into log format strings; free text is escaped and length-limited.
- Security events (unexpected tool names, argument-validation failures, unauthorised access attempts) carry `event_class=security` and are also forwarded to the SIEM (see 3.9).

### 3.2 Distributed tracing

OpenTelemetry. A trace starts at `POST /api/v1/batches` and propagates through queue messages (trace context carried in the message envelope; A-543), workers, the in-process AI access layer and LLM calls.

| Span | Component | Key attributes |
|---|---|---|
| `api.request` | api | route, status, idempotency outcome |
| `batch.ingest` | rule-worker | batch_id, chunk_id, records |
| `stage.rules` / `stage.heuristics` | rule-worker | rule_id, rule_version, findings_count, duration |
| `pipeline.triage` | ai-worker | tasks_created by type |
| `pipeline.category_task`, `pipeline.normalisation_task`, `pipeline.duplicate_task` | ai-worker | task_key, attempt, outcome (**accepted / downgraded / dropped**), drop_reason |
| `pipeline.validator` | ai-worker | checks failed (schema, reference, grounding, consistency, policy, calibration) |
| `pipeline.composer`, `pipeline.persist` | ai-worker | finding_id |
| `tool.<name>` | ai-worker | tool, masked args, result_count, latency, error |
| `ai_access.complete` / `ai_access.embed` | ai-worker (in-process) | model_id, tokens, latency, retries, cache_hit |
| `decision.create` / `export.generate` | api / rule-worker | decision_id, approval_level |

HLD requires per-step spans with `task_key`, `attempt`, `outcome` and drop reason (§9.2). Langfuse is dropped (ADR-021): LLM call metadata is in the `ai_task` table plus these OTel spans and Prometheus metrics; masked sampled prompt/response bodies are kept in the restricted store for inspection and replay. Sampling: 100% of error and AI spans; baseline sampling rate for others is not specified (OQ-540).

### 3.3 Agent execution monitoring

Per run and per step: step count, tool calls per task (cap 3 per handler step), LLM calls per task (cap 2), repair rate, `loop_guard_triggered` count (target 0, HLD §7.6), progress-write latency, chunk stage duration (timeout 5 min), batch duration (timeout 2 h → `ai_partial` + alert).

Trajectory dashboards compare replayed batches (step counts, repairs) as in the agent evaluation plan ([../testing/TESTING_AND_EVALUATION.md](../testing/TESTING_AND_EVALUATION.md)).

### 3.4 LLM request/response monitoring

Recorded per call (HLD §9.3): provider, model id, prompt version, temperature, input/output tokens, latency, finish reason, retry count, validation result, cache hit.

Masked prompt and response **bodies** are stored 30 days in a restricted store: sampled **10% in production**, **100% in staging**. Access to that store is restricted to named roles (see [../security/SECURITY_AND_GOVERNANCE.md](../security/SECURITY_AND_GOVERNANCE.md)); whether any prompt body counts as personal data despite masking is OQ-541.

### 3.5 Token usage and cost tracking

- Tokens (in/out) and cost per call are stored in `ai_task` (`tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`) and aggregated per task type, batch, model and prompt version (HLD §9.4, §9.7).
- Cost = tokens × versioned price table per model (HLD §9.7). Source and update process of the price table: OQ-542.
- Budgets enforced in the AI access layer: per batch (`ai_budget_per_batch_usd`, default 25) and per day. Daily budget value is not given (OQ-543).
- Unit metrics: **cost per 1k records** (target < USD 0.50, HLD §1.5) and **cost per approved finding**.
- Monthly showback report to business owners (HLD §9.7).

### 3.6 Metrics (proposed catalogue)

| Domain | Metrics |
|---|---|
| API | request rate, latency p50/p95/p99, 4xx/5xx rate per route |
| Pipeline | batches by status (`queued`, `empty`, `done`, `ai_partial`, plus failure states defined in LLD 06), time-to-first-finding, time-to-complete, records/s per chunk |
| Queues | depth, oldest-message age, in-flight, DLQ size, DLQ arrival rate |
| Workers | pod count, KEDA scale events, task failures by error code, retries |
| Database | CPU, connections, replication lag, p95 query latency, deadlocks, storage, vector search p95, vector count |
| Redis | memory, evictions, hit ratio |
| AI quality | schema-valid rate, drop rate by reason, `unsure` rate, repair rate, grounding failures, steward approval rate by source/issue type/prompt version, rejection reason mix |
| AI cost | tokens and USD by task/model, budget burn, cost per 1k records |
| LLM provider | provider error rate, 429 rate, retry count, latency (single provider) |
| Security | unauthorised access attempts, prompt-injection `suspicious_content` flags, policy blocks, unexpected tool names |
| Workflow | open findings, decisions/hour, ageing of open findings, four-eyes pending |

### 3.7 Dashboards (HLD §9.8)

| Dashboard | Panels |
|---|---|
| Service health | request rate, p95 latency, 5xx rate, pod health, queue depth, DLQ size |
| Batch pipeline | batches by status, time-to-first-finding, time-to-complete, `ai_partial` rate |
| AI quality | schema-valid rate, drop rate by reason, `unsure` rate, approval rate by source and prompt version |
| AI cost | tokens and USD by task/model, cost per 1k records, budget burn |
| Steward workflow | open findings, decisions/hour, rejection reasons, ageing of open findings |

Proposed addition: **Data & vector** (DB, replication lag, vector count and p95 search latency against the 10M / 100 ms migration triggers) and **Security** (unauthorised access attempts, injection flags). Stack: Prometheus + Grafana, Sentry (HLD §2.3; Langfuse dropped, ADR-021).

### 3.8 Alert thresholds (HLD §10.6)

Warning → Slack (P3). Critical → PagerDuty (P1/P2).

| Signal | Warning (Slack) | Critical (PagerDuty) |
|---|---|---|
| API 5xx rate | > 1% for 5 min | > 5% for 5 min |
| Findings API p95 latency | > 500 ms | > 2 s |
| Ingest queue age | > 5 min | > 20 min |
| DLQ messages | > 10 / hour | > 100 / hour |
| AI schema-valid rate | < 97% | < 90% (**auto-disable that AI task**) |
| AI approval rate (7-day) | drop > 10 pts | drop > 20 pts |
| Daily AI cost | > 80% of budget | > 100% of budget (**access layer blocks**) |
| Provider error rate | > 5% | > 20% (AI degrades to rule-only) |
| Loop-guard / policy blocks | any | > 10 / hour |
| Unauthorised resource access attempt | — | any (security incident) |

Proposed extra alerts not in the HLD (A-544): vector search p95 > 100 ms or vector count > 10M (migration trigger); replication lag; batch exceeding 2 h; audit-hash-chain verification failure; DLQ without consumer; secret rotation failure; certificate expiry; `ai_layer_enabled` flag service unreachable. Which of these become P1/P2 is OQ-544.

### 3.9 Component → metric → alert mapping

| Component | Key metric(s) | Alert |
|---|---|---|
| CloudFront/WAF/ALB | 5xx, blocked requests, TLS errors | API 5xx rate; WAF spike (A-544) |
| `api` | latency p95, 5xx, auth failures | API 5xx; findings p95 |
| `rule-worker` | task failures, chunk duration, queue age | Ingest queue age; DLQ |
| `ai-worker` (incl. in-process AI access layer) | schema-valid, drops, loop-guard, repair rate, provider errors, 429, tokens, budget burn | AI schema-valid; loop-guard blocks; provider error rate; AI cost |
| Task/chunk progress tables (Postgres) | write latency, table size | DB alerts (A-544) |
| RDS PostgreSQL | CPU, connections, lag, storage, vector p95 | DB + vector-trigger alerts (A-544) |
| pgvector index | count, p95 search, index build time | > 10M / > 100 ms |
| ElastiCache Redis | memory, evictions | (A-544) |
| SQS queues | depth, age, DLQ count | Queue age; DLQ messages |
| S3 | 4xx/5xx, replication status | Replication failure (A-544) |
| Secrets/ESO | sync failures, rotation status | Rotation failure (A-544) |
| Unleash | evaluation errors, latency | Flag service unreachable (A-544) |
| Audit trail | chain verification, SIEM forwarding lag | Chain break; forwarding failure (A-544) |
| Steward workflow | open-finding ageing | Ageing threshold (OQ-545) |

Every major infrastructure component must have at least one metric and one alert; the table is the checklist for the documentation review.

### 3.10 Audit and SIEM

The `audit_event` table is append-only and hash-chained (`prev_hash`, `hash`); events are streamed to the SIEM (Splunk); retention 7 years (HLD §5.7). Operations verifies the chain on a schedule (frequency: OQ-546) and alerts on mismatch. Events cover upload, finding creation (rule id/version or model id + prompt version), decisions (user, time, before/after, reason), exports, configuration and prompt changes.

### 3.11 Incident management (HLD §10.7)

| Severity | Example | Response |
|---|---|---|
| **SEV1** | Data exposure to unauthorised users; PII sent to an LLM unmasked | Page immediately; **kill-switch AI**; security team engaged; 15 min ack |
| **SEV2** | Pipeline down; wrong findings at scale | Page; rollback or disable the AI task; 30 min ack |
| **SEV3** | Degraded AI quality; one workflow slow | Ticket; next business day |

Process: detect (alert) → acknowledge → triage (dashboards, trace id) → mitigate (kill-switch / flag / rollback / bulk-retract by `prompt_version`) → communicate → resolve → blameless post-mortem for SEV1/SEV2 within 5 business days with tracked action items. Runbook per alert. Incident commander role, comms channel and status-page policy are not defined in the HLD (OQ-547). Regulatory notification duties on a SEV1 data exposure (GDPR/DPDP examples in the HLD) are unstated (OQ-548).

### 3.12 Human escalation (HLD §10.8)

Steward → Data Owner (high-impact/uncertain findings, four-eyes) · Data Owner → source-system owner (*Investigate* → ServiceNow/Jira ticket with evidence) · Steward/Owner → DQA product team ("report bad suggestion" button, weekly triage queue) · On-call → Engineering lead → Security / AI governance owner (SEV1/2, AI policy issues).

### 3.13 Post-live verification (after each release)

Same checklist as [../infra/ENVIRONMENTS_AND_DEPLOYMENT.md](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md) §3.10. Summary:

1. Confirm version, migrations, flags (AI canary %).
2. Run smoke suite with the synthetic test data set: health endpoints; golden two-record upload (known findings within 2 min); empty and malformed uploads; approve + export + audit entry; one AI call per provider.
3. Check dashboards: error rate, queue depth, AI schema-valid rate and cost burn at baseline.
4. Verify audit events and SIEM forwarding for the smoke batch.
5. Verify the kill-switch (off/on on the test data set).
6. Sign-off by on-call engineer and product owner in the release ticket.

### 3.14 Post-live monitoring

| Cadence | Activity |
|---|---|
| 72 h after each release | Heightened watch: on-call reviews service, pipeline and AI-quality dashboards **twice a day**; any regression vs. the previous week triggers a rollback discussion (HLD §10.3) |
| Continuous | Approval rate by source/issue type/prompt version (leading indicator of quality drift); rejection reason mix; schema-valid, drop, `unsure`, repair rates (HLD §10.4) |
| Daily | Cost vs budget; cost per 1k records; cost per approved finding; p95 AI-task latency; 429 rate (HLD §10.5) |
| Weekly | Sampled human audit of **50 accepted AI findings**; budget review with product; steward decisions flow into labelled dataset (after QA); "report bad suggestion" triage |
| Monthly | Golden-set re-run against production prompts to detect provider model drift; golden set refresh; cost showback report |
| Quarterly | Review thresholds, taxonomy, generic-term list, cost; third-party script/dependency audit; alert threshold review |
| Twice a year | DR drill |

### 3.15 Runbook index (to be written; one per alert)

| Runbook | Trigger |
|---|---|
| RB-01 API 5xx / latency | API 5xx, findings p95 |
| RB-02 Ingest queue age / worker stall | Queue age |
| RB-03 DLQ triage and replay | DLQ messages |
| RB-04 AI schema-valid rate drop / auto-disabled task | Schema-valid < 97% / < 90% |
| RB-05 AI approval rate drop (quality drift) | Approval drop |
| RB-06 AI cost / budget breach | Cost > 80% / 100% |
| RB-07 Provider errors (rule-only degradation) | Provider error rate |
| RB-08 Loop-guard / policy blocks | Loop-guard, policy |
| RB-09 Unauthorised resource access attempt (security incident) | Any |
| RB-10 PII-to-LLM incident | SEV1 |
| RB-11 Kill-switch procedure | Any AI incident |
| RB-12 Bulk-retract by prompt/rule version | Bad findings published |
| RB-13 Database failover / restore / PITR | DB alerts |
| RB-14 Vector store migration trigger | >10M vectors / p95 >100 ms |
| RB-15 Secret rotation failure | ESO/rotation alert |
| RB-16 Audit chain / SIEM forwarding failure | Audit alerts |
| RB-17 DR failover | Regional disaster |

## 4. Architecture decisions

| ADR | Relevance |
|---|---|
| ADR-010 / ADR-019 | Fixed pipeline with code-based triage/validator makes per-step spans and outcome telemetry possible |
| ADR-006 / ADR-017 | The single in-process AI access layer is the one place for LLM metadata, budgets and masking logs |
| ADR-003 | Vector migration triggers are monitored signals |
| ADR-002 / ADR-019 | `ai_task` progress in Postgres provides resume and replay; tracing at step level |
| ADR-008 / ADR-015 / ADR-021 | OpenTelemetry/Prometheus/Grafana/Sentry stack, no Langfuse (HLD proposal minus Langfuse; unconfirmed: OQ-549) |

## 5. Dependencies

[../infra/INFRASTRUCTURE.md](../infra/INFRASTRUCTURE.md) · [../infra/ENVIRONMENTS_AND_DEPLOYMENT.md](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md) · [../ai/LLM_MANAGEMENT.md](../ai/LLM_MANAGEMENT.md) · [../ai/AI_GUARDRAILS.md](../ai/AI_GUARDRAILS.md) · [../security/SECURITY_AND_GOVERNANCE.md](../security/SECURITY_AND_GOVERNANCE.md) · External: PagerDuty, Slack, Splunk SIEM, Sentry, CloudWatch/OpenSearch, Grafana/Prometheus.

## 6. Risks and edge cases

| Risk | Mitigation |
|---|---|
| PII or record text leaking into logs/traces | Masking/hashing at the logger; log-schema tests; PII-leak test in CI (HLD §7.7) |
| Trace context lost across the queue | Carry trace context in message envelope; test end-to-end trace continuity |
| Alert fatigue | Thresholds reviewed quarterly; warning vs critical split |
| 10% prompt-body sampling misses rare failures | Errors and dropped outputs sampled at 100% (A-545) |
| Observability cost (OTel volumes) | Sampling policy; retention limits |
| Auto-disable of an AI task at < 90% schema-valid rate hides the cause | Alert + runbook RB-04; keep failed outputs (masked) for debugging |
| Dashboards looking healthy while AI is wrong (HTTP success ≠ task success) | Quality metrics are first-class: approval rate, grounding failures, weekly human audit |
| Metrics cardinality explosion (per record_key) | `record_key` in logs and traces only, never as a metric label |
| Clock skew breaks hash-chain ordering | Server-side timestamps; chain order by sequence, not wall-clock (A-546) |
| Observability stack down | Monitor-the-monitor; app must not fail when telemetry is unavailable |

## 7. Related documents

[../infra/INFRASTRUCTURE.md](../infra/INFRASTRUCTURE.md) · [../infra/ENVIRONMENTS_AND_DEPLOYMENT.md](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md) · [../testing/TESTING_AND_EVALUATION.md](../testing/TESTING_AND_EVALUATION.md) · [../security/SECURITY_AND_GOVERNANCE.md](../security/SECURITY_AND_GOVERNANCE.md) · [../project/OPEN_QUESTIONS.md](../project/OPEN_QUESTIONS.md) · [../project/RISKS_AND_DEPENDENCIES.md](../project/RISKS_AND_DEPENDENCIES.md)

## Appendix — Assumptions and open questions introduced here

| ID | Text |
|---|---|
| A-540 | Metric names/labels are proposals; the HLD specifies signals only |
| A-541 | Extra log fields (`timestamp`, `event`, `task_key`, `rule_id`, `rule_version`, `prompt_version`, `model_id`, `error_code`) are added to the HLD's six |
| A-542 | Logs use opaque `record_key`, not raw `item_id` |
| A-543 | Trace context travels in the queue message envelope |
| A-544 | Extra alerts beyond HLD §10.6 (vector triggers, replication lag, batch >2 h, audit chain, rotation, flag service, WAF, S3 replication, Redis) |
| A-545 | Errors and dropped AI outputs are sampled at 100% regardless of the 10% production body sampling |
| A-546 | Audit-chain ordering uses a server-side sequence, not client time |
| OQ-540 | Baseline trace sampling rate for non-AI/non-error spans? |
| OQ-541 | Does masked prompt/response storage still count as personal data (retention/access implications)? |
| OQ-542 | Who maintains the versioned model price table and how often? |
| OQ-543 | Value of the daily AI budget? |
| OQ-544 | Which proposed extra alerts are P1/P2 vs P3? |
| OQ-545 | Alert threshold for ageing of open findings? |
| OQ-546 | Frequency/owner of audit hash-chain verification? |
| OQ-547 | Incident commander role, comms channel and status-page policy? |
| OQ-548 | Regulatory notification obligations/timelines on SEV1 data exposure? |
| OQ-549 | Confirm observability stack (OpenTelemetry, Prometheus, Grafana, Sentry, Fluent Bit, PagerDuty, Slack) as proposed by the HLD? |
