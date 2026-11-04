# High-Level Design (HLD) — Enterprise Item Data-Quality Assistant (DQA)

| Field | Value |
|---|---|
| Version | 2.0-draft (corrected re-issue of the PDF HLD dated Nov 4, 2026) |
| Status | Draft, awaiting approval (documentation-first gate: no application code until approved) |
| Markers | **PROVISIONAL** = a choice made here only to remove a contradiction; the project owner must confirm (linked `OQ-xx`). `A-xx` = assumption. `ADR-xx` = architecture decision in [ARCHITECTURE_DECISIONS.md](../project/ARCHITECTURE_DECISIONS.md) |
| Technology status | Every technology below is **"proposed in the source HLD, unconfirmed by the project owner"** unless the owner has fixed it: *fixed by owner* = full-system scope, Steward UI in scope (ADR-022), custom thin AI layer (in-process) + Unleash, Celery (SQS in prod, ElasticMQ locally, Redis for cache/rate limits) |

## Purpose

Describe the architecture of DQA at system level so that the LLDs, AI architecture, security, testing, infrastructure and operations documents can be derived from one consistent source. This version fixes contradictions and gaps found in the PDF HLD and aligns it with the brief sample.

## Scope

Covers the seven areas requested: (1) business and functional overview, (2) system architecture, (3) AI/LLM architecture, (4) agent execution architecture, (5) security architecture, (6) infrastructure architecture, (7) operational architecture. Component-level detail lives in the [LLD](../lld/LLD.md). The Steward UI is in scope (ADR-022, designed in LLD module 13) and appears here as an API consumer.

## Detailed explanation

---

## 1. Business and Functional Overview

### 1.1 Business objective
(See [BRD §3.3](../business/BRD.md).) Cut steward time spent finding bad item records by surfacing ranked, explained candidates; raise item-master quality before data reaches procurement, inventory and analytics; use AI help while humans remain the final decision-makers with a full audit trail.

### 1.2 Problem statement
Item records from several source systems (ERP-A, ERP-B, …) are inconsistent, incomplete, duplicated and poorly described. Manual review does not scale; fully automatic correction is unsafe because a wrong merge or recategorisation propagates into purchasing and stock.

### 1.3 Scope

| In scope (v1) | Out of scope (v1) |
|---|---|
| Upload of JSON / CSV item batches | Write-back to source ERPs |
| Deterministic, heuristic and AI-assisted checks | Automatic merge of duplicates |
| Review queue: approve / reject / investigate | Supplier master, BOM, pricing data |
| Audit trail, metrics, export of approved changes as a change file | Real-time streaming ingestion |
| — | (none: Steward UI is in scope, ADR-022; first version = Steward core) |

### 1.4 Target users
Uploader, Data Steward, Data Owner, Auditor, Platform Admin (see [BRD §3.5](../business/BRD.md)); external actors: source-system owner, MDM team, AI governance owner.

### 1.5 Input record model
Based on the brief sample (A-02; required/optional rules and length limits unknown — **OQ-03**):

| Field | Example | Notes |
|---|---|---|
| `item_id` | `"1001"` | Unique only within a `source_system` |
| `item_description` | `"bearing"` | Free text; may contain PII or injection text |
| `manufacturer` | `"SKF"` | |
| `manufacturer_part_number` (MPN) | `""` | Blank/whitespace/`null`/`"N/A"` all count as blank |
| `category` | `"Mechanical"` | Must exist in taxonomy for AI suggestions |
| `unit_of_measure` | `"EA"` | Source HLD calls this "UoM" |
| `source_system` | `"ERP-A"` | |

`record_key` = `<source_system>:<item_id>` (e.g. `ERP-A:1001`). Input also accepts known aliases (`mfr_part_no` → `manufacturer_part_number`; further aliases unknown, OQ-03).

### 1.6 Use cases
UC-01 … UC-10 are defined in [BRD §3.6](../business/BRD.md).

### 1.7 Functional requirements and architectural traceability

| FR | Requirement | Layer | Component | LLD module |
|---|---|---|---|---|
| FR-1 | Ingest JSON/CSV; report malformed/incomplete rows as findings, never crash | Deterministic | Ingestion & Validator | 01 |
| FR-2 | Missing MPN when manufacturer present | Deterministic | Rule Engine | 02 |
| FR-3 | Unsupported or suspicious UoM | Deterministic | Rule Engine | 02 |
| FR-4 | Duplicate `item_id` within a source system | Deterministic | Rule Engine | 02 |
| FR-5 | Weak or vague description | Heuristic | Heuristic Engine | 03 |
| FR-6 | Possible duplicate across systems | Heuristic + AI | Heuristic Engine → Agent Orchestrator (Duplicate Agent) | 03, 08 |
| FR-7 | Category mismatch candidate | Heuristic + AI | Heuristic Engine → Agent Orchestrator (Category Agent) | 03, 08 |
| FR-8 | Normalised description suggestion | AI | Agent Orchestrator (Normalisation Agent) | 08 |
| FR-9 | Every finding carries issue type, severity, confidence, explanation, evidence, suggested action, source | All | DQA API, AI validation & composer | 04, 09 |
| FR-10 | Approve / reject / investigate / bulk; decisions audited | Workflow | Review workflow | 11 |
| FR-11 | Approved suggestions exported as change file; nothing written automatically | Workflow | Export | 11 |

### 1.8 Non-functional requirements

| Area | Target | Verified by |
|---|---|---|
| Latency | Deterministic + heuristic: 10 k records < 30 s. AI: async, 10 k records < 15 min | Performance tests |
| Availability | 99.5 % UI/API; AI layer may degrade without blocking rule results | SLO dashboards |
| Safety | Zero automatic writes; forbidden wording blocked | Invariant tests |
| Explainability | 100 % findings carry explanation + evidence | Contract tests |
| Security | SSO, RBAC, batch-ownership access control, PII masked before any LLM call | Security tests |
| Auditability | Every finding, decision, model and prompt version traceable 7 years | Audit tests |
| Cost | AI cost / 1 k records < USD 0.50 (conflict with batch budget, **OQ-15**) | Cost dashboards |
| Maintainability | New rule without touching the engine; ≥ 85 % coverage on `checks/`, `validation/`, `normalize/` | CI gate |
| Capacity | Batches ≤ 100 k records; findings API p95 < 300 ms | Load tests |

### 1.9 Success metrics
Precision ≥ 85 % (rules) / ≥ 70 % (AI); steward throughput 2× vs baseline (**baseline undefined, OQ-13**); duplicate recall ≥ 80 %; AI schema-valid ≥ 99 %, hallucinated-evidence < 1 %.

### 1.10 Acceptance criteria and golden example
Acceptance criteria are those in [BRD §8.2](../business/BRD.md). The golden example is the brief sample:

**Input** — [`brief-sample-input.json`](../testing/fixtures/brief-sample-input.json): items 1001 (ERP-A, "bearing", SKF, blank MPN, Mechanical, EA) and 1002 (ERP-B, "SKF Bearing 6205 ZZ", MPN `6205-ZZ`, Electrical, EA).

