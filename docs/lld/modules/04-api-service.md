# LLD 04 — API Service (FastAPI)

> **ADR-023 note (2026-11-04):** no sign-in. Every request is the `anonymous` principal with all roles except Platform Admin; role/ownership checks, four-eyes and OIDC described below are **not enforced** until a new ADR reintroduces authentication through the `Authenticator` slot. Network controls are the only access control.

**Status:** DRAFT. HLD refs: §2.4, §6.4, §4.7 (idempotency), §5.1–5.2 (authN/Z), FR-1, FR-9, FR-10, FR-11, §6.3 (edge cases), §6.8 (compatibility).
Shared models: [LLD.md](../LLD.md). Decision/export business logic lives in [module 11](11-review-workflow-and-export.md); this module owns the HTTP contract and cross-cutting behaviour.

## 1. Purpose
Expose batches, findings, decisions, exports and reference data over REST/JSON at `/api/v1`; validate and authorise every request; write work to the queue; never do long work inline.

## 2. Scope
- In: routing, request/response schemas, pagination, filtering, idempotency, error model, authZ hooks, rate-limit headers, event notification, OpenAPI.
- Out: SSO token issuance (corporate IdP), gateway rate limiting itself (API Gateway), UI (no LLD), worker logic (06).

## 3. Detailed explanation

### 3.1 Responsibilities
1. Authenticate (JWT from IdP, 15-min lifetime) and authorise each call against **role + batch ownership** (HLD 5.1).
2. Accept uploads (streaming multipart), create the `batch`, enqueue `batch_created`.
3. Serve status, paginated findings, reference data.
4. Accept decisions (single and bulk), export requests.
5. Enforce `Idempotency-Key` on all writes.
6. Emit audit events for uploads, decisions, exports.

### 3.2 Common behaviour

| Aspect | Specification |
|---|---|
| Base path | `/api/v1`; additive changes only within v1; 90-day deprecation notice (HLD 6.8) |
| Auth | `Authorization: Bearer <JWT>`; claims → `user_id`, `roles` (IdP group-to-role mapping: see OQ-401 in [Security](../../security/SECURITY_AND_GOVERNANCE.md)); expired/invalid → `401` |
| AuthZ matrix | Uploader: upload, own batches. Data Steward: upload, view all batches, decide, export. Data Owner: + second approval. Auditor: read-only incl. audit. Platform Admin: metadata only, config (HLD 5.2) |
| Resource scoping | Uploader sees only own batches; other roles see all batches. A request for a batch the caller may not see returns `404` (no existence leak) and raises a security event |
| Idempotency | header `Idempotency-Key` (required on POST); stored with request hash; replay with same key+same body → original response; same key + different body → `422 idempotency_conflict` (PROVISIONAL, OQ-110). Retention window for keys OQ-110 |
| Error body | PROVISIONAL (LLD.md §3.3): `{"error":{"code","message","details","trace_id"}}`. Codes: `unauthenticated` 401, `forbidden` 403, `not_found` 404, `validation_error` 422, `idempotency_conflict` 422, `state_conflict` 409, `rate_limited` 429 (+`Retry-After`), `payload_too_large` 413, `internal_error` 500 |
| Pagination | keyset cursor, opaque base64 of `(severity_rank, confidence, id)`; `limit` default 50, max 200 (limits OQ-118); response `{items, next_cursor}`; sort severity desc, confidence desc (HLD 6.1.7) |
| Trace | `X-Request-Id`/W3C `traceparent` accepted and returned; `trace_id` stored on batch |
| Rate limiting | API Gateway; limits/user OQ-118; API returns gateway's `429` unchanged |

### 3.3 Endpoints

