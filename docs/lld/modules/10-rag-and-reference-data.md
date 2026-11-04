# LLD 10 — RAG and Reference Data Service

## 1. Purpose

Provide (a) versioned, steward-owned **reference data** (taxonomy, allowed UoM, generic terms, manufacturer aliases, abbreviations, severity policy, calibration, forbidden terms) and (b) **retrieval** over curated internal indexes that ground the AI task handlers and support duplicate search (HLD §2.2, §3.7, §6.5, §8.4).

## 2. Scope

In scope: `reference_data` versioning and read API; the missing write/approval path; the three indexes `taxonomy`, `approved_items`, `abbreviations`; simplified hybrid retrieval (Postgres full-text + vector, rank fusion, no reranker model, ADR-020); top-k = 5; isolation; on-change refresh plus nightly delta; embedding generation via the in-process AI Access Layer; the pgvector schema use; `similar_items` / `taxonomy_lookup` backing.

Out of scope: embedding transport (LLD 07), handler use (LLD 08), duplicate **heuristic** blocking with RapidFuzz (LLD 03), RBAC primitives (LLD/Security doc). A dedicated vector DB is a future path (HLD §8.4, ADR-003).

## 3. Detailed explanation

### 3.1 Responsibilities

1. Serve versioned reference data to rules, heuristics, validator and task handlers.
2. Provide a controlled write path to reference data (HLD gap, see §3.5).
3. Maintain indexes: ingest, embed, store, refresh.
4. Answer retrieval queries with ids so model evidence can be grounded (HLD §3.7).
5. Serve reads through a read-only DB role with parameterised queries and result-size caps.
6. Feed approved steward decisions into the retrieval index only after review (HLD §3.6: "never automatically into prompts unvetted").

### 3.2 Input and output

| Aspect | Definition |
|---|---|
| Input | Steward-maintained reference lists; approved findings/decisions; masked approved item text; queries from tools/heuristics |
| Output | Versioned reference payloads; ranked retrieval results with ids and scores; index health metrics |
| Never | Retrieval of unapproved items; use of external internet documents (HLD §5.3: curated internal indexes only) |

### 3.3 API contracts

Internal service (Python module + REST for the public part). The public read endpoint is HLD §6.4; the write endpoints below are **proposed** because the HLD lists only `GET` (**OQ-223**).

`GET /api/v1/reference-data/{type}` (HLD §6.4)

```json
{
  "type": "allowed_uom",
  "version": 7,
  "effective_from": "2026-11-01T00:00:00Z",
  "values": ["EA", "PC", "BOX", "KG", "M", "L", "SET", "PR"],
  "aliases": { "EACH": "EA", "PCS": "PC" }
}
```

Types (from HLD): `allowed_uom` (default EA, PC, BOX, KG, M, L, SET, PR), `taxonomy`, `generic_terms` (default bearing, valve, part, item, misc, spare), `min_description_tokens` (3). Additional types introduced by the other HLD sections (manufacturer aliases, abbreviation dictionary, keyword→category map, severity policy, calibration, forbidden terms, price table) are **not** in the §6.4 list of served types; whether they use the same endpoint is **OQ-224**.

Proposed write path (not in HLD):

```
POST /api/v1/reference-data/{type}/versions        body: {values|diff, change_reason}
-> 202 {version: 8, status: "pending_approval"}
POST /api/v1/reference-data/{type}/versions/{v}:approve   (second person)
-> 200 {version: 8, status: "active", effective_from: "..."}
```

Who may write: stewards "maintain" it (HLD §1.3) while RBAC §5.2 grants **Admin config** only to Platform Admin and gives stewards no config right. Role mapping is **OQ-225**.

### 3.4 Reference data versioning

