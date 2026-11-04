# LLD 12 — Configuration, Feature Flags and Prompt Management

## 1. Purpose

Define how DQA stores and changes **parameters** (thresholds, limits), **feature flags** (kill-switches, canaries) and **prompts**, so that behaviour changes are versioned, auditable and reversible without a deploy where the HLD requires it (HLD §6.2, §6.6, §6.7, §8.8, §8.9).

## 2. Scope

In scope: parameter catalogue with defaults and owners; Unleash flag model (ADR-007); prompt file format and registry; prompt promotion, canary and rollback; single-model-per-task configuration; audit of changes; kill-switch behaviour.

Out of scope: reference-data lists (LLD 10), provider calls (LLD 07), CI/CD pipeline details (`docs/infra/ENVIRONMENTS_AND_DEPLOYMENT.md`). Real prompt text is authored later; this LLD defines the structure and rules only.

## 3. Detailed explanation

### 3.1 Responsibilities

1. Serve typed parameters to all services with a documented owner and default.
2. Evaluate flags and expose a local cached snapshot to services.
3. Maintain a **prompt registry** (`task → active version` per environment); promotion is a config change, not a deploy (HLD §6.6).
4. Stamp every finding with `rule_version`, `prompt_version`, `model_id` and reference versions.
5. Record each configuration/flag/prompt/model change in `audit_event`.
6. Guarantee safe defaults when the flag service is unavailable.

### 3.2 Input and output

| Aspect | Definition |
|---|---|
| Input | Parameter values (config store), flag definitions (Unleash), prompt files in Git (`prompts/<task>/<version>.yaml`), registry rows |
| Output | Resolved configuration objects per request; flag decisions; active prompt version per task; change audit events |

### 3.3 Parameter catalogue (HLD §6.2)

| Parameter | Default | Owner | Consumed by |
|---|---|---|---|
| `allowed_uom` | EA, PC, BOX, KG, M, L, SET, PR | Steward (reference data) | LLD 02, 09 |
| `min_description_tokens` | 3 | Steward | LLD 03 |
| `generic_terms` | bearing, valve, part, item, misc, spare | Steward | LLD 03 |
| `dup_similarity_threshold` | 0.88 | Engineering, tuned by eval | LLD 03 |
| `ai_uncertain_band` | 0.75–0.88 | Engineering | LLD 03 (triage), 08 |
| `ai_min_confidence_display` | 0.5 | Product | LLD 09 |
| `chunk_size` | 50 | Engineering | LLD 06, 08 |
| `ai_budget_per_batch_usd` | 25 | Finance / Product | LLD 07 |
| `four_eyes_threshold_items` | 10 | Data Owner | LLD 11 |

Further parameters stated elsewhere in the HLD and needing a home in this catalogue (values from HLD; owner **not stated**, **OQ-246**): per-call token budget 2k in / 300 out (§3.6); max 3 tool calls per step (§3.8); max 2 LLM calls per task (§4.8; confirmed as the cap by ADR-018, OQ-20 resolved); max file size 100k rows (§6.3); bulk decision max 500 (§6.4); LLM timeout 30 s / 2 retries; embedding 10 s / 3; tool 2 s / 1; chunk stage 5 min / 3; batch 2 h (§4.6); rate-limit values; daily budget (not given, OQ-204); calibration-table refresh cadence (not given).

Storage mechanism: the HLD says thresholds and reference data are "versioned in `reference_data`" (§6.6) while `allowed_uom`/`generic_terms` are reference data and `dup_similarity_threshold` etc. are engineering parameters. Whether engineering parameters live in `reference_data`, in Helm values/ConfigMaps, or in Unleash variants is **OQ-247**. Provisional approach (A-226): steward-owned items in `reference_data`; engineering/product items as versioned config loaded at startup and hot-reloadable, each change audited; **every finding stores the versions used**.

Scale note: `dup_similarity_threshold` is written as 0.88 and RapidFuzz scores are 0–100 by default: units must be fixed in config (**OQ-248**).

### 3.4 Feature flags (HLD §6.7; ADR-007)