#### `POST /api/v1/batches` — upload (FR-1)
Multipart: `file` (JSON/CSV). Headers: `Idempotency-Key`.
Steps: authz (Uploader/Steward/Owner) → size check (`max_upload_mb`, OQ-104) → stream to S3 `uploads/{batch_id}` while computing SHA-256 → lookup `(idempotency_key)` then `(file_sha256)`; if found return the existing `batch_id` (HLD 4.7) → pre-check (`sniff_format`, `precheck` from module 01) → in one transaction insert `batch(queued)` + `audit_event(upload)` → publish `batch_created`.
Responses:
```json
// 202 Accepted
{"batch_id":"b_01J9ZK2A7T","status":"queued"}
```
```json
// 422 Unprocessable (not JSON / bad CSV encoding; HLD 6.3)
{"error":{"code":"validation_error","message":"File could not be parsed as JSON or CSV.","details":{"line":1,"position":0,"reason":"format_unrecognised"},"trace_id":"7c1e…"}}
```
Empty file: HLD says both "202 batch_id" and "200 with zero findings, status empty" → OQ-111. PROVISIONAL: 202 with the batch ending `status=empty` (consistent with async design). >100k rows: detected by the worker → batch `failed`, `error_code=too_many_rows`; if a size-based pre-check can reject earlier → `413 payload_too_large` with guidance.

#### `GET /api/v1/batches/{id}` — status
```json
{"batch_id":"b_01J9ZK2A7T","status":"processing","records":2,
 "findings_by_type":{"missing_part_number":1,"weak_description":1,"category_mismatch_candidate":1},
 "ai_status":"running","created_at":"2026-11-04T09:00:00Z","completed_at":null}
```
Uploader may only read own batches; others see all batches.

#### `GET /api/v1/batches/{id}/findings` — list
Query: `issue_type`, `severity`, `source`, `status`, `tab` (`main` | `needs_investigation` — the low-confidence AI tab, HLD 4.9; boundary at `ai_min_confidence_display`, OQ in HLD-corrections item 5), `limit`, `cursor`.
Response `{"items":[Finding...],"next_cursor":"…"}`. Finding schema: LLD.md §3.5 (HLD-PDF 6.4 object). Example item (brief 1002 as produced by module 03):
```json
{"finding_id":"f_01J9ZK3P4R","batch_id":"b_01J9ZK2A7T","record_key":"ERP-B:1002","item_id":"1002",
 "issue_type":"category_mismatch_candidate","severity":"low","confidence":0.7,
 "explanation":"Description suggests a mechanical bearing, but category is Electrical.",
 "evidence":{"item_description":"SKF Bearing 6205 ZZ","category":"Electrical","matched_keyword":"bearing"},
 "suggested_action":"Review category assignment before approval.",
 "suggested_value":{"category":"Mechanical"},"source":"heuristic","also_detected_by":[],
 "rule_id":"category_mismatch","rule_version":"1.2.0","model_id":null,"prompt_version":null,
 "status":"needs_review","created_at":"2026-11-04T09:00:02Z"}
```

#### `POST /api/v1/findings/{id}/decisions` — decide (FR-10)
Request (HLD-PDF 6.4): `{"action":"approve|reject|investigate","reason_code":"wrong_suggestion","comment":"…","edited_value":{…}}`. `reason_code` required for reject; `edited_value` only with approve (edit-and-approve); reason-code list is OQ-133 (HLD gives only the example `wrong_suggestion`).
Response `201 {"decision_id":"d_…","finding_status":"approved"}`. Re-submitting the identical decision → same `201` body (no-op, HLD 4.7); conflicting decision on a finding no longer `needs_review` → `409 state_conflict`. Four-eyes outcome representation → OQ-131. Logic: module 11.

#### `POST /api/v1/findings/decisions:bulk` — bulk (max 500)
Gated by flag `bulk_approve_enabled` (else `403 forbidden`). Body `{"decisions":[{"finding_id","action","reason_code?","comment?"}...]}` (≤500, else `422`). Response `207 Multi-Status`:
```json
{"results":[{"finding_id":"f_1","status":201,"decision_id":"d_1","finding_status":"approved"},
            {"finding_id":"f_2","status":409,"error":{"code":"state_conflict"}}]}
```
Each item is its own transaction; one failure does not roll back others. Path note: HLD writes `/api/v1/findings/decisions:bulk` (no `{id}`).