**Expected findings (brief projection)** — [`brief-expected-output.json`](../testing/fixtures/brief-expected-output.json):

| item | issue_type | severity | confidence | explanation |
|---|---|---|---|---|
| 1001 | `missing_part_number` | medium | 0.95 | Manufacturer is present but manufacturer part number is missing. |
| 1002 | `category_mismatch_candidate` | low | 0.70 | Description suggests a mechanical bearing, but category is Electrical. |

**Full finding object (API contract, FR-9)** for item 1002, as produced by this HLD:

```json
{
  "finding_id": "f_8c1…",
  "batch_id": "b_42",
  "record_key": "ERP-B:1002",
  "item_id": "1002",
  "issue_type": "category_mismatch_candidate",
  "severity": "low",
  "confidence": 0.70,
  "explanation": "Description suggests a mechanical bearing, but category is Electrical.",
  "evidence": {"item_description": "SKF Bearing 6205 ZZ", "category": "Electrical"},
  "suggested_action": "Review category assignment before approval.",
  "suggested_value": {"category": "Mechanical"},
  "source": "heuristic",
  "contributing_sources": ["heuristic"],
  "rule_id": "category_mismatch", "rule_version": "1.2.0",
  "model_id": null, "prompt_version": null,
  "status": "needs_review",
  "created_at": "2026-11-04T09:00:00Z"
}
```

The PDF's example showed `source: "ai_suggestion"` with `rule_id` set for this same item (a mix of AI and heuristic metadata); here a heuristic-only finding leaves `model_id`/`prompt_version` null and AI-corroborated findings add `ai_suggestion` to `contributing_sources`. **PROVISIONAL**, OQ-18.

Open question on the golden test: items 1001/1002 would, under the literal source-HLD rules, also trigger `weak_description` (1001 "bearing") and potentially `possible_duplicate` (token-set similarity of "bearing" ⊂ "SKF Bearing 6205 ZZ" scores 100). The brief expects only two findings. **PROVISIONAL** handling in §3.3; owner must decide the acceptance semantics (**OQ-12**).

---

## 2. System Architecture

### 2.1 System context diagram

```mermaid
flowchart LR
    subgraph Users
        UP[Uploader]
        ST[Data Steward]
        DO[Data Owner]
        AU[Auditor]
        AD[Platform Admin]
    end
    subgraph External
        IDP["Corporate IdP<br/>Okta / Entra ID"]
        ERP["Source ERPs<br/>files only in v1"]
        LLM["One LLM provider<br/>Bedrock proposed, behind an adapter"]
        TKT["ServiceNow / Jira"]
        MDM["MDM team<br/>applies change file"]
        SIEM["SIEM Splunk"]
        FLAG["Unleash flags"]
    end
    DQA(("DQA<br/>Data-Quality Assistant"))
    UP -->|upload batch| DQA
    ST -->|review, decide, export| DQA
    DO -->|second approval| DQA
    AU -->|read-only audit| DQA
    AD -->|configuration| DQA
    IDP -->|OIDC/SAML tokens, group claims| DQA
    ERP -.->|extract files supplied by users| UP
    DQA -->|masked minimal fields via in-process LLM adapter only| LLM
    DQA -->|investigate webhook| TKT
    DQA -->|change file| MDM
    DQA -->|security and audit events| SIEM
    FLAG -->|flag evaluation| DQA
```

### 2.2 Component architecture

```mermaid
flowchart TB
    UI["Steward UI<br/>React + TypeScript SPA, ADR-022"] --> GW["API Gateway<br/>OIDC validation, rate limit"]
    GW --> API["DQA API<br/>FastAPI"]
    API -->|enqueue batch_created| Q[("Queue<br/>dqa-ingest / dqa-ai-tasks / dqa-export<br/>+ *-dlq")]
    API --> PG
    API --> S3
    Q -->|ingest| RW["Rule worker<br/>Ingestion and Validator<br/>Rule Engine, Heuristic Engine"]
    RW -->|findings| PG[("PostgreSQL 16 + pgvector<br/>batch, record_snapshot, finding,<br/>decision, ai_task, audit_event,<br/>reference_data, item_embedding")]
    RW -->|ai_task messages uncertain records only| Q
    Q -->|ai tasks| AW["Worker (ai queue)<br/>Task pipeline, plain Python<br/>AI Access Layer, Validator, Composer"]
    AW -->|read refs, write ai_task + AI findings| PG
    AW -->|complete / embed via LLM adapter| LLM["Bedrock (one provider)"]
    RW --> REF["Reference Data Service<br/>taxonomy, UoM, aliases"]
    AW --> REF
    REF --> PG
    S3[("Object storage S3<br/>raw files, change files")]
    Q -->|export| RW
    OBS["Observability<br/>OpenTelemetry, Prometheus, Grafana, Sentry"]
    API -.-> OBS
    RW -.-> OBS
    AW -.-> OBS
```

The PDF's diagram caption says "12 components" while §2.2 lists 14 rows; the list below is authoritative.

### 2.3 Component responsibilities

| Component | Responsibility | Deployable |
|---|---|---|
| Steward UI | Upload, browse/filter findings, decide, bulk actions, export (designed in [LLD 13](../lld/modules/13-steward-ui.md), ADR-022) | `ui` (static assets, hosting OQ-808) |
| API Gateway | SSO token validation, rate limiting | Edge / ingress |
| DQA API (FastAPI) | Batch, finding, decision, export, reference-data endpoints; writes jobs to queue; enforces RBAC + batch ownership on every request | `api` |
| Ingestion & Validator | Parse JSON/CSV (streaming), normalise blanks/nulls, emit `malformed_row` / `incomplete_row`, store immutable raw snapshot | `rule-worker` |
| Rule Engine | Pure deterministic checks, `check(records, ctx) -> list[Finding]`, versioned rule registry | `rule-worker` |
| Heuristic Engine | Weak description, normalised-MPN duplicate blocking, keyword category mismatch, conflicting values, injection scanner | `rule-worker` |
| AI task pipeline | Plain Python pipeline for records needing judgement; triage → task handler → validator → composer → persist (ADR-019) | worker image, `dqa-ai-tasks` consumers |
| AI Access Layer | In-process module, single exit to the one LLM provider: PII masking, allow-lists, retries, token/cost budgets, response checks, logging (ADR-017) | library inside the worker image |
| Reference Data Service | Taxonomy, allowed UoM, generic terms, manufacturer aliases, approved-decision examples; versioned | in `api` + library |
| Finding Store (PostgreSQL) | System of record: batches, snapshots, findings, decisions, audit log | RDS |
| Vector Store (pgvector) | Embeddings of approved items and taxonomy | RDS (same cluster v1) |
| Object Storage (S3) | Raw uploaded files, exported change files | S3 |
| Queue | Decouples upload from rule and AI processing | SQS (prod) / ElasticMQ (local) |
| Observability | Traces, logs, metrics, LLM tracing | OTel + stack |
| Feature flags | Kill-switch and rollout controls evaluated | Unleash |