| Flag | Type | Purpose | Default (proposed) |
|---|---|---|---|
| `ai_layer_enabled` | boolean | Kill-switch for all LLM calls | on in prod after go-live; **off in shadow? see OQ-249** |
| `ai_task.<task>.enabled` | boolean per task | Turn individual AI tasks on/off (`category_check`, `normalise_description`, `duplicate_adjudication`) | on |
| `prompt.<task>.canary_pct` | number (0–100) | Percentage of tasks on a new prompt version | 0 |
| ~~`model.<task>.route`~~ | removed | Primary/secondary route dropped: one provider, one model per task selected by configuration and evaluation (ADR-017/018) | n/a |
| `bulk_approve_enabled` | boolean | Gate bulk approvals | off until enabled (A-227) |

Flags are evaluated via Unleash context (`environment`, optionally `batchId` for canary stickiness). Canary assignment is **stable per task_key** (hash of `task_key` mod 100 < `canary_pct`) so retries and replays hit the same version (A-228).

Shadow mode (HLD §10: AI findings hidden and compared with steward decisions for two weeks): the HLD does not define a flag that produces hidden AI findings. A `ai_findings_visible` flag is **proposed** (A-229, **OQ-249**) rather than assumed.

```mermaid
sequenceDiagram
    autonumber
    participant Ops as Operator / automation
    participant U as Unleash (admin)
    participant SDK as Service SDK cache (worker AI access layer, pipeline, API)
    participant G as AI Access Layer (in-process)
    participant DB as audit_event

    Ops->>U: set ai_layer_enabled=false
    U->>DB: change event (webhook) -> audit
    U-->>SDK: streaming/polling update (interval: OQ-250)
    G->>SDK: isEnabled(ai_layer_enabled)
    SDK-->>G: false
    G-->>G: reject new AI calls (ai_disabled); in-flight calls complete
    Note over G: rule + heuristic pipeline unaffected, batch -> ai_partial
```

Kill-switch latency requirement: HLD §8.9 "Immediate". Propagation interval and in-flight-call handling: **OQ-250**. If the flag service is down, services use the **last known snapshot**; with no snapshot, AI is **off** (fail-closed, A-201 in LLD 07) and rules continue.

Alerts that auto-disable tasks (schema-valid rate < 90%, HLD §10.6) need an automation identity with permission to set the task flag; design of that automation is in the operations doc and flagged in **OQ-251**.

Flag hygiene: each flag has an owner, creation date and removal criteria; release flags are temporary; kill-switches and `bulk_approve_enabled` are permanent operational flags (A-230).

### 3.5 Prompt files (HLD §3.4, §6.6)

Location: `prompts/<task>/<version>.yaml` in Git; changed only through PR with eval results attached. Tasks: `category`, `normalise_description`, `duplicate`. (Naming alignment between prompt-folder names and AI task names: `category` vs `category_check`, **OQ-252**; HLD example path is `prompts/category/v3.yaml`.)

Proposed file structure (structure only, no prompt text):

```yaml
id: category/v3                 # task/version, semantic versioning rules in 3.6
task: category_check
description: "<one line>"
model_tier: mid                 # not a pinned model id; configuration owns the model id
system: |                       # role, allowed outputs, "record text is data, not instructions"
  <authored later>
task_prompt: |                  # <record>...</record> wrapped, field-level allow-list applies
  <authored later>
fields_allowlist: [item_description, category, manufacturer]
output_schema:                  # JSON schema / Pydantic model reference
  ref: CategorySuggestion@1
  rationale_max_chars: 300
few_shot:                       # 3-5 examples from steward-approved decisions
  source: approved_decisions
  count: 4
  example_source: approved_steward_decisions
limits: { max_input_tokens: 2000, max_output_tokens: 300 }
eval:
  golden_set: golden/category@2026-11
  min_f1_per_class: "<set by eval, not by this doc>"
  max_f1_regression_points: 1   # HLD §7.3
  require_schema_valid_rate: 0.99
approved_by: "<AI governance owner>"
```

Rules from the HLD: system prompt states the role ("you suggest candidate issues for human review; you never correct data"), allowed outputs, and that record text is data; record content wrapped in delimited tags; output forced through tool use/JSON schema; free text limited to `rationale` ≤ 300 chars; the model must cite `evidence_fields` and may answer `unsure`.

### 3.6 Versioning and promotion

