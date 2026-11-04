# Architecture Decision Records — Data-Quality Assistant (DQA)

## Purpose

Record every major architectural decision for DQA in one place, with the context, the options weighed, the choice, and the consequences, so that no decision is implicit and any later change goes through a documented ADR before implementation (see root `CLAUDE.md`).

## Scope

Twenty-three decisions: ADR-001 to ADR-010 are referenced from every other document; ADR-011 to ADR-015 are new decisions this review found necessary; ADR-016 (single entity), ADR-017 to ADR-021 (simplified AI layer) ADR-022 (Steward UI in scope) and ADR-023 (open access, no authentication) were directed by the user. Product-level decisions (what the system does) live in the [BRD](../business/BRD.md) and [HLD](../hld/HLD.md); this file covers *how* it is built and *why that way*.

## Detailed explanation

### How to read this file

- **Status values**
  - **Decided by user** — the user stated or approved the choice (full-system scope, Steward UI in scope (ADR-022), custom thin AI gateway (in-process per ADR-017), Unleash, Celery with SQS in production / ElasticMQ locally / Redis for cache, and the approved plan as a whole).
  - **Proposed — pending user confirmation** — inherited from the source HLD PDF or introduced by the architect; not yet confirmed by the user. Treat as the working baseline, not as final (BRD A-01, OQ-16).
- Technologies are judged against this system's requirements (HLD §1.5 NFRs: 10k records < 30 s rule pass, AI async < 15 min, zero automatic writes, 7-year audit, role/batch-ownership access control, kill-switchable AI), **not** on popularity.
- "Reversibility" is stated per decision because it drives how hard it is to change later.
- Open questions are referenced as `OQ-xx`; they are defined in their owning documents and consolidated in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

### Decision index

| ID | Title | Status |
|---|---|---|
| ADR-001 | LLM provider and model tiers | Proposed — pending user confirmation; **updated by ADR-017/018** (one provider, two tiers) |
| ADR-002 | Agent orchestration framework | **Superseded in part by ADR-019** (plain Python pipeline instead of LangGraph) |
| ADR-003 | Vector store | Proposed — pending user confirmation; retrieval simplified by ADR-020 |
| ADR-004 | Application framework | Proposed — pending user confirmation |
| ADR-005 | Queue and worker stack | Decided by user (Celery; SQS prod; ElasticMQ local; Redis cache) |
| ADR-006 | AI Gateway implementation | Decided by user (custom thin gateway); **realised in-process by ADR-017** |
| ADR-007 | Feature-flag service | Decided by user (Unleash) |
| ADR-008 | Cloud and runtime platform | Proposed — pending user confirmation |
| ADR-009 | System-of-record database | Proposed — pending user confirmation |
| ADR-010 | Agent architecture pattern | Proposed — pending user confirmation; **updated by ADR-019** (pipeline + task handlers) |
| ADR-011 | Immutable snapshots and hash-chained audit | Proposed — pending user confirmation |
| ADR-012 | Finding source and rule/AI merge model | Proposed — PROVISIONAL, pending user confirmation |
| ADR-013 | Batch-scope pass for cross-record checks | Proposed — PROVISIONAL, pending user confirmation |
| ADR-014 | PII masking approach | Proposed — pending user confirmation |
| ADR-015 | Observability stack | Proposed — pending user confirmation; **updated by ADR-021** (no Langfuse) |
| ADR-016 | Single-entity deployment, no multi-tenancy | Decided by user |
| ADR-017 | In-process AI access layer, single provider | Decided by user — direction; specifics PROVISIONAL, pending confirmation |
| ADR-018 | Two model tiers, 2-call cap, no escalation | Decided by user — direction; specifics PROVISIONAL, pending confirmation |
| ADR-019 | Plain Python pipeline replaces LangGraph | Decided by user — direction; specifics PROVISIONAL, pending confirmation |
| ADR-020 | Simplified RAG on existing Postgres | Decided by user — direction; specifics PROVISIONAL, pending confirmation |
| ADR-021 | Cost controls and simplified observability | Decided by user — direction; specifics PROVISIONAL, pending confirmation |

Scope decisions made by the user and not requiring an ADR of their own: full-system scope; Steward UI in scope (ADR-022); approval gate passed 2026-11-04.

---

## ADR-001 — LLM provider and model tiers

**Status:** Proposed — pending user confirmation (HLD §2.3, §3.1; BRD A-01, OQ-16)

> **Update (ADR-017, ADR-018):** Superseded in part: **one provider** (Bedrock as proposed, behind an adapter; OQ-700, OQ-207), **two model tiers** (small/fast and mid), no Azure OpenAI secondary, no top-tier escalation model. Option 4 (single provider, no fallback) is selected; degradation is rule-only mode. The embedding dimension conflict (OQ-21/OQ-208) is resolved. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** The AI layer suggests categories, normalises descriptions and adjudicates duplicate pairs on masked, minimal fields. The enterprise stipulates zero data retention where possible, regional hosting, structured-output support, and the system must work without the LLM (NFR Availability, rule-only mode).

**Problem.** Which provider(s) and which model *tiers* serve the three AI tasks, with a fallback that does not make quality or compliance worse.

**Options considered**
1. **Claude on Amazon Bedrock (primary) + Azure OpenAI (secondary)** — the HLD proposal.
2. Direct vendor APIs (Anthropic / OpenAI) over the public internet.
3. Self-hosted open-weight models on a private GPU endpoint.
4. Single provider only, no fallback.

**Selected approach.** Option 1, with models chosen **per task by tier**, not by name: mid-tier for category suggestion and duplicate adjudication, small/fast for description normalisation, top-tier only for escalations and offline evaluation. Exact model IDs and versions are **not fixed here** (OQ-301, OQ-207); the HLD requires pinning to exact provider versions, never a floating "latest" (HLD §8.8). Option 3 is kept as a contingency for the high-volume normalisation task (HLD §11.3).

**Justification.** Bedrock fits the AWS target (ADR-008): VPC endpoints keep traffic off the public internet, IAM roles replace long-lived keys, and enterprise data terms are available. A second provider behind the gateway (ADR-006) removes single-vendor outage risk (HLD §3.10, §10.6 failover alerts). Tiering controls cost: triage sends only uncertain records to AI (target < 30 %), the NFR cost target is below USD 0.50 per 1k records.