### 2.4 Technology stack (all unconfirmed by owner unless marked)

| Layer | Choice | ADR | Status |
|---|---|---|---|
| Language | Python 3.12 | ADR-004 | Proposed in HLD |
| API | FastAPI + Pydantic v2 | ADR-004 | Proposed in HLD |
| Workers | **Celery** (broker: SQS prod, ElasticMQ local, Redis for cache/rate-limit) | ADR-005 | **Fixed by owner** (queue stack) |
| Orchestration | Plain Python pipeline, no agent framework | ADR-002 (superseded in part), ADR-019 | **Decided by owner (direction)** |
| Database | PostgreSQL 16 + pgvector | ADR-009, ADR-003 | Proposed in HLD |
| Fuzzy matching | RapidFuzz | ADR-010 (heuristics) | Proposed in HLD |
| LLM | Claude via Amazon Bedrock, one provider, two tiers | ADR-001, ADR-017, ADR-018 | Provider proposed in HLD; single-provider/two-tier simplification decided by owner |
| AI access layer | **Custom thin in-process module** (direct provider SDK behind an adapter) | ADR-006, ADR-017 | **Fixed by owner** |
| Feature flags | **Unleash** | ADR-007 | **Fixed by owner** |
| Observability | OpenTelemetry, Prometheus, Grafana, Sentry (Langfuse dropped) | ADR-015, ADR-021 | Simplified by owner direction |
| Infra | AWS EKS, Terraform, Helm, Argo CD / Rollouts | ADR-008 | Proposed in HLD (A-01, OQ-14) |
| UI | React + TypeScript | — | In HLD stack; out of this documentation round |

The PDF left "Celery or Arq", "SQS / Redis Streams", "LiteLLM or custom" and "LaunchDarkly / Unleash" open; these are now closed by the owner's decisions.

### 2.5 External integrations

| Integration | Purpose | Direction | Failure handling |
|---|---|---|---|
| Corporate IdP | SSO, group claims → roles | Inbound | Reject request (401); JWKS cached with bounded TTL |
| LLM provider (Bedrock proposed; one provider) | Category, normalisation, duplicate adjudication | Outbound via the in-process AI Access Layer only | Retry, then rule-only mode |
| Embedding model (Titan v2, one model) | Vectors for retrieval and duplicate search | Outbound via the AI Access Layer | 3 retries; lexical-only retrieval; AI task degrades |
| Source ERPs | Read-only extracts | File-based (A-03) | n/a |
| ServiceNow / Jira | "Investigate" ticket | Outbound webhook | Retry with backoff; DLQ; finding stays `investigating` with `ticket_pending` flag (A-07) |
| SIEM (Splunk) | Audit + security events | Outbound | Buffer + retry; never blocks request path |
| Unleash | Flags | Inbound polling/streaming | Last-known-good flags; default **AI off** on cold failure (A-08) |

### 2.6 Data flow

```mermaid
flowchart TD
    A["Upload batch file<br/>JSON or CSV, Idempotency-Key"] --> B["Parse and validate<br/>bad rows become findings"]
    B --> C["Deterministic rules<br/>per-rule confidence"]
    C --> D["Heuristic checks<br/>confidence 0.6 to 0.9"]
    D --> E{"Needs AI?"}
    E -- no --> G["Compose explanation<br/>status needs_review"]
    E -- yes --> F["AI agents<br/>masked, minimal fields"]
    F --> V{"Output valid?"}
    V -- no --> X["Drop and log ai_invalid_output<br/>rule findings kept"]
    V -- yes --> G
    G --> R["Review queue<br/>source badge, evidence, confidence"]
    R --> S{"Steward decides"}
    S -- approve --> CH["Change file to MDM<br/>applied by normal process"]
    S -- investigate --> T["Ticket to source owner"]
    S -- reject --> RL["Reason logged<br/>feeds evaluation set"]
```

### 2.7 Request lifecycle (upload to first findings to decision)

```mermaid
sequenceDiagram
    autonumber
    actor Steward
    participant GW as API Gateway
    participant API as DQA API
    participant S3
    participant PG as PostgreSQL
    participant Q as Queue
    participant RW as Rule worker
    participant AW as AI worker
    participant AIG as AI Access Layer (in worker)
    participant LLM
    Steward->>GW: POST /api/v1/batches (file, Idempotency-Key, JWT)
    GW->>API: validated token, rate-limit ok
    API->>API: authZ role, SHA-256 of file
    API->>S3: store raw file
    API->>PG: insert batch (queued), audit_event upload
    API->>Q: batch_created on dqa-ingest
    API-->>Steward: 202 {batch_id, status: queued}
    Q->>RW: chunk of 50 records
    RW->>PG: record_snapshot (immutable), findings (needs_review), batch processing
    Steward->>API: GET /batches/{id}/findings (poll or SSE/webhook, OQ-08)
    RW->>Q: ai_task messages, uncertain records only (dqa-ai-tasks)
    Q->>AW: ai_task (task_key)
    AW->>PG: read refs (read-only), check ai_task cache by task_key
    AW->>AIG: complete() (masked, minimal fields)
    AIG->>LLM: provider call (timeout 30 s, retry)
    LLM-->>AIG: structured output
    AIG-->>AW: checked response + usage
    AW->>AW: validator, composer
    AW->>PG: ai_task result + AI findings (needs_review)
    Steward->>API: POST /findings/{id}/decisions
    API->>PG: decision + audit_event (hash chained)
    Steward->>API: POST /batches/{id}/exports
    API->>Q: export job (dqa-export)
    Q->>RW: build change file
    RW->>S3: change file, signed URL returned to API
```

### 2.8 Deployment architecture

```mermaid
flowchart TB
    subgraph Edge
        CF["CloudFront + WAF"] --> ALB["ALB"]
    end
    subgraph VPC["Private VPC (AWS, A-01)"]
        subgraph EKS["EKS namespace dqa"]
            API2["api"]
            RW2["rule-worker"]
            AW2["ai-worker (same image)"]
            UI2["ui"]
            UNL["unleash"]
        end
        subgraph Data["Private data subnets"]
            RDS[("RDS PostgreSQL 16 Multi-AZ + pgvector")]
            RED[("ElastiCache Redis")]
            SQS[("SQS queues + DLQs")]
            S3B[("S3 versioned, KMS")]
        end
        VPCE["VPC endpoints: Bedrock, S3, SQS, Secrets Manager"]
    end
    ALB --> API2
    API2 --> RDS
    RW2 --> RDS
    AW2 --> RDS
    API2 --> SQS
    RW2 --> SQS
    AW2 --> SQS
    API2 --> S3B
    AW2 --> VPCE --> BR["Bedrock (one provider)"]
    KEDA["KEDA scales workers on queue depth"] -.-> RW2
    KEDA -.-> AW2
```