- Table `reference_data(type, version, values jsonb, effective_from)` (HLD §6.5). Append-only; a new version never mutates an old one.
- Every finding stores the versions it used (HLD §6.6), so old findings remain explainable.
- A batch pins the reference versions at **batch start** (A-211), so a mid-batch change cannot produce inconsistent findings within one batch. Reference data is global (single entity, ADR-016; OQ-226 resolved).
- Changes emit `audit_event` (configuration change, HLD §5.7) and trigger re-indexing for `taxonomy` and `abbreviations` (HLD §3.7).

### 3.5 The missing write path (summary of the gap)

The HLD states stewards own and maintain reference data (§1.3, §6.2 owners: Steward, Data Owner, Engineering, Product, Finance) but defines no endpoint, workflow, approval or role to do so; the RBAC table gives only Platform Admin "Admin config". This module proposes the two endpoints above with maker-checker approval, and flags the decision (OQ-223/225). Without it, reference data can only be loaded by deployment/config, which contradicts "steward-maintained".

### 3.6 Indexes (HLD §3.7)

| Index | Content | Used by | Retrieval type |
|---|---|---|---|
| `taxonomy` | category nodes with definitions and example items | Category handler (`taxonomy_lookup`) | full-text + vector, rank fusion |
| `approved_items` | steward-approved clean records (masked) | Category, Duplicate handlers (`similar_items`) | full-text + vector, rank fusion |
| `abbreviations` | domain dictionary (BRG=bearing, VLV=valve, SS=stainless steel) | Normalisation handler (`abbreviation_dictionary`) | **exact lookup, not vector** |

Storage: pgvector in the main RDS cluster, table `item_embedding(record_key, vector(1024), source ∈ {approved, taxonomy})` with HNSW indexes and partitioning (HLD §6.5, §8.4). The lexical leg uses **Postgres full-text search** (`tsvector` + GIN index) over description tokens, so no extra search infrastructure is needed (ADR-020; OQ-227 resolved in principle: Postgres FTS).

### 3.7 Retrieval algorithm (simplified hybrid, ADR-020)

```
retrieve(query_text, index, k=5):
  1. normalise query (same normalisation as ingest; mask PII)   # same masker as LLD 07
  2. lexical: Postgres full-text rank (ts_rank)  -> candidates L (top N_l)
  3. vector: embed(query) via AI Access Layer embed(), ANN search
     (HNSW)                         -> candidates V (top N_v)
  4. fuse: reciprocal rank fusion of L and V (no reranker model) -> ranked list
  5. return top-k=5 items, each with id, score, source index, index version
```

The HLD says only "reranked"; this design uses simple rank fusion and **no separate reranker** to avoid another model and its cost (ADR-020). Candidate counts N_l, N_v and the fusion constant: **OQ-228**. Every returned item carries its **id** so the validator can check grounding (LLD 09 check 3). The tool layer records the ids actually returned for the task.

`similar_items(record_key, k)` excludes the record itself, restricts to `approved_items` , and never returns unapproved or rejected content.

### 3.8 Duplicate search relation

LLD 03 owns heuristic duplicate **blocking** (normalised MPN + manufacturer alias; RapidFuzz token-set similarity ≥ 0.88; uncertain band 0.75–0.88). This module supplies embeddings-based candidate search against `approved_items` for cross-batch comparison, in line with "pairwise within a batch plus approved items; no global entity resolution" (HLD §11.6). Whether embedding-similarity candidates feed heuristics, or only the Duplicate agent's `similar_items` tool: **OQ-229**.

### 3.9 Embedding strategy

- Embeddings created by the AI Access Layer `embed()` using **one embedding model** (Titan v2 proposed, HLD §2.7/§3.1; the `text-embedding-3-small` fallback is dropped, ADR-017). Embeddings are computed only for taxonomy nodes and approved items, in batches.
- Dimension: column is `vector(1024)`. With a single model the cross-provider mismatch (OQ-208) is resolved by ADR-017. `model_id` metadata is still stored per row (A-212 proposes an additive `embedding_model` column) so a later model change is detectable and triggers a full re-embed.
- What is embedded: masked, normalised description (+ manufacturer, MPN-normalised token) for items; node name + definition + examples for taxonomy. Exact text composition: **OQ-230**.
- Embeddings are rebuildable from source tables; the vector store is **never a source of truth** (HLD §8.4).

