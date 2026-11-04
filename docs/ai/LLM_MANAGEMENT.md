# LLM Management

## 1. Purpose

Define how LLM usage is governed: prompt and model versioning, token budgets, context window management, model configuration and degradation, rate limiting, caching, and cost optimisation, all through a single in-process AI Access Layer (one provider, two model tiers; ADR-017, ADR-018).

## 2. Scope

All LLM and embedding calls in DQA. Provider choice itself is ADR-001 (proposed in the HLD, unconfirmed by the user); this document is provider-neutral. Out of scope: agent logic (`AGENT_DESIGN.md`), threat model (`AI_GUARDRAILS.md`).

## 3. Detailed explanation

### 3.1 AI Access Layer as the single exit (in-process)

All completion and embedding traffic goes through one **in-process library module** of the worker image, exposing `complete()` and `embed()` (LLD 07). It is not a separate service: no HTTP endpoints, no deployment, no autoscaler, no service-to-service hop (ADR-017). Selected approach (ADR-006, user decision, realised in-process): a **custom thin layer** calling one provider through a small adapter interface, instead of LiteLLM. Handlers never import provider SDKs, so swapping the provider is an adapter and configuration change.

Responsibilities: provider adapter and credentials access, PII masking, field allow-lists, retries with backoff, token and cost budgets, provider-level response checks, call logging to `ai_task`, per-batch accounting, kill-switch enforcement. Network egress of the worker pod is restricted to the single LLM endpoint.

### 3.2 Prompt versioning

- Prompts are Git files `prompts/<task>/<version>.yaml` containing: system part, task part, JSON schema, 3-5 few-shot examples, eval thresholds (HLD 6.6).
- Semantic versions; changed only by PR with eval results attached (promptfoo / DeepEval in CI, HLD 7.3/8.7).
- A **prompt registry table** maps `task -> active version` per environment; promoting a version is a configuration change, not a deploy (rollback in under 1 minute, HLD 8.9).
- Canary: `prompt.<task>.canary_pct` sends a percentage of tasks to the new version (Unleash flag, ADR-007).
- Every finding stores `model_id`, `prompt_version`, `rule_version`, so it can be reproduced and explained after change.
- Few-shot examples come only from vetted steward decisions (OQ-307).

### 3.3 Model versioning and registry

- Models are pinned to exact provider versions; **no floating "latest"** (HLD 8.8). The actual pinned IDs are not yet chosen (OQ-301).
- Model registry: model, version, provider, data-processing terms (zero retention, region), evaluation scores, owner, approval status.
- Any new model or prompt needs passing evals and sign-off from the AI governance owner before production (HLD 5.8). Regression gate: no class may lose more than 1 F1 point vs the current version.
- Provider model updates are treated as a change: monthly golden-set re-run against production prompts detects silent drift (HLD 10.4).

### 3.4 Token budgets

| Budget | Default (HLD) | Enforced by | Notes |
|---|---|---|---|
| Per call | 2k input / 300 output tokens ("e.g." in HLD 3.6) | AI Access Layer | Configurable per task; values per task not specified (OQ-304) |
| Per batch | `ai_budget_per_batch_usd` = 25 USD (Finance/Product owner) | AI Access Layer + pipeline | Exceeded: skip remaining AI, batch `ai_partial` |
| Per day | Not specified in HLD; alerts at > 80 % (warn) and > 100 % (access layer blocks) | AI Access Layer | Value is an open question (OQ-304) |
| Per task | Max LLM calls: see `AI_GUARDRAILS.md` §3.5 (**2**: initial + one repair; ADR-018) | Pipeline step counter | OQ-300 resolved |
| Output | `rationale` ≤ 300 characters; output tokens capped | Schema + access layer | |

Token usage is recorded per call in `ai_task` (tokens_in, tokens_out, cost_usd, latency_ms) and aggregated per task type, batch, model and prompt version.

### 3.5 Context window management