Namespaces/deployments: `api`, `rule-worker` and `ai-worker` (two Deployments of **one worker image**, consuming different queues; `ai-gateway` is removed because the AI access layer is an in-process module, ADR-017), `ui`, plus `unleash` (added by owner decision ADR-007; the PDF listed no flag service). Detail in §6 and [INFRASTRUCTURE.md](../infra/INFRASTRUCTURE.md).

### 2.9 API architecture

REST over HTTPS, JSON, versioned under `/api/v1`. Long work is asynchronous: upload returns `batch_id`; clients poll or receive SSE/webhook (**OQ-08**). All writes take an `Idempotency-Key` header.

| Method & path | Purpose | Response |
|---|---|---|
| `POST /api/v1/batches` | Upload (multipart) + `Idempotency-Key` | `202 {batch_id, status:"queued"}` for any valid upload, including an empty file (**PROVISIONAL**, OQ-17) |
| `GET /api/v1/batches` | List batches (own for Uploader; all for others) — **added** | `{items, next_cursor}` |
| `GET /api/v1/batches/{id}` | Status and counts | `{status, records, findings_by_type, ai_status}` |
| `GET /api/v1/batches/{id}/findings` | Paginated, filter by type/severity/source/status | `{items:[Finding], next_cursor}` |
| `POST /api/v1/findings/{id}/decisions` | approve / reject / investigate / edit-and-approve | `201 {decision_id, finding_status}` |
| `POST /api/v1/findings/decisions:bulk` | Bulk decision (max 500) | `207` per-item results |
| `POST /api/v1/batches/{id}/exports` | Generate change file | `202 {export_id}` → signed URL |
| `GET /api/v1/reference-data/{type}` | UoM list, taxonomy, generic terms | Versioned list |
| `PUT /api/v1/reference-data/{type}` | Create a new version — **added**, role/approval **PROVISIONAL** (OQ-22) | `201 {version}` |
| `GET /api/v1/audit-events` | Auditor read-only audit view — **added** | `{items, next_cursor}` |

Decision request: `{"action":"approve|reject|investigate","reason_code":"wrong_suggestion","comment":"…","edited_value":{…}}`. The reject reason-code list is undefined (**OQ-06**).

### 2.10 Database architecture

PostgreSQL is the system of record. Raw records are stored once as an immutable snapshot per batch; findings reference them by `(batch_id, record_key)`. Decisions and audit events are append-only. Access control is role- and batch-ownership-based; there is no row-level security because DQA serves a single entity (ADR-016). Table overview (full schema in [05-data-layer](../lld/modules/05-data-layer.md)):

| Table | Purpose | Key constraints |
|---|---|---|
| `batch` | Upload metadata, status, counts | `UNIQUE(file_sha256)` for idempotent re-upload |
| `record_snapshot` | Immutable raw + normalised record | PK `(batch_id, record_key)` |
| `finding` | Detected issue with explanation, evidence, source | `UNIQUE(dedupe_key)` |
| `decision` | Append-only steward decisions | One *active* (latest) per finding; history retained |
| `ai_task` | AI work unit, tokens, cost, latency | `UNIQUE(task_key)` |
| `audit_event` | Hash-chained append-only audit log | `prev_hash`, `hash` |
| `reference_data` | Versioned taxonomy, UoM, thresholds | `(type, version)` |
| `item_embedding` | `vector(1024)` for approved items + taxonomy | HNSW, partition |

---

## 3. AI and LLM Architecture

### 3.1 Principle
AI handles only what rules cannot decide: semantic category fit, description normalisation, fuzzy duplicate adjudication. It runs **after** the rules, sees **only masked minimal fields**, returns **schema-validated JSON**, and its output is always `needs_review`. The AI layer is an untrusted, read-only advisor (ADR-010).

### 3.2 Provider and model selection (ADR-001, updated by ADR-017/018)

| Task | Tier | Example | Why |
|---|---|---|---|
| Category suggestion, duplicate adjudication | Mid | Claude Sonnet via Bedrock | Reasoning over taxonomy + retrieved examples; cost/quality |
| Description normalisation | Small/fast | Claude Haiku | High volume, short structured output |
| Offline evals judge | Mid | same mid-tier model | No top tier (ADR-018) |
| Embeddings | Embedding model | Titan Embeddings v2 (1024 dims) | Cheap, multilingual, inside enterprise boundary |
| Provider outage | — | Rule-only mode; no second provider (ADR-017) | Degraded, not down |

Selection criteria: data residency and zero-retention terms, structured-output support, measured accuracy on the golden set, latency, cost per 1 k records. Models are chosen **by evaluation**, pinned to exact versions (no floating "latest"), and recorded in a model registry. Specific model versions are not decided here (OQ-16).

**Embedding dimension (OQ-21): resolved by ADR-017.** `item_embedding` is `vector(1024)` and there is a single embedding model (Titan v2 proposed), so there is no cross-provider dimension conflict. `embedding_model_id` is still stored per row; a later model change triggers a full re-embed.