**Advantages**
- Private connectivity, IAM-based auth, regional data residency options.
- Two independent providers; provider swap is a gateway config change.
- Tier choice is revisitable by evaluation without a redesign.

**Disadvantages**
- Two vendor contracts, DPAs and zero-retention confirmations to maintain.
- Prompts must stay provider-neutral, which limits use of provider-specific features.
- Embedding models differ per provider (1024 vs 1536 dimensions): see OQ-21 / OQ-208.

**Risks**
- Silent quality drift after a provider model update (mitigation: pinned versions, monthly golden-set re-run, approval-rate alerts).
- Fallback model has lower accuracy on the golden set (must be evaluated, not assumed).
- Zero-retention and residency terms unconfirmed (OQ-207, OQ-411).

**Consequences.** A model registry (version, provider, terms, eval scores, owner) is mandatory (SEC doc, ADR-006). A model or prompt change requires passing evals and AI-governance approval. A mixed-provider embedding strategy must be decided before RAG is built (OQ-208).

**Reversibility:** high at the gateway (config), medium for embeddings (re-index).

---

## ADR-002 — Agent orchestration framework

**Status:** Superseded in part by ADR-019 (HLD §2.3, §3.9)

> **Update (ADR-019):** LangGraph is **not** used. The flow is fixed and code-driven, so a plain Python pipeline with progress recorded in Postgres gives the same determinism, resume and replay without an agent framework dependency. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** The AI workflow is a fixed pipeline with two bounded back-edges (one repair, one escalation), per-chunk checkpoints, crash resume, replay with a new prompt version, and a human-in-the-loop end state. Behaviour must be deterministic and testable.

**Problem.** What runs and persists the AI workflow state?

**Options considered**
1. **LangGraph** state graph with a Postgres checkpointer (HLD).
2. **Hand-rolled state machine** in the worker (explicit states in Postgres).
3. **Temporal** or **AWS Step Functions** as an external durable-workflow engine.
4. **LangChain / autonomous agent loops** where the model picks the next step.

**Selected approach.** Option 1, constrained: the graph is fixed and written in code; the LLM never chooses the next node; checkpoint after every node; Postgres checkpointer (same cluster, ADR-009). The graph is hidden behind a small internal interface so the workflow definition is not coupled to framework internals.

**Justification.** The requirements (checkpoint per node, replay, bounded loops, typed shared state, interrupts) match LangGraph's model and keep the number of moving parts low: no extra service to run, unlike Temporal or Step Functions. A hand-rolled machine (Option 2) is a credible alternative for a graph this small; it is not selected only because checkpointing, replay and tracing would have to be built and tested by us. Option 4 is rejected: it contradicts the "model never chooses its next step" safety property (HLD §3.2).

**Advantages**
- Native checkpoint/replay, typed state, explicit edges, human-interrupt support.
- No separate workflow cluster.

**Disadvantages**
- Dependency on a fast-moving framework and its Postgres checkpoint schema.
- Checkpoint table growth (retained batch + 30 days, HLD §4.4).
- Team learning cost.

**Risks**
- Upstream breaking changes (mitigation: pin version, wrapper interface, characterisation tests).
- Checkpoint serialisation of large states (50-record chunks keeps state small).
- If the framework proves limiting, migration to Option 2 touches only the orchestrator module (LLD 08).

**Consequences.** Version pinning and an upgrade policy are required (ENVIRONMENTS doc). Replay for evaluation is a first-class capability and writes to a separate store, never to live findings (OQ-211).

**Reversibility:** medium (orchestrator module is isolated; state schema is ours).

---

## ADR-003 — Vector store

**Status:** Proposed — pending user confirmation (HLD §2.5, §8.4)

> **Update (ADR-020):** pgvector in the existing Postgres is kept (no new infra). Retrieval is simplified: Postgres full-text + vector similarity with rank fusion, no reranker model, one embedding model, embeddings only for taxonomy nodes and approved items. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** Vectors support taxonomy lookup, similar approved items and duplicate search. v1 volume is bounded (HLD: move trigger at > 10M vectors or p95 search > 100 ms); embeddings are rebuildable from source tables, so the store is never the source of truth.

**Problem.** Where do embeddings live in v1, and what makes us move?

**Options considered**
1. **pgvector in the main Postgres cluster** with HNSW (single index; one entity, no partitioning).
2. Amazon OpenSearch k-NN (also gives native BM25 for hybrid retrieval).
3. Qdrant (dedicated vector database).

**Selected approach.** Option 1 for v1, with documented triggers to move to Option 2 or 3 and a read replica for retrieval to avoid contention with OLTP (HLD §11.1).

**Justification.** One datastore keeps access control, transactions, backups and DR uniform; volumes in v1 do not need a dedicated engine; rebuildability lowers migration cost. Hybrid retrieval needs BM25: Postgres full-text search is *proposed* as the lexical part (OQ-227), which avoids a second engine now.

**Advantages**
- One system to secure, back up and operate; DB grants cover vectors.
- Embeddings and relational data can be joined in SQL.

**Disadvantages**
- Index builds and ANN queries compete with transactional load.
- Postgres FTS is weaker than a dedicated BM25 engine; reranking is extra work (OQ-228).
- One embedding dimension per column (OQ-21).

**Risks**
- Retrieval latency or recall degrades at scale; performance tests at 100k records and the > 10M vector trigger exist to detect this.

**Consequences.** Retrieval sits behind an interface so a store swap does not touch agents (LLD 10). Re-indexing from source is a supported, tested operation (nightly and on reference-data change).

**Reversibility:** high (rebuild from source).

---

## ADR-004 — Application framework

**Status:** Proposed — pending user confirmation (HLD §2.3)

**Context.** The API handles uploads, finding queries, decisions, bulk decisions and exports. It shares typed contracts with LLM output validation. Long-running work is asynchronous.

**Problem.** Which Python framework backs the API and the shared contract layer?