- Per-record context only: one record (or pair) + retrieved references; no cross-batch memory.
- Field-level allow-list per prompt: only fields the task needs are sent; item ids replaced with opaque keys; pricing, contract terms, supplier bank details, personal data and internal cost centres are never sent (HLD 5.4).
- Trimming is by relevance: reduce retrieved items from the lowest rank, never truncate mid-record. If the record alone exceeds the input budget (very long field), route the record to rule-only (the input scanner flags very long fields).
- Retrieval is capped at top-k = 5 with ids.

### 3.6 Model configuration and degradation

| Situation | Action |
|---|---|
| Normal | Use the single configured model for the task (small/fast tier for normalisation; mid tier for category and duplicate adjudication); changing it is a config + eval change, not a runtime route |
| Provider timeout (30 s) / 5xx / 429 | Retry 2x with exponential backoff and jitter (1 s -> 8 s); then `provider_error`, chunk continues rule-only, batch `ai_partial` |
| Output invalid after 1 repair attempt | Drop AI finding, keep rule findings, log `ai_invalid_output` |
| Low confidence or `unsure` | No escalation to a bigger model; shown to the steward as "Investigate"; never re-asked in a loop |
| Budget exceeded or AI disabled by flag | Skip AI layer; deliver rule/heuristic findings; batch `ai_partial` |
| Provider down | Rule-only mode (degraded, not down) |
| AI schema-valid rate < 90 % | Auto-disable the affected AI task (alert) |

Models are chosen per task by evaluation. The HLD's Azure OpenAI secondary provider and top-tier model are dropped (ADR-017, ADR-018). Prompts are kept provider-neutral and the adapter is small, so vendor lock-in is mitigated without running a second provider.

### 3.7 Rate limiting and concurrency

- Provider rate limits (tokens/min) cap AI throughput (HLD 11.5); the `dqa-ai-tasks` consumers are scaled with KEDA and capped by provider limits.
- Concurrency cap per provider (HLD 4.2). Specific numbers are not in the HLD and must come from quota discovery (OQ-304).
- 429 handling: counts toward the retry policy, then the chunk degrades to rule-only; sustained 429s raise the "provider error rate" alert (> 5 % warn, > 20 % critical).
- Throughput target: ≥ 1k records/min with provider limits respected (HLD 7.8).
- The access layer's daily budget acts as a secondary limiter.

### 3.8 Caching

| Cache | Key | Effect |
|---|---|---|
| Result cache | `task_key = hash(record_key, task, prompt_version, model_id)` | Retries and replays never double-bill; cache hit is recorded in call metadata |
| Embedding cache | content hash + embedding model id | Avoid re-embedding unchanged items (on-change + nightly delta) |
| Retrieval | none initially | Embeddings refreshed on change plus nightly delta |

Scope and TTL of the result cache (retention window) are not specified: OQ-312. `record_key` (source system + item id) is unique within the single entity, so `task_key` is a sufficient cache key.

### 3.9 Cost optimisation

1. **Triage first**: only uncertain records go to AI; target < 30 % of records (HLD 11.4), tracked as a metric.
2. Right-size models: small/fast tier for the high-volume normalisation task; mid tier only for category and duplicate adjudication; no top tier.
3. Cache by `task_key`; no re-asks.
4. Batch / off-peak inference for non-urgent runs as an option (HLD 11.4; acceptability is OQ-702).
5. Per-batch USD budget guard enforced in the access layer, plus prompt caching where the provider supports it (OQ-701) and a hard kill-switch.
6. Rule-graduation: tasks with consistently low approval are re-tuned or turned off; rules with high approval graduate from heuristics (HLD 10.9).
7. Option to self-host an open-weight model for normalisation if pricing/terms change (HLD 11.3), not committed.