### 3.10 Index refresh (on change + nightly delta)

| Trigger | Action |
|---|---|
| On change | Embed new approved items / changed taxonomy nodes when they are approved or edited (batched) |
| Nightly delta job | Pick up approved decisions since last run and anything missed (after QA gating: A-213); no full rebuild |
| Reference-data change (`taxonomy`, `abbreviations`) | Immediate refresh for that type |
| Manual | Admin-triggered full rebuild (e.g. embedding model change) |

Approval-to-index gate: only findings with a steward-approved **and** (if high-impact) four-eyes-approved decision contribute (HLD §3.6, §4.10). Rejected decisions feed few-shot **negative** examples and evaluation only after review (HLD §10.9 weekly QA). Index writes are upserts keyed by `(record_key, source)`; re-runs are idempotent.

### 3.11 Data access and prompt hygiene (HLD §5.5)

- Single entity (ADR-016): no tenant partitioning. Retrieval runs under a read-only DB role; indexes are internal.
- Prompts carry one record (or pair) only; few-shot examples come only from steward-approved decisions. How the example set is created, approved and flagged: **OQ-231**.
- An unauthorised access attempt is a security event (HLD §10.6).

### 3.12 Database interactions

| Table | Access |
|---|---|
| `reference_data` | read; append new version (write path) |
| `item_embedding` | upsert, ANN query (HNSW), delete on withdrawal/retention |
| `decision`, `finding` | read approved decisions for indexing |
| `audit_event` | insert on reference changes and index rebuilds |

Consistency: a reference-data version becomes `active` atomically (single transaction: status flip + audit event); index rebuild reads a consistent snapshot version.

### 3.13 External dependencies

AI Access Layer `embed()` (10 s timeout, 3 retries, exponential, HLD §4.6); Postgres + pgvector; scheduler (Celery beat or K8s CronJob; Celery assumed, A-214). Tools time out at 2 s with 1 retry; on timeout the tool returns an empty result and the handler may answer `unsure` (A-215).

### 3.14 Error handling and retry

| Failure | Behaviour |
|---|---|
| Embedding service down | Retrieval degrades to BM25-only; indexing job retried; alert |
| ANN query timeout (>100 ms p95 trigger for dedicated store, HLD §8.4) | return BM25 results; log; capacity signal |
| Index empty (before first approvals) | tools return empty; handlers answer `unsure`; steward sees Investigate |
| Reference version invalid/unavailable | block batch start (`policy_block`), alert |
| Partial re-index failure | job resumable by `(record_key)`; previous index stays serving |

### 3.15 Logging

Per retrieval: `trace_id`, `index`, result count, latency, `lexical_only` flag; query text only masked/hashed. Per re-index: counts, duration, embedding model id, failures. Tool calls logged per LLD 08.

### 3.16 Security

Read-only DB role for tool access; parameterised queries; result-size caps; retrieval only from curated internal indexes; no PII in embeddings input (masked first); S3 prefixes for any exported index artefacts; reference-data writes require authorisation and are audited (maker-checker per proposal).

### 3.17 Performance

`taxonomy_lookup` and `similar_items` p95 target is not given in the HLD beyond the trigger (p95 search > 100 ms or > 10M vectors → move to a dedicated store such as OpenSearch k-NN or Qdrant, HLD §8.4); the module monitors both. Read replica for retrieval to avoid OLTP contention (HLD §11.1). HNSW parameters (m, ef): **OQ-232**.

### 3.18 Testing