**Options considered**
1. **FastAPI + Pydantic v2** (HLD).
2. Django + Django REST Framework.
3. Non-Python stack (e.g. Java/Spring, Go).

**Selected approach.** Option 1.

**Justification.** The same Pydantic models validate API payloads, queue messages and LLM structured output, which removes a class of contract-drift defects; OpenAPI is generated from the types; async I/O suits upload streaming and the gateway client. Python is also the language of the data-quality tooling (RapidFuzz, Presidio) and LLM SDKs. Django's batteries (admin, ORM, auth) bring less value because identity is external (OIDC), the data layer needs fine-grained control (grants, `ON CONFLICT`, JSONB, hash chain), and an admin UI is out of scope. A non-Python stack would give up the shared-model benefit for no stated requirement.

**Advantages:** typed contracts end to end; low framework overhead; clear OpenAPI.

**Disadvantages:** no built-in migrations/admin/auth (we choose and own them: Alembic, OIDC middleware); async misuse can block the loop; DB access layer must be chosen deliberately.

**Risks:** inconsistent patterns across services without conventions (mitigation: LLD 00 conventions, mypy strict, ruff); sync CPU-bound work in async handlers (mitigation: rule/heuristic work runs in workers, not in request handlers).

**Consequences.** Python 3.12 baseline; shared `contracts` package (no code written in this phase) used by API, workers and gateway.

**Reversibility:** low (shared models and tests depend on it).

---

## ADR-005 — Queue and worker stack

**Status:** Decided by user. The user asked for a suggestion for the *local* queue; the architect proposed Celery everywhere with SQS in production and ElasticMQ locally, and the user approved the plan containing it. The local broker remains overturnable.

**Context.** Work is decoupled between upload, rule/heuristic workers, AI workers and export. HLD §2.2 says "SQS / Redis Streams", §2.3 "Celery or Arq on Redis / SQS"; HLD §8.5 specifies SQS queues, DLQs and KEDA scaling.

**Problem.** One task framework and one broker strategy that behaves the same in dev and prod, including retries, visibility timeouts and dead letters.

**Options considered**
1. **Celery with SQS (prod) and ElasticMQ (local), Redis for cache and rate limiting.**
2. Arq on Redis Streams everywhere.
3. Celery with Redis as broker in all environments.
4. Native SQS consumers (no task framework).
5. Kafka / RabbitMQ.

**Selected approach.** Option 1 (user-approved).

**Justification.** SQS gives managed durability, DLQs with redrive and KEDA queue-depth scaling (HLD §8.5) without running a broker. ElasticMQ speaks the SQS API, so dev exercises the same visibility-timeout, redrive and DLQ behaviour as production; Redis-as-broker locally (Option 3) would hide those differences until staging. Arq is lighter, but DLQ, replay tooling and KEDA integration would be ours to build; Kafka/RabbitMQ add operations burden for no stated throughput need.

**Advantages:** one API across environments; managed prod broker; established retry/ETA semantics.

**Disadvantages (recorded trade-offs, LLD 06)**
- Celery's SQS transport has no results backend, delay ≤ 900 s, weaker monitoring/introspection than Redis; at-least-once delivery means every handler must be idempotent.
- ElasticMQ is not identical to SQS in every detail (FIFO, long polling, throttling); must be covered by staging smoke tests (A-522).

**Risks:** poison messages and visibility-timeout misconfiguration (OQ-505, OQ-139); sweepers (outbox, task re-publish, 2 h deadline) must be correct because the broker alone is not trusted (LLD 06 D-06-3).

**Consequences.** No Celery results backend: state lives in Postgres. `task_key` and finding unique keys enforce idempotency. DLQ replay tool scope is an open question (OQ-506).

**Reversibility:** medium (task handlers are framework-light; broker is config).

---

## ADR-006 — AI Gateway implementation

**Status:** Decided by user (custom thin gateway)

> **Update (ADR-017):** The custom thin gateway is **realised as an in-process library module inside the worker image**, not as a separately deployed FastAPI service. Masking, allow-lists, budgets, retries, response checks and logging are kept; the HTTP endpoints, deployment, autoscaler, mTLS hop and second provider are removed. The user decision to build custom rather than adopt LiteLLM stands. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** All LLM and embedding traffic must leave through one point that masks PII, enforces field allow-lists, routes, retries, fails over, budgets tokens, validates responses and logs (HLD §8.3, §5.4).

**Problem.** Build a thin service or adopt a proxy?

**Options considered**
1. **Custom thin FastAPI service** with provider SDKs behind a small provider interface (`/v1/complete`, `/v1/embed`).
2. LiteLLM-based gateway with custom hooks.
3. Cloud-native only (e.g. Bedrock features directly, no gateway).

**Selected approach.** Option 1 (user decision).

**Justification.** DQA's requirements are control-heavy rather than provider-breadth-heavy: two providers, mandatory masking before any call, per-batch budgets, response-validation hooks, and kill-switch semantics. A thin custom service keeps the security-critical path small and fully owned and avoids inheriting a large proxy's surface area; two providers do not justify a multi-provider abstraction library.

**Advantages:** minimal dependency surface; exact control over masking, logging and error taxonomy; simple to reason about for audit.

**Disadvantages:** we own retries, circuit breaking, price tables, SDK upgrades and any new provider adapter; fewer built-in features than LiteLLM (OQ-205 circuit-breaker policy, OQ-542 price-table ownership).

**Risks:** re-implementing solved problems incorrectly (mitigation: a narrow scope, provider contract tests, recorded-response tests); gateway becomes a single point of failure (mitigation: horizontal scaling, rule-only mode when down).

**Consequences.** Workers never import provider SDKs (enforced by a lint/CI rule); adding a provider is a gateway change plus evaluation. If scope grows beyond two providers, revisit LiteLLM via a new ADR.