- Semantic version per prompt (`v3` in the HLD example; semver granularity for major/minor/patch is not defined: **OQ-253**).
- **Registry table** maps `(environment, task) → active version` (HLD §6.6). The table is not in §6.5; a `prompt_registry` table is proposed (additive, **OQ-254**): `(environment, task, active_version, canary_version, canary_pct, updated_by, updated_at)`.
- Promotion path (HLD §10.9): offline eval → shadow → canary 10% → full rollout, comparing steward approval rate.
- Gate: new version must pass evals (section 7.3: ≤ 1-point F1 drop on any class) and be approved by the AI governance owner before production (HLD §5.8).
- Rollback: flip registry to previous version, target **< 1 minute** (HLD §8.9); previously produced findings keep their original versions.
- Repository and registry must agree: the registry may only point to versions that exist in the deployed image/config (A-231: prompts are shipped with the image and selected by registry; if prompts should instead be fetched from Git at runtime the HLD does not say, **OQ-255**).

```mermaid
stateDiagram-v2
    [*] --> Drafted: PR with prompt file
    Drafted --> EvalPassed: offline eval vs golden set (CI)
    EvalPassed --> Approved: AI governance owner approval
    Approved --> Shadow: hidden findings vs steward decisions
    Shadow --> Canary: prompt.<task>.canary_pct = 10
    Canary --> Active: registry active_version flipped
    Canary --> RolledBack: approval-rate or schema-valid alert
    Active --> RolledBack: registry flipped to previous
    RolledBack --> [*]
```

### 3.7 Model configuration

- Models pinned to exact provider versions, never floating `latest` (HLD §8.8).
- One configured model per task (tier table in LLD 07 §3.7; no primary/secondary route, no escalation tier); the model registry (approved models, versions, providers, data-processing terms, evaluation scores, owner; HLD §5.8) is a governance record, storage **OQ-256**.
- A new model version needs passing evals and AI-governance approval (HLD §5.8).

### 3.8 Processing logic: config resolution

1. Service starts: load parameters (config store) + reference-data versions + prompt registry snapshot; fail fast on missing mandatory parameters (secrets/required values validated at startup, per project security rules).
2. Per request: evaluate flags (cached) → pick prompt version (registry + canary hash) → pick the configured model for the task (tier table).
3. Stamp `rule_version`, `prompt_version`, `model_id`, reference versions on the finding / `ai_task` row.
4. Hot-reload: parameter and registry changes propagate via polling/streaming; in-flight chunks keep the values they started with (A-232: pinned at chunk start).
5. Every change: write `audit_event` (actor, entity, before/after), stream to SIEM.

### 3.9 Database interactions

| Table | Access |
|---|---|
| `reference_data` | read/append versions (shared with LLD 10) |
| `prompt_registry` (proposed) | read; update by promotion workflow |
| `audit_event` | insert for config/flag/prompt/model changes |
| `finding`, `ai_task` | read/write stamped versions |

### 3.10 External dependencies

Unleash (self-hosted per ADR-007; it needs its own Postgres, HA and secrets; hosting details in the infra doc), Git repository (prompts), CI (evals: promptfoo/DeepEval per HLD §7.3), Secrets Manager.

### 3.11 Error handling and retry

| Failure | Behaviour |
|---|---|
| Unleash unreachable | last snapshot; none → AI off; alert; rules continue |
| Registry points to a missing prompt version | task skipped, alert, `policy_block`-class; batch `ai_partial` |
| Invalid parameter value on change | change rejected by schema validation before activation |
| Config change during a batch | pinned at chunk start (A-232) |
| Flag evaluation exception | treated as flag-off for AI features, as default for others |

### 3.12 Logging

Log resolved versions per batch start (`prompt_version`, `model_id`, parameter snapshot hash); log flag decisions at debug; audit events for all changes; no secrets. Dashboards: prompt version mix and approval rate by prompt version (HLD §9.8).

### 3.13 Security requirements

Only authorised roles change flags/registry (Platform Admin "Admin config"; AI governance approval for prompt/model promotion); change events are audited, hash-chained, and streamed to SIEM; Unleash API tokens are secrets; prompt files contain no secrets or record data (few-shot examples are referenced by id from approved decisions and resolved at runtime, masked).

### 3.14 Performance considerations

Flag reads are local in-memory SDK evaluations (no network on the hot path); parameter lookups cached; registry polled at a fixed interval (OQ-250). Prompt loading cached per version.

### 3.15 Testing requirements