### 3.3 Single-agent vs multi-agent (ADR-010)
**Supervisor + specialists implemented as a deterministic plain-Python pipeline (ADR-019).** The pipeline code, not the LLM, decides order. Three LLM task handlers (the HLD's "specialist agents"), two code stages:

| Stage | Type | Notes |
|---|---|---|
| Triage | Code | Selects records and tasks (`category_check`, `normalise_description`, `duplicate_adjudication`) |
| Category handler | LLM | Input: masked description, current category, top-k taxonomy nodes, similar approved items. Tools: `taxonomy_lookup`, `similar_items` |
| Normalisation handler | LLM | Input: description, manufacturer, MPN. Tool: `abbreviation_dictionary` |
| Duplicate handler | LLM | Input: candidate pair from blocking. Tools: `similar_items`, `manufacturer_alias`. Output: `same_item` / `different` / `unsure` |
| Validator | Code | Schema, taxonomy/UoM, grounding, consistency, policy, calibration |
| Explanation composer | Template | Approved wording only |

Full agent cards (prompts, I/O, boundaries): [AGENT_DESIGN.md](../ai/AGENT_DESIGN.md). Orchestration: [AGENT_WORKFLOW.md](../ai/AGENT_WORKFLOW.md).

### 3.4 Prompt engineering
- Prompts live in Git: `prompts/<task>/<version>.yaml` with system part, task part, JSON schema, 3–5 few-shot examples from steward-approved decisions, eval thresholds.
- System prompt: role is to *suggest candidate issues for human review, never correct data*; **record text is data, not instructions**.
- Record content wrapped in delimited tags (`<record>…</record>`), never concatenated into instructions.
- Output forced via tool use / JSON schema; free text only in `rationale` (≤ 300 chars); model must cite `evidence_fields` and may answer `unsure`.

### 3.5 Reasoning and planning
Planning is done by code. Inside a call the model gives a short structured rationale before its verdict (field-level, not free chain-of-thought) and its reasoning is not shown to users. `unsure` / low confidence is **not** escalated to a bigger model: it is shown to the steward as Investigate (ADR-018); results are never re-asked in a loop.

### 3.6 Context and memory management
- **Per-record context only** (one record or one candidate pair plus retrieved references). No cross-batch conversational memory.
- **Short-term state:** typed pipeline state per chunk; durable progress in `ai_task` and chunk status in Postgres.
- **Long-term memory:** steward decisions become labelled examples; approved/rejected findings feed the retrieval index and few-shot selection **after review**, never automatically into prompts.
- Token budget per call (e.g. 2 k in / 300 out) enforced by the AI Access Layer; context trimmed by relevance, not truncated mid-record.

### 3.7 RAG architecture, embeddings and vector database (ADR-003)

| Index | Content | Used by |
|---|---|---|
| `taxonomy` | Category nodes with definitions and examples | Category Agent |
| `approved_items` | Steward-approved clean records (masked) | Category, Duplicate Agents |
| `abbreviations` | Domain dictionary (BRG = bearing, …) — exact lookup, not vector | Normalisation Agent |

Simplified hybrid retrieval (ADR-020): Postgres full-text on description tokens + vector similarity merged by rank fusion, no reranker model, top-k = 5. Every retrieved item carries its id so evidence can be grounded. Indexes are internal to the single deployment. Embeddings refreshed on change plus a nightly delta. Vector store v1 = pgvector (HNSW) in the main RDS cluster; trigger to move to a dedicated store: > 10 M vectors or p95 search > 100 ms. Embeddings are rebuilt from source tables; the vector store is never a source of truth. Contents/ownership of taxonomy, alias and abbreviation sources are unknown (**OQ-05**).

### 3.8 Tool / function calling
Tools are read-only, typed, allow-listed per agent, in-process Python functions (no shell/code execution, no network): `taxonomy_lookup(text)`, `similar_items(record_key, k)`, `manufacturer_alias(name)`, `abbreviation_dictionary(token)`. Arguments validated by Pydantic; max 3 tool calls per agent step; each tool: 2 s timeout, 1 retry; all calls logged with masked args.

### 3.9 Structured output validation (6 steps)
1. **Schema** — Pydantic; unknown fields rejected.
2. **Reference check** — suggested category exists in taxonomy; UoM in allow-list.
3. **Grounding** — `evidence_fields` exist in the record; cited retrieved ids were actually retrieved.
4. **Consistency** — does not contradict a deterministic finding; differs from current value.
5. **Policy** — no forbidden wording, no PII in rationale.
6. **Confidence calibration** — model confidence mapped through a calibration table built from steward outcomes (cold start undefined, **OQ-09**). Findings with calibrated confidence **< 0.5** are shown only under "Investigate" (**PROVISIONAL** boundary, `>= 0.5` is a normal finding; OQ-23).

### 3.10 Model configuration and degradation

| Situation | Action |
|---|---|
| Normal | Use the single configured model for the task (small/fast or mid tier) |
| Provider timeout / 5xx / 429 | Retry with backoff; then rule-only for the chunk (no second provider) |
| Output invalid after 1 repair attempt | Drop AI finding, keep rule findings, log `ai_invalid_output` |
| Low confidence or `unsure` | Shown as Investigate; no escalation model |
| Budget exceeded or AI disabled by flag | Skip AI layer; rule/heuristic findings delivered; batch marked `ai_partial` |
| Provider down | Rule-only mode (degraded, not down) |

### 3.11 Hallucination management
Taxonomy check, grounding check, `unsure` option, calibration, adversarial evaluation set (target false-confident rate < 2 %), category outside taxonomy counts as hallucination (target 0 after validation). See [AI_GUARDRAILS.md](../ai/AI_GUARDRAILS.md).

### 3.12 Rule-versus-AI merge and severity **(PROVISIONAL, OQ-18)**
- Deterministic rules decide severity from a **policy table** by issue type and business impact (full table undefined, **OQ-04**; known: `missing_part_number` medium, `unsupported_uom` high, `duplicate_item_id` high, `weak_description` low/medium, `category_mismatch_candidate` low).
- When rule/heuristic and AI **agree** on the same `(record_key, issue_type)`: keep **one** finding, confidence = max, `source` = the highest-precedence source (`deterministic_rule` > `heuristic` > `ai_suggestion`), and list every contributor in `contributing_sources`.
- When they **disagree**: keep both findings and flag each for review.
- Per-rule confidence is a **constant in the rule registry** (not a global 1.0). **PROVISIONAL:** `missing_part_number` = 0.95 to match the brief; other deterministic rules 1.0 until the owner states otherwise (**OQ-19**).

### 3.13 Heuristic and rule algorithm summary
1. Parse and normalise (non-mutating): frozen `Record`; `is_blank()` treats `None`, `""`, whitespace, `"N/A"`, `"null"` as blank; raw values kept for evidence.
2. Row validation → `malformed_row` / `incomplete_row`.
3. Deterministic rules: `missing_part_number` (manufacturer not blank AND MPN blank); `unsupported_uom` (after case/alias mapping, e.g. `each` → `EA`); `duplicate_item_id` (same `(source_system, item_id)` more than once).
4. Heuristics: `weak_description` (< 3 tokens, or only stop-list generic nouns, or no attribute tokens); `possible_duplicate` (blocking by `normalize_mpn()` + manufacturer alias = exact block 0.9; else description similarity ≥ 0.88 within same manufacturer = 0.7); `category_mismatch_candidate` (keyword → expected-category map disagrees with current category, 0.6–0.7); `conflicting_source_values`; `suspicious_content` (injection scanner).
5. Triage for AI: weak descriptions, keyword-ambiguous categories, duplicate pairs in the uncertain similarity band (0.75–0.88).
6. AI tasks → validation → merge (§3.12).
7. Severity and confidence; queue sorted by severity then confidence.
8. Explanation from per-issue templates filled with evidence.

**PROVISIONAL handling to avoid false results on the brief sample (OQ-12):**
- `possible_duplicate` description-similarity branch uses a similarity measure that is **not subset-insensitive** (e.g. a sort-based ratio rather than token-set ratio) **and** is not applied to records already flagged `weak_description`. Otherwise "bearing" scores 100 against "SKF Bearing 6205 ZZ". Scale of the 0.88 threshold (0–1 vs RapidFuzz 0–100) must be fixed (**OQ-11**).
- Whether `weak_description` also fires for item 1001 is left to the owner: the literal HLD rule says yes, the brief's expected output lists only two findings (OQ-12).

---

## 4. Agent Execution Architecture

### 4.1 Task decomposition
1. **Batch** → split into **chunks** of 50 records (`chunk_size`, configurable).
2. Each chunk runs **stages**: ingest → rules → heuristics → triage → AI tasks → validate → compose → persist.
3. Triage creates **AI tasks** only where needed: `category_check`, `normalise_description`, `duplicate_adjudication` (pairs from blocking).
4. Each AI task is one bounded unit of work with a deterministic `task_key = hash(record_key, task, prompt_version, model_id)` (pair tasks use a sorted pair key).

### 4.2 Workflow execution
`batch_created` job → rule workers process chunks synchronously and publish findings immediately (stewards can review before AI finishes) → `ai_task` messages on `dqa-ai-tasks` consumed by AI workers with a concurrency cap per provider → batch completes when all chunks report `done` or `ai_partial`.

Batch states (canonical): `queued` → `processing` → `done` | `ai_partial` | `empty` | `failed`. The PDF defines no `failed` state; added for non-retryable ingest failure.

### 4.3 Sequential vs parallel execution
- **Sequential per chunk:** stages are a DAG (rules before heuristics before triage).
- **Parallel:** chunks across rule workers; AI tasks across AI workers; independent specialist tasks for different records in a chunk (fan-out per task); bounded by provider concurrency caps and token budgets.

### 4.4 Agent-to-agent communication
Task handlers never message each other. They communicate through the **shared pipeline state** (typed Pydantic object) within a chunk run and through the **queue** between stages — no hidden conversations; every hand-off is inspectable; each handler is replaceable.

### 4.5 Workflow state management

| State | Where | Lifetime |
|---|---|---|
| Batch status, counts | `batch` table | Permanent |
| Chunk / task progress | `ai_task` + chunk status (Postgres), no graph checkpointer | Until batch completes + 30 days |
| AI task status, attempts, tokens, cost | `ai_task` table | Permanent (audit) |
| Findings | `finding` table | Permanent; status changes via decisions |
| Raw records | `record_snapshot` (immutable) + S3 file | Retention policy (e.g. 2 years) — **conflicts with 7-year traceability, OQ-26** |

### 4.6 Retry and timeout strategy

| Operation | Timeout | Retries | Backoff |
|---|---|---|---|
| LLM call | 30 s | 2 (no second provider) | Exponential + jitter 1 s → 8 s |
| Embedding call | 10 s | 3 | Exponential |
| Tool (DB lookup) | 2 s | 1 | Fixed |
| Chunk stage | 5 min | 3 | Re-queued with delay |
| Whole batch | 2 h | — | Marked `ai_partial`, alert raised |

Non-retryable (schema violation after repair, policy block, 4xx) → dead-letter queue with reason code. Error taxonomy: `parse_error`, `provider_error`, `ai_invalid_output`, `policy_block`, `loop_guard_triggered`, `timeout`.

### 4.7 Idempotency and duplicate prevention
- Upload: `Idempotency-Key` header + SHA-256 of content; same file re-uploaded returns existing `batch_id`. Scope: global (single entity).
- Findings: `dedupe_key = sha256(batch_id | record_key | issue_type | rule_id | rule_version)`; for pair findings `record_key` is the lexicographically ordered pair key; `INSERT … ON CONFLICT DO NOTHING` (**OQ-27**).
- AI tasks: `task_key` unique; result cached so retries and replays do not double-bill.
- Decisions: re-submitting the same decision is a no-op; each finding has **one active decision at a time**; history (e.g. `investigate` followed later by `approve`) is retained append-only.

### 4.8 Checkpointing and replay
Progress is recorded per task in `ai_task`. A crashed worker resumes from the last completed task; completed AI calls are not repeated. Replay: re-run a chunk with a new prompt version for evaluation **without touching live findings**.

### 4.9 Loop prevention
- The per-chunk pipeline is acyclic; the only loop is one **repair** attempt on invalid output. There is no escalation to a higher-tier model (ADR-018).
- Hard caps: max 3 tool calls per handler step; max **2 LLM calls per task** (initial + one repair; transport retries are *not* counted) — resolves the PDF's "max 2" vs repair + escalation contradiction by removing escalation (ADR-018, OQ-20 resolved); max token budget per batch.
- Step counter in state aborts with `loop_guard_triggered`.
- Records never re-enter AI triage because of an AI finding; only new uploads or explicit re-runs trigger analysis.

### 4.10 Human-in-the-loop and approval workflow
Humans are the only actors that change a finding's outcome. Stewards approve, reject (reason code), investigate (ticket), or edit the suggested value before approving. Low-confidence AI findings are shown in a separate "Needs investigation" tab, never mixed with high-confidence rules.

```mermaid
stateDiagram-v2
    [*] --> needs_review: finding created (rule, heuristic or AI)
    needs_review --> withdrawn: system only (rule or prompt rolled back)
    needs_review --> approved: steward approves
    needs_review --> rejected: steward rejects (reason code)
    needs_review --> investigating: steward investigates (ticket)
    investigating --> needs_review: ticket resolved
    approved --> in_change_file: export job
    rejected --> closed: reason feeds evaluation
    in_change_file --> closed: applied by MDM (outside DQA)
```

- The system may only **create** or **withdraw** a finding; every other transition is a Steward or Data Owner action.
- **Four-eyes rule:** duplicate merges and category changes affecting more than *N* items need a second approver (Data Owner). Default `four_eyes_threshold_items = 10`. What "affecting N items" means for a single finding and who is the second approver when the Data Owner is the first are undefined (**OQ-10**).
- Approved findings become lines in a **change file** (CSV/JSON; layout undefined, **OQ-07**) applied by the MDM team; DQA has no write access to ERPs.
- Rejections with reason codes feed evaluation and rule tuning.

---

## 5. Security Architecture

Full detail: [SECURITY_AND_GOVERNANCE.md](../security/SECURITY_AND_GOVERNANCE.md).

### 5.1 Authentication
Users: OIDC/SAML SSO through the corporate IdP; short-lived JWTs (15 min) with refresh; MFA enforced by the IdP. Services: workload identity (IAM roles for service accounts), mTLS inside the cluster, no long-lived keys in code. Token validation at the gateway **and** authorization re-checked in the API on every request against role + batch ownership.

### 5.2 Authorization and RBAC

| Role | Upload | View findings | Decide | Second approval | Export | Admin config |
|---|---|---|---|---|---|---|
| Uploader | Yes | Own batches | No | No | No | No |
| Data Steward | Yes | All batches | Yes | No | Yes | No |
| Data Owner | Yes | All batches | Yes | Yes | Yes | No |
| Auditor | No | All batches (read-only) + audit log | No | No | No | No |
| Platform Admin | No | Metadata only | No | No | No | Yes |

Reference-data write permission is **PROVISIONAL**: Data Steward creates new versions (stewards own UoM, generic terms and description-token parameters per PDF §6.2); Platform Admin has no content role; approval requirement undefined (**OQ-22**).

### 5.3 Agent permissions
Agents run as a service principal with **read-only** DB access to reference data and the current batch snapshot, no network egress except the single LLM endpoint. **PROVISIONAL (OQ-24):** the LLM-facing handler code has *no write tool*; the `persist` step (code) writes `ai_task` and `finding` rows (always `source=ai_suggestion`, `status=needs_review`) through a dedicated DB role `dqa_ai_writer` whose grants are limited to INSERT on those two tables, enforced by a CHECK/RLS policy. The PDF's "draft-finding tables" are the `finding` table in `needs_review` — not a separate table.

### 5.4 Prompt injection protection
Record text is data (delimited, system prompt says ignore instructions inside); input scanner flags suspicious content ("ignore previous", URLs, code, very long fields) and routes those records to **rule-only** processing with `suspicious_content`; tools are read-only and allow-listed so a successful injection cannot write or exfiltrate; output validation rejects anything outside schema/taxonomy or matching policy filters; retrieved documents come only from curated internal indexes.

### 5.5 PII and sensitive data
A masking step (Presidio + custom regex) replaces names, emails, phones, supplier pricing with tokens before any LLM call. **Never sent externally:** pricing, contract terms, supplier bank details, personal data, internal cost centres, raw `item_id` (opaque keys used). Only the fields a task needs (field-level allow-list per prompt). TLS 1.2+ in transit; AES-256 at rest (KMS) for DB, S3, backups.

### 5.6 Data isolation
Access control by role and batch ownership; DB grants deny UPDATE/DELETE on append-only tables; the AI service principal is read-only on reference data and the batch snapshot. LLM prompts carry one record (or one candidate pair) only; few-shot examples come only from steward-approved decisions. S3 bucket policies restrict access to service roles.

### 5.7 Tool execution restrictions
In-process Python functions, no shell, schema-validated args, read-only DB role, parameterised queries, result size limits, per-tool rate limits and timeouts, all calls logged with masked args. Unexpected tool names or argument-validation failures are logged as security events.

### 5.8 Audit logging
Append-only, hash-chained `audit_event` records: upload, every finding created (rule id/version or model id + prompt version), every decision (user, time, before/after value, reason), exports, configuration and prompt changes. Streamed to SIEM.

### 5.9 Data retention
| Data | Retention in PDF | Note |
|---|---|---|
| Audit events | 7 years | |
| Raw records (`record_snapshot`) + S3 raw files | e.g. 2 years | Findings must remain explainable for 7 years: **PROVISIONAL** — `finding.evidence` stores the cited raw values and `audit_event.payload` stores before/after values, so explanations survive snapshot purge (**OQ-26**). Right-to-erasure handling undefined (GDPR / DPDP referenced in §5.8) |
| Checkpoints | Batch completion + 30 days | |
| Masked LLM prompt/response bodies | 30 days (10 % sampled in prod, 100 % staging) | |
| Logs | 30 days hot, 1 year archive | |

### 5.10 Model governance
Model registry (approved models, versions, providers, data-processing terms, eval scores, owner); a new model or prompt version needs passing evals and AI governance owner approval; vendor DPAs with zero data retention; regional processing for data-residency; periodic precision/rejection review; kill-switch flag `ai_layer_enabled`; documentation (HLD, model cards, risk assessment) for audit and EU-AI-Act-style transparency.

---

## 6. Infrastructure Architecture

Detail: [INFRASTRUCTURE.md](../infra/INFRASTRUCTURE.md), [ENVIRONMENTS_AND_DEPLOYMENT.md](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md).

| Concern | Design |
|---|---|
| Cloud | AWS private VPC on EKS; Terraform; GitOps (A-01, OQ-14) |
| Application services | EKS namespace `dqa`: `api`, `rule-worker`, `ai-worker` (same image, different queues), `ui`, `unleash`; HPA/KEDA |
| Database | RDS PostgreSQL 16 Multi-AZ + pgvector; Alembic migrations, forward-only, expand → migrate → contract |
| Queues and workers | Celery workers. Queues `dqa-ingest` (rule-worker, KEDA 2–20 pods), `dqa-ai-tasks` (ai-worker, KEDA capped by provider tokens/min), `dqa-export` (rule-worker, 1–3 pods), `*-dlq` (ops alert + replay tool). SQS in prod; **ElasticMQ** locally; ElastiCache Redis for cache / rate limits. Visibility timeout > max task time; messages carry `task_key` |
| LLM connectivity | One in-process AI Access Layer (`complete()`, `embed()`); handlers never import provider SDKs; VPC endpoint to the single provider |
| Vector DB | pgvector with HNSW, partitioning; move to OpenSearch k-NN or Qdrant above 10 M vectors or p95 > 100 ms |
| Secrets | AWS Secrets Manager + External Secrets Operator; rotation: DB credentials 30 days, provider keys 90 days; no secrets in Git/images/logs; gitleaks in CI |
| Network security | CloudFront + WAF + ALB; private subnets only for data; VPC endpoints (Bedrock, S3, SQS, Secrets Manager); mTLS in cluster where used; worker pods have egress only to the single LLM endpoint |
| Scalability | KEDA on queue depth; provider rate limits cap AI throughput; `finding` partition by month beyond ~500 M rows; review-queue pagination tuned to ~1 M open findings |
| Disaster recovery | RDS PITR 35 days, daily cross-region snapshot copy; S3 versioning + CRR; infra reproducible from Terraform in DR region; **RPO 15 min, RTO 4 h**; DR drill twice a year; both LLM providers down ⇒ rule-only mode |
| Rollback | Argo Rollouts abort on SLO breach (< 5 min); prompt/model flip in registry (< 1 min); `ai_layer_enabled=false` (immediate); expand/contract migrations; bulk-retract findings by `prompt_version`/`rule_version` (status `withdrawn`, audited) |

---

## 7. Operational Architecture

Detail: [OBSERVABILITY_AND_OPERATIONS.md](../operations/OBSERVABILITY_AND_OPERATIONS.md).

| Topic | Design |
|---|---|
| Logging | Structured JSON (structlog): `trace_id`, `batch_id`, `record_key`, `component`, `level`; no raw record text or PII; Fluent Bit → CloudWatch/OpenSearch; 30 days hot, 1 year archive |
| Distributed tracing | One `trace_id` from upload through every rule, agent step, tool call and LLM request to the steward's decision (OpenTelemetry) |
| Agent execution monitoring | Span per pipeline step (`triage`, `category_task`, `validator`, …) with `task_key`, attempt, outcome (accepted/downgraded/dropped), drop reason |
| LLM monitoring | Per call: provider, model id, prompt version, temperature, tokens in/out, latency, finish reason, retries, validation result, cache hit; stored in `ai_task` plus OTel/Prometheus (no Langfuse, ADR-021); masked sampled prompt/response bodies in the restricted store for inspection and replay |
| Token usage | Recorded per call in `ai_task`; aggregated per task type, batch, model and prompt version; budgets enforced in the AI Access Layer per batch and per day |
| Cost monitoring | Tokens × versioned price table; dashboards/batch/task/prompt; monthly showback; key unit metrics: cost per 1 k records and per **approved** finding |
| Alerting | PagerDuty (P1/P2) and Slack (P3). Thresholds: API 5xx > 1 % (warn) / > 5 % (critical); findings API p95 > 500 ms / > 2 s; ingest queue age > 5 min / > 20 min; DLQ > 10 / > 100 per hour; AI schema-valid rate < 97 % / < 90 % (auto-disable AI task); AI approval rate drop > 10 / > 20 pts (7-day); daily AI cost > 80 % / > 100 % budget (access layer blocks); provider errors > 5 % / > 20 %; loop-guard/policy blocks any / > 10 per hour; unauthorised resource access attempt: any (security event) |
| Incident management | SEV1 (data exposure to unauthorised users, unmasked PII to LLM): page immediately, kill-switch AI, 15 min ack. SEV2 (pipeline down, wrong findings at scale): 30 min ack, rollback/disable task. SEV3: ticket, next business day. Blameless post-mortem for SEV1/2 within 5 business days |
| Post-live verification | Confirm version, migrations and flag values; run smoke suite with a synthetic test data set (golden two-record file → exactly the known findings within 2 minutes; empty and malformed file → graceful; approve → export → change file contains it and audit shows decision; one AI call through each provider); check dashboards at baseline; verify audit + SIEM forwarding; toggle `ai_layer_enabled` off/on; sign-off by on-call engineer and product owner |
| Post-live monitoring | 72 h heightened watch after each release (dashboards twice a day); AI quality: approval rate by source/issue type/prompt version, rejection reason mix, schema-valid/drop/`unsure`/repair rates, weekly sampled human audit of 50 accepted AI findings, monthly golden-set re-run |
| Go-live | Staged: 2 weeks **shadow mode** (AI findings hidden, compared with steward decisions) → pilot group → GA. Shadow mode needs a flag not present in the PDF list: **PROVISIONAL** `ai_shadow_mode` (OQ-28) |

---

## Assumptions introduced by this HLD

A-01…A-06 are in [BRD §7](../business/BRD.md). Additional:

| ID | Assumption | Status |
|---|---|---|
| A-07 | If the ticketing webhook fails, the finding stays `investigating` with a pending-ticket marker and the webhook is retried then dead-lettered; the PDF specifies no failure behaviour | Unconfirmed |
| A-08 | If Unleash is unreachable on cold start, `ai_layer_enabled` defaults to **off** (fail-safe: rules still run); last-known-good flags are used otherwise | Unconfirmed |

## Architecture decisions

| ADR | Topic | Status |
|---|---|---|
| ADR-001 | LLM provider and model tiers | Proposed |
| ADR-002 | Orchestration framework (LangGraph proposed; superseded in part by ADR-019) | Updated |
| ADR-003 | Vector database (pgvector) | Proposed |
| ADR-004 | Application framework (FastAPI) | Proposed |
| ADR-005 | Queue and workers (Celery; SQS / ElasticMQ / Redis) | Owner-directed |
| ADR-006 | AI gateway (custom thin layer; in-process per ADR-017) | Owner-directed |
| ADR-007 | Feature flags (Unleash) | Owner-directed |
| ADR-008 | Infrastructure (AWS EKS, Terraform) | Proposed |
| ADR-009 | Database (PostgreSQL 16) | Proposed |
| ADR-010 | Single vs multi-agent (supervisor + specialists; pipeline + handlers per ADR-019) | Updated |

## Dependencies

[BRD](../business/BRD.md) · [LLD](../lld/LLD.md) · [AI architecture](../ai/AI_ARCHITECTURE.md) · [Security](../security/SECURITY_AND_GOVERNANCE.md) · [Testing](../testing/TESTING_AND_EVALUATION.md) · [Infrastructure](../infra/INFRASTRUCTURE.md) · [Operations](../operations/OBSERVABILITY_AND_OPERATIONS.md). External: corporate IdP, LLM providers, ServiceNow/Jira, SIEM, Unleash, MDM process.

## Risks and edge cases

| Risk / edge case | Handling |
|---|---|
| Empty file | Valid upload → `202`; batch status `empty`; zero findings (PROVISIONAL) |
| Not JSON / bad CSV encoding | `422` with line/position; partial rows still processed where possible |
| Missing required field / null / whitespace | `incomplete_row` finding; record still checked for other issues |
| Duplicate `item_id` in same system | `duplicate_item_id` (high) |
| Same item in different systems | `possible_duplicate`, never auto-merged |
| MPN formats `6205-ZZ`, `6205 ZZ`, `6205ZZ` | Normalised for matching only; raw values shown as evidence |
| Very short description ("valve") | `weak_description` + AI normalisation suggestion |
| Attributes in description, wrong category | `category_mismatch_candidate` with keyword evidence |
| Unsupported UoM (`EACH`, `ea.`, `pcs`) | Alias map first; unknown → `unsupported_uom` |
| Conflicting values across systems | `conflicting_source_values` listing each system's value |
| Non-English / abbreviation-heavy text | Abbreviation dictionary + multilingual model; low confidence → Investigate |
| Prompt-injection text in description | Rule-only processing, `suspicious_content` flag |
| File > 100 k rows | Rejected with guidance to split; streaming parser below the limit |
| Provider outage | Failover; both down ⇒ rule-only; batch `ai_partial` |
| Steward over-trust in AI | Source badges, no default approve-all for AI, sampled QA, four-eyes |
| Cost growth | Triage sends only uncertain records (< 30 % target), `task_key` caching, budgets, small models for volume. **Batch budget USD 25 (6.2) vs target USD 0.50 / 1 k × 100 k records = USD 50 — contradiction (OQ-15)** |
| Known limitations | No ERP write-back; pairwise duplicate detection only (no global entity resolution); categories limited to existing taxonomy; non-English coverage limited initially |

Full register: [RISKS_AND_DEPENDENCIES.md](../project/RISKS_AND_DEPENDENCIES.md).

## Related documents

- [BRD](../business/BRD.md), [LLD](../lld/LLD.md), [AI_ARCHITECTURE](../ai/AI_ARCHITECTURE.md), [AGENT_DESIGN](../ai/AGENT_DESIGN.md), [AGENT_WORKFLOW](../ai/AGENT_WORKFLOW.md), [LLM_MANAGEMENT](../ai/LLM_MANAGEMENT.md), [AI_GUARDRAILS](../ai/AI_GUARDRAILS.md)
- [SECURITY_AND_GOVERNANCE](../security/SECURITY_AND_GOVERNANCE.md), [TESTING_AND_EVALUATION](../testing/TESTING_AND_EVALUATION.md)
- [INFRASTRUCTURE](../infra/INFRASTRUCTURE.md), [ENVIRONMENTS_AND_DEPLOYMENT](../infra/ENVIRONMENTS_AND_DEPLOYMENT.md), [OBSERVABILITY_AND_OPERATIONS](../operations/OBSERVABILITY_AND_OPERATIONS.md)
- [ARCHITECTURE_DECISIONS](../project/ARCHITECTURE_DECISIONS.md), [OPEN_QUESTIONS](../project/OPEN_QUESTIONS.md), [RISKS_AND_DEPENDENCIES](../project/RISKS_AND_DEPENDENCIES.md), [IMPLEMENTATION_PLAN](../project/IMPLEMENTATION_PLAN.md)