#### `POST /api/v1/batches/{id}/exports` — export (FR-11)
Roles: Steward, Data Owner. Requires `Idempotency-Key`. Response `202 {"export_id":"x_…"}`. HLD says "→ signed URL" but defines no read endpoint; PROVISIONAL addition `GET /api/v1/exports/{export_id}` → `{"status":"queued|running|ready|failed","signed_url":"…","expires_at":"…","finding_count":n}` (OQ-132). Change-file format is OQ-134.

#### `GET /api/v1/reference-data/{type}`
Types: `allowed_uom`, `taxonomy`, `generic_terms` (+ others used by checks). Response `{"type":"allowed_uom","version":3,"effective_from":"…","values":["EA","PC",…]}`. Write path for stewards is not in the HLD (HLD-PDF 1.3 says stewards maintain it) → OQ-135; ETag/`If-None-Match` supported.

#### Notification of completion (HLD 2.4: "webhook/SSE")
PROVISIONAL: `GET /api/v1/batches/{id}/events` (SSE) emitting `batch.status_changed`, `batch.ai_status_changed`; outbound webhook registration is not specified → OQ-117.

#### Health
`GET /healthz` (liveness), `GET /readyz` (DB + queue reachable). Not versioned, unauthenticated, no batch data.

### 3.4 Internal processing (request lifecycle)
1. Gateway validates JWT and rate-limits; API re-validates signature/claims (defence in depth, HLD 5.1).
2. Dependency `current_principal` builds `{user_id, roles}`; `authorize(action, resource)` checks the matrix; resource ownership checked in SQL (`WHERE … [AND created_by=…]` for Uploader).
3. DB session opened.
4. Idempotency lookup/insert for writes.
5. Handler; commit; enqueue **after commit** using a transactional-outbox row (PROVISIONAL, §3.6) so a crash cannot leave a batch without a message.
6. Response; structured access log; metrics.

### 3.5 Database interactions

| Endpoint | Reads | Writes |
|---|---|---|
| POST batches | `batch` (idempotency/sha256) | `batch`, `audit_event`, outbox |
| GET batch | `batch`, `finding` aggregate | — |
| GET findings | `finding` (keyset index) | — |
| POST decisions | `finding` (FOR UPDATE), `decision` | `decision`, `finding.status`, `audit_event` |
| POST exports | `finding` count | `export`, `audit_event`, outbox |
| GET reference-data | `reference_data` | — |
Transactions: one per request (bulk: one per item). Isolation READ COMMITTED with row locks on `finding` for decisions.

### 3.6 Outbox (PROVISIONAL, D-04-2)
HLD has no outbox. Without it, "insert batch" then "publish" can diverge on crash. Option: `outbox(id, queue, payload, created_at, sent_at)` written in the same transaction, drained by a relay. Alternative: publish after commit and let a sweeper re-enqueue `queued` batches older than N minutes. To confirm in ADR (module 06 notes the sweeper as the minimal fallback).

### 3.7 External dependencies
S3, queue, PostgreSQL, IdP (JWKS for signature validation, cached), ticketing webhook (module 11), Unleash (flags: `bulk_approve_enabled`).

### 3.8 Error handling and retry
| Failure | Behaviour |
|---|---|
| DB unavailable | `503` with `Retry-After`; no partial writes |
| Queue publish fails after commit | outbox/sweeper retries; client still receives `202` (batch is `queued`) |
| S3 upload fails | `502`-class `internal_error`; no batch row |
| JWKS fetch fails | use cached keys until expiry; else `503` |
| Client retry | safe via `Idempotency-Key` |
Outbound calls from the API have 2 s connect / 5 s read timeouts (PROVISIONAL, HLD gives none for API).