Cost target: AI cost per 1k records within an agreed budget, **target < USD 0.50** (HLD NFR; to be validated against the real pinned models). Cost = tokens x versioned price table, stored per AI task; dashboards, batch, task type and prompt version; monthly showback to business owners. Key unit metrics: cost per 1k records, cost per *approved* finding.

### 3.9a Cost model (assumption-labelled; no prices are stated here)

All inputs are variables to be filled from the provider's price list and measured token counts (OQ-15, OQ-207, OQ-204). Nothing below is a quoted price.

```text
records_to_ai      = N_records * ai_share                      # ai_share target < 0.30 (HLD 11.4); measured by triage
calls_per_task     = 1 + repair_rate                           # cap 2 (ADR-018); repair_rate measured
cost_task_t        = calls_per_task * (tok_in_t * price_in_model_t + tok_out_t * price_out_model_t)
cost_batch         = sum over tasks of cost_task_t * (1 - cache_hit_rate)
                     + embed_tokens * price_embed             # taxonomy + approved items only, on change
cost_per_1k_records= cost_batch / (N_records / 1000)          # target < USD 0.50 (HLD NFR) - to be validated
guard              = ai_budget_per_batch_usd (default 25)     # note: 0.50 per 1k implies up to 50 for 100k records (OQ-15)
```

Levers, in order of effect: lower `ai_share` (stricter triage), cache hits, smaller model tier per task, prompt caching, batch/off-peak inference for non-urgent runs, tighter token caps. The per-batch guard and the kill-switch bound the worst case. Measured values (tokens per task, repair rate, cache hit rate) are recorded in `ai_task` and reported on the AI cost dashboard.

### 3.10 Request/response metadata and retention

Per call: provider, model id, prompt version, temperature, input/output tokens, latency, finish reason, retry count, validation result, cache hit. Masked prompt and response bodies are stored for 30 days in a restricted store (sampled 10 % in production, 100 % in staging, HLD 9.3) in the database/S3 (no separate tracing service); LLM call metadata lives in the `ai_task` table plus OpenTelemetry spans and Prometheus metrics (ADR-021). Temperature value is not specified in the HLD (OQ-301).

## 4. Architecture decisions

| ADR | Decision |
|---|---|
| ADR-001 | Provider/models: proposed, unconfirmed; updated by ADR-017/018 (one provider, two tiers) |
| ADR-006 | Custom thin gateway (user decision), in-process per ADR-017 |
| ADR-007 | Unleash for flags (user decision), including canary percentage and kill-switch |
| ADR-003 | Embedding storage in pgvector |

## 5. Dependencies

AI Access Layer (LLD 07), config/flags/prompts (LLD 12), task pipeline (LLD 08), data layer (`ai_task`, LLD 05), observability (OTel, Prometheus), Secrets Manager for provider keys (rotation 90 days, HLD 8.6), Finance/Product for budgets.

## 6. Risks and edge cases

| Risk | Mitigation |
|---|---|
| Provider outage or throttling | Retries, then rule-only mode (single-provider dependency accepted; adapter limits lock-in) |
| Silent drift after provider update | Pinned versions, monthly golden re-run, approval-rate alerts (drop > 10 pts warn, > 20 pts critical) |
| Cost spike from large re-upload | Idempotent upload (same SHA-256 returns existing batch), `task_key` cache, per-batch cap |
| Budget cap hits mid-batch | Remaining AI skipped; which records get AI first is undefined (OQ-309) |
| Access layer failure inside a worker | Stateless; worker restarts; rule-only degradation; no extra service to fail |

## 7. Related documents

`AI_ARCHITECTURE.md`, `AGENT_DESIGN.md`, `AI_GUARDRAILS.md`, `../lld/modules/07-ai-gateway.md` (AI Access Layer), `../lld/modules/12-config-flags-and-prompts.md`, `../operations/OBSERVABILITY_AND_OPERATIONS.md`, `../project/ARCHITECTURE_DECISIONS.md`, `../project/OPEN_QUESTIONS.md`.