Unit: `normalize` consistency between ingest and query; fusion ordering; exact-lookup for abbreviations; version pinning. Retrieval eval (HLD §7.4): recall@5 ≥ 0.9 and MRR of the correct taxonomy node / true duplicate on the labelled set. re-index idempotence; embedding outage → lexical-only retrieval (degraded mode, not a second provider); empty index. Faithfulness (RAGAS-style) is covered by the AI evaluation doc.

## 4. Architecture decisions

| ID | Decision | Rationale |
|---|---|---|
| ADR-003 | pgvector (v1) with HNSW | One store, fewer moving parts; trigger to move at >10M vectors or p95 >100 ms |
| D-10-1 | Abbreviation lookup is exact, not vector | Deterministic, auditable (HLD §3.7) |
| D-10-2 | Append-only reference versions with maker-checker approval | Reproducibility; resolves missing write path (OQ-223) |
| D-10-3 | Batch pins reference versions at start | Consistency within a batch |

## 5. Dependencies

LLD 05 (schemas, grants), 07 (embeddings), 08 (tools), 09 (validator uses reference), 11 (approved decisions feed index), 12 (parameters, flags), 03 (dedupe blocking). Docs: `docs/ai/AI_ARCHITECTURE.md`, `docs/security/SECURITY_AND_GOVERNANCE.md`.

## 6. Risks and edge cases

| # | Case | Handling |
|---|---|---|
| E1 | Outdated taxonomy → false positives | Steward-owned, versioned, quarterly review (HLD §11.1) |
| E2 | Poisoned approved items (bad steward approval) | Only approved decisions; QA sampling; four-eyes on high impact |
| E4 | Index drift vs reference change | On-change re-index; version stored in each result |
| E5 | New category absent from taxonomy | Category suggestions limited to existing taxonomy; steward must add (HLD §11.6) |
| E6 | Retrieval returns near-duplicates that bias the model | top-k diversity not specified (OQ-228) |
| E7 | Non-English descriptions | Multilingual embedding + abbreviation dictionary; initially limited (HLD §11.6) |
| E8 | pgvector contention with OLTP | read replica; migration trigger |

## 7. Related documents

`docs/hld/HLD.md`; LLD 03, 05, 07, 08, 09, 11, 12; `docs/ai/AI_ARCHITECTURE.md`; `docs/ai/LLM_MANAGEMENT.md`; `docs/security/SECURITY_AND_GOVERNANCE.md`; `docs/testing/TESTING_AND_EVALUATION.md`; `docs/project/OPEN_QUESTIONS.md`.

### Assumptions and open questions introduced here

| ID | Text |
|---|---|
| A-211 | A batch pins all reference-data versions at batch start |
| A-212 | An `embedding_model` metadata column is needed on `item_embedding` (additive; HLD schema lacks it) |
| A-213 | Only decisions passing steward QA gating (HLD §10.9) enter `approved_items` |
| A-214 | Celery beat (or K8s CronJob) schedules nightly re-index |
| A-215 | Tool timeout returns empty result; agent may answer `unsure` |
| OQ-223 | Reference-data write path: endpoints, workflow, approval (HLD lists GET only) |
| OQ-224 | Are manufacturer aliases, abbreviations, severity policy, keyword map, calibration, forbidden terms served via the same endpoint/types? |
| OQ-225 | Which roles may edit reference data (RBAC gives Admin config only to Platform Admin; stewards "own" it) |
| OQ-226 | RESOLVED by ADR-016: reference data is global (single entity). |
| OQ-227 | BM25 implementation (Postgres FTS vs library) |
| OQ-228 | Candidate counts, fusion constant; diversity in top-k (no reranker, ADR-020) |
| OQ-229 | Do embedding-similarity candidates also feed heuristic duplicate detection? |
| OQ-230 | Exact text composition that is embedded for items and taxonomy nodes |
| OQ-231 | Governance of the "curated shared set" of examples (who curates and approves them) |
| OQ-232 | HNSW parameters and recall/latency targets for retrieval |