### 3.9 Edge cases
Duplicate upload (same SHA, new key) → existing batch; same key, different file → `422 idempotency_conflict`; decision on a `withdrawn` finding → `409`; bulk with duplicate ids → second is `409`/no-op; cursor tampering → `422`; Uploader requesting another's batch → `404`; export with zero approved findings → `202` then `ready` with `finding_count=0` or `422` (OQ-134); batch `failed` → findings list returns what exists plus `error_code` in batch status.

### 3.10 Logging
JSON access log: `trace_id, user_id (hashed), route, status, latency_ms, idempotent_replay`. No request bodies, no filenames beyond extension; 5xx to Sentry with release tag.

### 3.11 Security
JWT validation (`iss`, `aud`, `exp`, signature); least-privilege role check on every route; uploads: size cap, content sniffing, antivirus scan hook (not in HLD → OQ-118 mention); CSRF protection applies only if cookie auth is used (bearer tokens assumed); strict CORS to the UI origin; response headers per HLD web-security baseline (HSTS, nosniff, frame deny); no stack traces to clients; access to a batch the caller may not see → security event and `404`.

### 3.12 Performance
Findings list p95 < 300 ms (HLD 7.8) via the keyset index `(batch_id, status, severity_rank DESC, confidence DESC, id)`; no `OFFSET`. Upload streams (no full-file buffering). Bulk 500 items must finish within an SLA TBD (OQ-118). Connection pooling per pod.

### 3.13 Test requirements
Unit: schema validation, cursor encode/decode, idempotency logic, authz matrix (table-driven per role × endpoint, HLD 7.7). Integration: upload→202→status; re-upload returns same id; empty/malformed files never 500; decisions state conflicts; bulk 207 mix; Uploader requesting another user's batch → 404. Contract tests from OpenAPI (schemathesis-style fuzz is an option). E2E (Playwright via UI per HLD 7.2) is outside this module's code but uses these contracts. DAST (ZAP) on staging.

## 4. Architecture decisions
ADR-004 FastAPI + Pydantic v2; ADR-009 PostgreSQL; ADR-005 queue. Local: D-04-1 keyset pagination; D-04-2 outbox (PROVISIONAL); D-04-3 404 for inaccessible batches.

## 5. Dependencies
[05](05-data-layer.md), [06](06-queue-and-workers.md), [11](11-review-workflow-and-export.md), [12](12-config-flags-and-prompts.md), [Security](../../security/SECURITY_AND_GOVERNANCE.md).

## 6. Risks and edge cases
Contract gaps in the HLD (export download, reference-data write, reason codes) block UI work; unauthenticated health endpoints; large multipart uploads vs gateway limits; idempotency-key table growth.

## 7. Related documents
[LLD.md](../LLD.md) · [01](01-ingestion-validator.md) · [05](05-data-layer.md) · [06](06-queue-and-workers.md) · [11](11-review-workflow-and-export.md) · [Infra](../../infra/INFRASTRUCTURE.md) · [Testing](../../testing/TESTING_AND_EVALUATION.md)

## Open questions (this module)

| ID | Question |
|---|---|
| OQ-110 | Idempotency semantics: scope (user?), key retention window, same key + different body response code, interaction with `file_sha256` uniqueness. |
| OQ-111 | Empty file: 200 vs 202; where 422 "line/position" is produced (sync pre-check vs worker). |
| OQ-117 | Completion notification: SSE vs outbound webhook vs polling only; payload and registration. |
| OQ-118 | Limits: `max_upload_mb`, rate limits, page size, bulk SLA, antivirus scanning. |
| OQ-131 | How "awaiting second approval" is represented (no state in HLD-PDF 4.10). |
| OQ-132 | Missing endpoint for retrieving the export signed URL. |
| OQ-133 | Allowed `reason_code` values. |
| OQ-134 | Change-file format/columns; zero-approved export behaviour. |
| OQ-135 | Reference-data write path and role. |