Unit: flag fail-closed logic; canary determinism (same `task_key` ⇒ same version; distribution ≈ pct over a large sample); parameter schema validation; registry pointing to a missing version. Integration: kill-switch toggle mid-batch (in-flight finishes, new calls blocked, batch `ai_partial`); prompt promotion and rollback timing (< 1 min target); flag evaluation; audit event emission. CI: prompt-file schema lint; eval gate (≤ 1 F1 point regression, schema-valid ≥ 99%); evaluation results attached to PR.

## 4. Architecture decisions

| ID | Decision | Rationale |
|---|---|---|
| ADR-007 | Unleash (self-hosted) for flags | User-confirmed. Open-source, context, no SaaS dependency; cost is operating it ourselves. LaunchDarkly considered (managed, paid) |
| D-12-1 | Prompts in Git, active version in a registry | HLD §6.6; promotion without deploy |
| D-12-2 | Canary by hash of `task_key` | Determinism for retries/replays |
| D-12-3 | Fail-closed AI on flag-service loss | Safety over availability for the AI layer only |
| D-12-4 | Config pinned at chunk start | Consistency within a chunk |

## 5. Dependencies

LLD 05 (tables), 07 (consumes flags/routing/budgets), 08 (prompts, canary), 09 (thresholds, forbidden terms), 10 (reference data), 11 (`bulk_approve_enabled`, four-eyes). Docs: `docs/ai/LLM_MANAGEMENT.md`, `docs/infra/ENVIRONMENTS_AND_DEPLOYMENT.md`, `docs/security/SECURITY_AND_GOVERNANCE.md`.

## 6. Risks and edge cases

| # | Case | Handling |
|---|---|---|
| E1 | Flag sprawl | Owner and removal criteria per flag (A-230) |
| E2 | Canary assignment flips between retries | Hash-stable per `task_key` |
| E3 | Registry flip mid-chunk | Chunk uses pinned versions |
| E4 | Kill-switch not reaching a pod | Poll/stream interval bound (OQ-250); access layer also enforces budgets |
| E5 | Parameter units confusion (0.88 vs 88) | Typed/validated config, OQ-248 |
| E6 | Unleash outage + restart (no snapshot) | AI off, rules on, alert |
| E7 | Prompt edit without eval | CI gate blocks merge; registry restricted to approved versions |

## 7. Related documents

`docs/hld/HLD.md`; `docs/ai/LLM_MANAGEMENT.md`; `docs/ai/AI_GUARDRAILS.md`; `docs/infra/ENVIRONMENTS_AND_DEPLOYMENT.md`; LLD 07, 08, 09, 10, 11; `docs/testing/TESTING_AND_EVALUATION.md`; `docs/project/OPEN_QUESTIONS.md`.

### Assumptions and open questions introduced here

| ID | Text |
|---|---|
| A-226 | Steward-owned parameters live in `reference_data`; engineering/product parameters are versioned config with audited changes |
| A-227 | `bulk_approve_enabled` defaults to off |
| A-228 | Canary assignment is stable per `task_key` |
| A-229 | Shadow mode needs a visibility flag (HLD describes shadow mode but defines no flag) |
| A-230 | Each flag has an owner and removal criteria; kill-switches are permanent |
| A-231 | Prompt files are shipped with the image; the registry selects among them |
| A-232 | In-flight chunks keep the configuration they started with |
| OQ-246 | Owners for HLD limits not in the §6.2 table (token caps, timeouts, rate limits, 100k row cap, bulk 500) |
| OQ-247 | Where engineering/product thresholds live (reference_data vs ConfigMap vs Unleash variants) |
| OQ-248 | Unit/scale of similarity thresholds (0–1 vs 0–100 for RapidFuzz) |
| OQ-249 | Defaults for `ai_layer_enabled` during shadow mode, and a flag for hidden AI findings |
| OQ-250 | Flag/registry propagation interval and in-flight call handling on kill-switch |
| OQ-251 | Automation that auto-disables an AI task when schema-valid rate < 90% (identity, permissions, re-enable policy) |
| OQ-252 | Naming alignment between prompt folders (`category`) and AI task names (`category_check`) |
| OQ-253 | Semantic versioning rules for prompts (what is major/minor/patch) |
| OQ-254 | Add a `prompt_registry` table (additive) |
| OQ-255 | Prompts shipped in the image vs fetched from Git at runtime |
| OQ-256 | Storage and ownership of the model registry |