**Reversibility:** medium (the gateway's HTTP contract is stable for workers).

---

## ADR-007 — Feature-flag service

**Status:** Decided by user (Unleash)

**Context.** Flags: `ai_layer_enabled`, `ai_task.<task>.enabled`, `prompt.<task>.canary_pct`, `bulk_approve_enabled` (the HLD's `model.<task>.route` was removed by ADR-018), evaluated (HLD §6.7). The AI kill-switch must work in an incident.

**Problem.** Which flag service, and what happens when it is unreachable?

**Options considered**
1. **Unleash** (self-hosted).
2. LaunchDarkly (SaaS).
3. Config-file or database flags with no dedicated service.

**Selected approach.** Option 1 (user decision).

**Justification.** Self-hosting avoids a SaaS dependency and a third-party processing context; the flag needs (boolean, percentage rollout, context) are well within Unleash's scope.

**Advantages:** no external vendor; strategies; SDK caching.

**Disadvantages:** another stateful service to host, upgrade and make highly available (OQ-516); no vendor SLA.

**Risks:** flag service down on cold start. **A-08 (provisional):** unreachable on cold start ⇒ AI flags default **off**, rule-only continues. Propagation delay may leave in-flight AI calls running after a kill-switch (OQ-250).

**Consequences.** Flag definitions and defaults are documented per environment; flag changes are audited (audit_event). A hidden-AI "shadow mode" flag is added (OQ-28 / OQ-249).

**Reversibility:** high (thin client interface).

---

## ADR-008 — Cloud and runtime platform

**Status:** Proposed — pending user confirmation (HLD §8; A-01, OQ-14, OQ-501)

**Context.** Needs: private networking, managed Postgres with PITR, managed queues, KMS, workload identity, queue-depth autoscaling, reproducible infrastructure, regional data control.

**Problem.** Where and on what does DQA run?

**Options considered**
1. **AWS: EKS + Terraform + Argo CD/Rollouts** (HLD).
2. AWS ECS/Fargate + Terraform.
3. Another cloud or on-prem Kubernetes.

**Selected approach.** Option 1 as the working baseline, **unconfirmed**.

**Justification.** Bedrock (ADR-001), SQS (ADR-005), RDS, S3 and VPC endpoints are all AWS-native; EKS gives KEDA scaling and canary rollouts (Argo Rollouts), matching HLD §8.7 and §8.9. ECS/Fargate would reduce operational weight and is a legitimate alternative if platform skills for Kubernetes are not available; this is a decision the user should make with platform ownership known (OQ-500).

**Advantages:** managed data services, mature IAM/KMS, KEDA-based scaling, GitOps rollouts.

**Disadvantages:** Kubernetes operational cost and skill need; AWS lock-in; (the Azure OpenAI connectivity concern is gone with ADR-017; OQ-509 resolved).

**Risks:** over-built for v1 scale; DR objectives not met by the HLD design as written (see RISKS R-OP-02); egress control to two clouds.

**Consequences.** Terraform for all infrastructure, DR region rebuildable from code; secrets in Secrets Manager with External Secrets Operator.

**Reversibility:** low for the cloud, medium for EKS vs ECS.

---

## ADR-009 — System-of-record database

**Status:** Proposed — pending user confirmation (HLD §2.5, §6.5)

**Context.** Needs: transactions, role/grant-based access control, JSONB for raw/evidence, unique constraints for idempotency, append-only audit, optional vectors (ADR-003), 7-year retention.

**Problem.** Which datastore is the system of record?

**Options considered**
1. **PostgreSQL 16 (RDS Multi-AZ) with pgvector**.
2. Document store (e.g. DynamoDB/MongoDB) plus a separate relational store.
3. Another relational engine.

**Selected approach.** Option 1.

**Justification.** Idempotency (`ON CONFLICT DO NOTHING`), grants, constraints, JSONB and the hash-chained audit table are native strengths; one engine to back up and secure. Migrations via Alembic using expand → migrate → contract (HLD §6.5, §8.9).

**Advantages:** strong consistency, grants, mature tooling, PITR (35 days).

**Disadvantages:** single-region write limits (partition `finding` by month at ~500M rows, HLD §11.5); connection exhaustion from autoscaled workers (the HLD omits a pooler, OQ-504, RISKS R-TECH-03).

**Risks:** over-broad grants; long migrations on large tables; checkpoint and audit growth.

**Consequences.** A connection pooler is required in practice. Grants must deny UPDATE/DELETE on every append-only table. Retention vs immutability conflicts are resolved in OQ-26 / OQ-402.

**Reversibility:** low.

---

## ADR-010 — Agent architecture pattern

**Status:** Proposed — pending user confirmation (HLD §3.2)

> **Update (ADR-019):** Supervisor + specialists is kept as a deterministic **pipeline of code steps plus three AI task handlers** (category, normalisation, duplicate); there is no graph framework and no escalation back-edge. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** Rules and heuristics decide most cases; only uncertain records reach AI. Requirements demand predictability, explainability, bounded cost and no autonomous actions.

**Problem.** How many agents, and who decides what runs next?

**Options considered**
1. **Supervisor + specialists as a deterministic graph**: code-based triage and validator, three LLM specialists (Category, Normalisation, Duplicate), template composer.
2. A single general agent with all tools.
3. An autonomous multi-agent system where agents delegate to each other.

**Selected approach.** Option 1. Triage, validation and explanation are code, not LLM calls; agents communicate only through graph state and the queue; tools are read-only, allow-listed per agent.

**Justification.** Each AI task has a narrow input, a typed output and a different best model tier, so specialists are cheaper and easier to evaluate than one general agent. A deterministic supervisor removes the risk of the model choosing tools or loops, which the NFRs (safety, cost, auditability) cannot tolerate. Autonomous delegation adds nondeterminism with no benefit for a three-task problem.

**Advantages:** testable trajectories; per-task evaluation and tier choice; bounded cost; simple failure analysis.

**Disadvantages:** adding a task means editing the graph; less flexibility for open-ended reasoning (not required).

**Risks:** specialists overlap in responsibility (mitigation: AGENT_DESIGN boundaries); over-use of AI if triage is too loose (cost target < 30 %).

**Consequences.** Hard caps: tool calls per step, LLM calls per task (provisional 3, OQ-300), step counter with `loop_guard_triggered`, token budget per batch.

**Reversibility:** medium.

---

## ADR-011 — Immutable snapshots and hash-chained audit

**Status:** Proposed — pending user confirmation (HLD §4.4, §5.7, §6.5)

**Context.** NFR: input records must be byte-identical before and after processing; every finding, decision, model/prompt version and export is traceable for 7 years; audit must be tamper-evident.

**Problem.** How to guarantee non-mutation of inputs and tamper-evident traceability.

**Options considered**
1. **Immutable `record_snapshot` rows + append-only `audit_event` table with a hash chain** (`prev_hash`, `hash`), also streamed to the SIEM.
2. Ordinary mutable tables with triggers or application-level logging.
3. A managed ledger database.

**Selected approach.** Option 1; database permissions deny UPDATE/DELETE on both tables for application roles. Chain scope (global vs), verification cadence and external anchoring are open (OQ-114, OQ-403, OQ-546).

**Justification.** Meets the requirement within the existing database (ADR-009) without another system; the SIEM stream provides an independent copy.

**Advantages:** tamper evidence, reproducibility, simple model.

**Disadvantages:** chain writes serialise per chain (throughput ceiling if global); retention vs right to erasure conflict (OQ-26, OQ-402); storage growth.

**Risks:** hash-chain contention under load; a corrupted chain invalidates later verification.

**Consequences.** Per-chains are the likely scale path (decision pending). Raw-record retention (2 years in the HLD) must not break 7-year traceability of findings.

**Reversibility:** low once data exists.

---

## ADR-012 — Finding source and rule/AI merge model

**Status:** Proposed — **PROVISIONAL**, pending user confirmation (OQ-18, OQ-19, OQ-130, OQ-218, OQ-310)

**Context.** The HLD uses source badges Rule / Heuristic / AI and `source: ai_suggestion`; the brief's expected output uses `deterministic_rule` and `ai_or_heuristic_candidate`, and a deterministic confidence of 0.95 against the HLD's 1.0. When rule and AI both flag the same record, the HLD says keep one finding with the higher confidence and both sources listed, or keep both if they disagree (§6.1 step 6).

**Problem.** One canonical `source` vocabulary and a merge rule that fit one column, one `dedupe_key` and the API.

**Options considered**
1. **Enum `deterministic_rule | heuristic | ai_suggestion`** plus a separate list of contributing sources; brief labels mapped at the API boundary.
2. Adopt the brief's labels as canonical.
3. Free-text source string.

**Selected approach (provisional).** Option 1. The finding keeps a primary `source` and an `evidence_sources` list; disagreement keeps two findings flagged for review. The mapping of `ai_or_heuristic_candidate` is **unresolved**.

**Justification.** The HLD's three-way distinction drives UI badges, calibration (only AI is calibrated) and metrics (precision by source); collapsing heuristic and AI would lose that.

**Advantages:** accurate attribution and metrics; backward compatible with HLD examples.

**Disadvantages:** diverges from the user-supplied brief output; needs an explicit mapping decision; pair findings (duplicates) complicate `dedupe_key` (OQ-27).

**Risks:** acceptance tests written against the brief fail if semantics differ (OQ-12, OQ-222, OQ-432).

**Consequences.** Golden-test assertion mode (exact vs required-set) must be decided before test implementation (OQ-432).

**Reversibility:** medium before release, low after (stored values and API contracts).

---

## ADR-013 — Batch-scope pass for cross-record checks

**Status:** Proposed — **PROVISIONAL**, pending user confirmation (LLD 06 D-06-1; OQ-119)

**Context.** The HLD processes 50-record chunks (§4.1), but `duplicate_item_id`, exact-MPN blocking and description similarity compare records across the *whole batch* (and, for similarity, against approved items).

**Problem.** Chunked processing cannot detect duplicates that fall in different chunks.

**Options considered**
1. **Per-chunk record rules plus a separate batch-scope pass** (after all chunks) for duplicate checks.
2. Make the chunk size equal to the batch (no chunking).
3. Pre-partition by blocking key before chunking.

**Selected approach (provisional).** Option 1: per-record rules and heuristics run per chunk; a `batch_scope_checks` stage runs once all chunks complete and must finish inside its stage timeout; batch completes only when it and AI are complete.

**Justification.** Keeps chunk-level parallelism, checkpointing and idempotency for the bulk of the work and confines the O(n) grouping to one controlled stage (blocking keeps it near O(n), HLD §6.1).

**Advantages:** correct duplicate detection; chunk parallelism preserved; clear completion semantics.

**Disadvantages:** time-to-first-finding is unaffected for chunk findings but duplicate findings arrive later; memory for a 100k-record grouping; stage timeout needs sizing.

**Risks:** stage becomes the bottleneck at 100k records; false pairs inside very large manufacturer blocks (OQ-129, OQ-213).

**Consequences.** Batch states and metrics include the batch-scope stage; performance tests cover 100k records (HLD §7.8).

**Reversibility:** medium.

---

## ADR-014 — PII masking approach

**Status:** Proposed — pending user confirmation (HLD §5.4; LLD 07)

**Context.** Free-text fields can contain names, emails, phones or supplier pricing; none may reach a provider. Part numbers and sizes look like identifiers and must survive masking to keep suggestions useful.

**Problem.** Where and how is masking done, and what happens when it fails?

**Options considered**
1. **In the in-process AI access layer (ADR-017), mandatory, Presidio + custom regex**, field allow-lists per task, opaque keys for `item_id`/`record_key`, residual scan after masking.
2. Mask in each worker before calling the gateway.
3. Rely on the provider's data-protection features.

**Selected approach.** Option 1. A residual scan finding PII after masking ⇒ `policy_block`; the call does not go out. The reverse mapping for opaque keys stays in worker memory/state and is never sent.

**Justification.** A single enforcement point cannot be bypassed by a worker bug; provider features are not a substitute for not sending the data.

**Advantages:** one place to test and audit; fail-closed.

**Disadvantages:** masking can degrade quality (e.g. part numbers mistaken for phone numbers; OQ-206, OQ-406); added latency; regex list needs ownership.

**Risks:** false negatives leaking PII (SEV1 per incident table); false positives masking part numbers.

**Consequences.** PII-leak tests (seeded emails/phones) are a release gate; the detector list and exemptions are reference data owned by someone named (OQ-206).

**Reversibility:** high.

---

## ADR-015 — Observability stack

**Status:** Proposed — pending user confirmation (HLD §2.3, §9; OQ-549)

> **Update (ADR-021):** Langfuse is dropped. LLM call metadata lives in the `ai_task` table plus OpenTelemetry spans and Prometheus metrics; sampled masked prompt/response bodies are kept in the database or S3 under the existing retention. No additional observability service. The original HLD-based text below is kept for history; where it conflicts with this update, the update wins.

**Context.** One trace id must follow a batch from upload through every rule, agent step, tool call and LLM request to the steward's decision; LLM calls need prompt-level inspection; cost per 1k records and per approved finding are key unit metrics.

**Problem.** Which telemetry stack, and how is PII kept out of it?

**Options considered**
1. **OpenTelemetry + Prometheus/Grafana + Langfuse (LLM spans) + Sentry, structlog JSON to CloudWatch/OpenSearch** (HLD).
2. A single commercial observability platform.
3. Cloud-native only (CloudWatch/X-Ray).

**Selected approach.** Option 1 as the baseline; vendor-neutral OpenTelemetry instrumentation keeps the back end swappable.

**Justification.** OpenTelemetry avoids lock-in at the instrumentation layer; Langfuse covers prompt-level traces and replay that general APM tools do not.

**Advantages:** open standards; LLM-specific visibility; fine-grained cost attribution.

**Disadvantages:** several components to run (Langfuse hosting, Grafana, Sentry); masked prompt/response storage is itself sensitive (OQ-541); trace sampling needs a policy (OQ-540).

**Risks:** telemetry leaking PII (mitigation: no raw record text in logs, masked bodies only, 10 % sample in production); alert noise.

**Consequences.** Dashboards and alerts in OBSERVABILITY doc map to every major infrastructure component; Langfuse hosting and retention need an owner.

**Reversibility:** high.

---

## ADR-016 — Single-entity deployment, no multi-tenancy

**Status:** Decided by user

**Context.** The HLD PDF assumed a multi-tenant service: `tenant_id` on every table, Postgres row-level security (RLS), per-tenant vector namespaces and S3 prefixes, tenant routing at the gateway, per-tenant budgets, concurrency caps and feature-flag evaluation. The user has decided that DQA is built for a single entity (one organisation) only.

**Problem.** Keep the multi-tenant design, or remove the tenant concept entirely?

**Options considered**
1. **Single entity, no tenant concept**: no `tenant_id`, no RLS, global budgets/limits/flags, access control by role and batch ownership.
2. Keep multi-tenancy (RLS, per-tenant isolation) for future SaaS use.
3. Single entity now but keep a dormant `tenant_id` column for later.

**Selected approach.** Option 1.

**Justification.** There is no stated requirement for more than one entity (YAGNI). Removing the tenant dimension simplifies the schema, queries, cache keys, retrieval, budgets, flags, dashboards and tests, and removes a whole class of defects (missing filter, mis-set session variable).

**Advantages:** simpler schema and indexes (no tenant column in keys); no RLS configuration or session-variable handling; global budgets, concurrency and flags; fewer tests; one audit hash chain; smaller operational surface.

**Disadvantages:** later multi-tenancy would need a schema migration, an RLS design and a review of every cache key, index, prompt and S3 path; no isolation between organisations if the deployment is ever shared.

**Risks:** an unstated future requirement for a second entity; inside one entity, data access still depends on correct role and batch-ownership checks and on least-privilege DB grants, because RLS is no longer a backstop.

**Consequences.**
- Removed: `tenant_id` columns and keys, RLS policies, per-tenant S3 prefixes, vector namespaces and partitions, tenant routing, per-tenant budgets/caps/dashboards, tenant offboarding, cross-tenant tests and alerts.
- Kept: role-based access (Uploader: own batches; Data Steward, Data Owner, Auditor: all batches; Platform Admin: metadata only), batch ownership, least-privilege DB grants, encryption, audit.
- Reference data is global. The audit hash chain is one global chain.
- "Pilot tenant" becomes a pilot group (users or source systems) in the go-live stages.
- Any future multi-tenancy requires a new ADR and migration plan.

**Reversibility:** low (schema-level), by design a conscious simplification.

## ADR-017 — In-process AI access layer, single provider

**Status:** Decided by user — direction (simplify the LLM parts, minimum infrastructure, cost-effective); specifics PROVISIONAL, pending confirmation (OQ-700, OQ-207)

**Context.** The HLD placed all LLM traffic behind a separate AI Gateway service (HTTP `/v1/complete`, `/v1/embed`, own deployment, HPA, mTLS) with Bedrock primary and Azure OpenAI fallback. ADR-006 (user) chose a custom thin gateway over LiteLLM. The user now wants minimum infrastructure and lower cost.

**Problem.** How much of the gateway needs to be a deployed service, and is a second provider worth its cost and complexity?

**Options considered**
1. Separate gateway service, two providers (HLD).
2. Separate gateway service, one provider.
3. **In-process library module in the worker image, one provider behind a small adapter interface.**
4. Call the provider SDK directly from handlers with no common layer.

**Selected approach.** Option 3. The module keeps masking, field allow-lists, budget guard, retry/backoff, response checks, `task_key` cache and logging to `ai_task`. Network egress of the worker pods is restricted to the single LLM endpoint. A structure test fails the build if another module imports a provider SDK. The provider (Bedrock as proposed) is confirmed by OQ-700; the adapter keeps lock-in low.

**Justification.** All callers are Python workers already, so an in-process module provides the same single exit without a service to deploy, scale, secure and monitor. A second provider doubles contracts, prompt evaluation and credentials for a rare outage, which rule-only mode already covers (HLD §8.10).

**Advantages:** no gateway deployment, HTTP hop, mTLS hop or autoscaler; fewer credentials; the embedding dimension conflict disappears; simpler tests and docker-compose.

**Disadvantages:** one provider outage means no AI until recovery (rule-only meanwhile); the control point is code, so discipline (structure test, review) replaces a network boundary; a later second consumer outside the worker (for example a UI feature) would need the module extracted into a service.

**Risks:** single-provider dependency and vendor lock-in (adapter, pinned versions, monthly golden re-run); provider quota limits throughput (KEDA cap).

**Consequences.** Removes `ai-gateway` from infrastructure, HLD diagrams and compose; LLD 07 becomes the AI Access Layer spec; HLD §11.3's two-provider requirement is dropped; OQ-208 and OQ-21 are resolved; the Azure credentials and private link disappear.

**Reversibility:** medium (extract the module into a service if a second consumer appears; add a second adapter if the risk register demands it).

---

## ADR-018 — Two model tiers, 2-call cap, no escalation

**Status:** Decided by user — direction; specifics PROVISIONAL, pending confirmation (OQ-301, OQ-207)

**Context.** The HLD used three tiers (small, mid, top) with one escalation to the top tier for low-confidence results and one repair, and contradicted itself on the call cap (max 2 vs repair + escalation = 3).

**Problem.** Which tiers and call limits give acceptable quality at the lowest cost?

**Options considered**
1. Three tiers, escalation, cap 3 (HLD, reconciled).
2. **Two tiers (small/fast for normalisation; mid for category and duplicate adjudication), one repair, no escalation, cap 2.**
3. One tier for everything.

**Selected approach.** Option 2. Low confidence or `unsure` is shown to the steward as Investigate; humans decide. The offline evaluation judge uses the mid tier.

**Justification.** Escalation to the largest model is the most expensive call for the least certain records, and the human review step already handles uncertainty. Cap 2 matches HLD §4.8 literally and resolves the HLD contradiction.

**Advantages:** lower and more predictable cost; simpler routing and tests; resolves OQ-20/OQ-210/OQ-300/OQ-421.

**Disadvantages:** hard cases get no stronger-model second opinion, so more records land in the Investigate tab; classification quality is bounded by the mid tier.

**Risks:** mid tier may underperform on the golden set (measure before go-live; if needed a new ADR can add a tier).

**Consequences.** Removes escalation logic, the escalation back-edge and its tests; `model.<task>.route` flag removed (one model per task by config); `ai_task` records `attempts` ≤ 2.

**Reversibility:** high.

---

## ADR-019 — Plain Python pipeline replaces LangGraph

**Status:** Decided by user — direction; specifics PROVISIONAL, pending confirmation

**Context.** ADR-002 proposed LangGraph for a fixed graph where code decides every step. ADR-010 kept supervisor + specialists.

**Problem.** Does a fixed, code-driven flow justify an agent-framework dependency, its checkpointer and its upgrade surface?

**Options considered**
1. LangGraph with Postgres checkpointer (HLD).
2. Temporal / Step Functions.
3. **Plain Python functions (`triage → run task → validate → compose → persist`) with progress in `ai_task` and chunk status, idempotent by `task_key`.**

**Selected approach.** Option 3. The three specialists become AI task handlers (prompt + schema + allowed tools); agent cards stay in AGENT_DESIGN.md. Replay re-runs a chunk with a new prompt version writing to evaluation tables. Loop prevention is a step counter plus the single repair.

**Justification.** The model never routes, so graph features (dynamic edges, interrupts, checkpointer) are unused; human-in-the-loop is the review queue. Fewer dependencies and simpler operations.

**Advantages:** no framework dependency or checkpointer tables; easier tests; same resume and idempotency guarantees via `task_key`.

**Disadvantages:** resume and replay logic is written by us; adding a genuinely dynamic multi-step agent later would need a framework or a new ADR.

**Risks:** hand-rolled progress tracking bugs (mitigated by kill-and-resume tests).

**Consequences.** Removes LangGraph and the graph checkpointer from stack, infra, docs and tasks; LLD 08 becomes the AI task pipeline spec.

**Reversibility:** medium.

---

## ADR-020 — Simplified RAG on the existing Postgres

**Status:** Decided by user — direction; specifics PROVISIONAL, pending confirmation (OQ-227, OQ-228)

**Context.** The HLD specified hybrid BM25 + vector retrieval with reranking, nightly re-indexing and a fallback embedding model.

**Problem.** What is the least infrastructure that still grounds category and duplicate suggestions?

**Options considered**
1. HLD hybrid with a reranker model and a dedicated search engine.
2. **pgvector + Postgres full-text (`tsvector`) in the existing cluster, rank fusion, no reranker.**
3. Vector only.

**Selected approach.** Option 2. One embedding model; embeddings computed only for taxonomy nodes and approved items, in batches, on change plus a nightly delta; abbreviation dictionary stays exact lookup; top-k 5.

**Justification.** No new service, no extra model call per query, small corpora. Move to a dedicated store only at the HLD triggers (10M vectors or p95 > 100 ms).

**Advantages:** no new infra or cost; simpler index maintenance.

**Disadvantages:** lower ranking quality than a reranker (measure recall@5, target 0.9); full-text on short technical strings can be weak.

**Risks:** retrieval quality below target (OQ-228 tuning; vector-only fallback).

**Consequences.** LLD 10 simplified; OQ-227 resolved in principle; retrieval evaluation (T8) gates go-live.

**Reversibility:** high.

---

## ADR-021 — Cost controls and simplified observability

**Status:** Decided by user — direction; specifics PROVISIONAL, pending confirmation (OQ-15, OQ-701, OQ-702)

**Context.** NFR cost target is below USD 0.50 per 1k records, yet the HLD batch budget (USD 25) allows up to 50 for 100k records (OQ-15). The HLD adds Langfuse for LLM tracing.

**Problem.** Which controls keep AI cost low, and which tooling is unnecessary?

**Options considered**
1. HLD set (Langfuse + gateway metrics + escalation).
2. **Cost-first set: triage < 30% to AI, `task_key` cache, prompt caching where supported, optional batch/off-peak inference, small token caps, per-batch USD guard, hard kill-switch; LLM metadata in `ai_task` + OTel + Prometheus; no Langfuse.**

**Selected approach.** Option 2, with an assumption-labelled cost model in LLM_MANAGEMENT.md (no invented prices).

**Justification.** Cost is driven by how many records reach AI and which tier answers; observability needs are met by data already stored.

**Advantages:** one fewer service; cost is measurable per batch/task/prompt version from `ai_task`.

**Disadvantages:** no prompt-level UI like Langfuse (SQL/Grafana dashboards instead); batch/off-peak inference adds latency for those runs (acceptability OQ-702).

**Risks:** cost target unmet if triage sends > 30% to AI.

**Consequences.** Supersedes the Langfuse part of ADR-015; OPS and LLM_MANAGEMENT updated; Unleash (ADR-007, user-decided) remains an extra service, flagged in OQ-703.

**Reversibility:** high.

## ADR-022 — Steward UI in scope: Vite + React + TypeScript + TanStack Query/Table, plain CSS tokens

**Status:** Decided by user for scope and stack (2026-11-04); design direction PROVISIONAL (OQ-807). UI code is **paused until the backend API (P2/P3) exists**, per user.

**Context.** The first documentation round treated the UI as an API consumer only (OQ-25, OQ-420). The user has put the Steward UI in scope; the HLD names React + TypeScript and nothing more.

**Problem.** Which front-end stack and build approach fits a data-steward back office with large cursor-paginated tables, URL-driven filters and a small team?

**Options considered**
1. Next.js + React + TypeScript (server rendering, routing conventions).
2. Vite + React + TypeScript + Tailwind/shadcn (fast styling, template look).
3. **Vite + React + TypeScript + TanStack Query/Table, plain CSS with design tokens, Vitest + Playwright.**

**Selected approach.** Option 3. Static SPA (hosting provisional, OQ-808), server state in TanStack Query, filters/sort/page/tab in the URL, tokens as CSS custom properties.

**Justification.** No SEO or server rendering need; the smallest dependency set meets the JS budget (< 300 kB gz, web performance rules); plain CSS tokens allow a deliberate visual direction instead of library defaults.

**Advantages:** minimal build and hosting; typed API client from the LLD 04 contract; easy visual-regression and a11y testing.

**Disadvantages:** hand-written components (no ready kit); design-system work falls to the team; no SSR.

**Risks:** API contract shifts in P2/P3 invalidate the UI LLD (module 13); token handling in a SPA (OQ-800); design taste unconfirmed (OQ-807).

**Consequences.** New module [13-steward-ui.md](../lld/modules/13-steward-ui.md), phase P3b and tasks U-01..U-13; static hosting added to infrastructure; UI test types added to the testing document. Supersedes the "no UI LLD" scope note; OQ-25 and OQ-420 are resolved for scope only.

**Reversibility:** medium (component code is framework-bound; API contract is not).

## ADR-023 — Open access: no authentication or role-based authorisation

**Status:** Decided by user (2026-11-04: "remove the signin process, just let anyone view and see it"). Supersedes the authentication, RBAC and four-eyes parts of HLD 5.1/5.2/4.10, the security document sections 3.2-3.5, and ADR-016's "role and batch-ownership access control".

**Context.** The HLD requires corporate SSO (OIDC/SAML), RBAC and batch ownership. The owner wants the application usable by anyone who can reach it, with no sign-in.

**Problem.** Remove login and role gating without breaking the audit trail, the API contract or the UI.

**Options considered.** (1) Keep SSO and RBAC (HLD). (2) Open access with an anonymous principal and an `Authenticator` slot kept for later. (3) Shared static API key. (4) Remove the concept of a user entirely.

**Selected approach.** Option 2. The API's default `auth_mode` is `open`: every request is `Principal("anonymous", all roles except Platform Admin)`; a startup WARNING states "auth disabled: open access". `dev_header` mode stays for role-matrix tests. The UI has no sign-in, no role-gated visibility and shows an "Open access" footer note.

**Justification.** Smallest change that meets the instruction, keeps the `Authenticator` Protocol so real OIDC can be added without API changes, and keeps one audit actor field.

**Advantages:** no IdP dependency, simpler UI and API, faster adoption.

**Disadvantages and consequences:**
- Audit actor is always `anonymous`: no individual accountability for decisions or exports.
- Four-eyes / Data Owner second approval cannot be enforced; Uploader ownership and the Auditor read-only role are void (OQ-821).
- Network-level protection (private network, VPN, WAF allow-list) becomes the **only** control. The service must not be exposed to the public internet (OQ-820).
- Anyone reaching it can read item data (commercial / possibly personal data in free text), upload, approve, reject and export change files that the MDM team may apply. Unauthenticated write endpoints are an OWASP A01/A07 exposure.
- AI cost abuse by anonymous uploads is limited only by the per-batch budget and network exposure.

**Risks:** R-SEC-OPEN (unauthenticated access incl. decisions and exports). **Reversibility:** high (Authenticator slot), but the audit history stays anonymous. Reintroducing authentication needs a new ADR.

## Architecture decisions

This file *is* the decision record. Decisions that remain open and could change an ADR: OQ-16 (stack confirmation), OQ-14/OQ-501 (cloud), OQ-18 (source vocabulary), OQ-119 (batch scope), OQ-700 (provider/model confirmation). OQ-208 is resolved by ADR-017.

## Dependencies

- Inputs: [HLD](../hld/HLD.md), [BRD](../business/BRD.md), [LLD](../lld/LLD.md) modules 05–12, [AI architecture](../ai/AI_ARCHITECTURE.md), [Security](../security/SECURITY_AND_GOVERNANCE.md), [Infrastructure](../infra/INFRASTRUCTURE.md).
- Consumers: [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md), [TASK_BREAKDOWN](TASK_BREAKDOWN.md), [OPEN_QUESTIONS](OPEN_QUESTIONS.md), [RISKS_AND_DEPENDENCIES](RISKS_AND_DEPENDENCIES.md).

## Risks and edge cases

- Several ADRs are only *Proposed*; building on them before confirmation risks rework (mitigation: approval gate, OQ-16).
- ADR-012 and ADR-013 are provisional answers to HLD contradictions; changing them after implementation is costly.
- ADR-005 relies on Celery's SQS transport limits being acceptable; if not, the fallback is a thin custom SQS consumer layer (new ADR).
- Any change to an accepted ADR requires a superseding ADR before code changes.

## Related documents

- [RISKS_AND_DEPENDENCIES.md](RISKS_AND_DEPENDENCIES.md)
- [docs/README.md](../README.md)
