# LLD 01 — Ingestion & Validator

**Status:** DRAFT. HLD refs: FR-1, §2.2 (Ingestion & Validator), §6.1 steps 1–2, §6.3, §6.8, §5.3 (input scanner), §4.7 (upload idempotency).
Conventions and shared models: [LLD.md](../LLD.md).

## 1. Purpose
Turn an uploaded JSON/CSV file into immutable `record_snapshot` rows and a stream of frozen `Record` objects. Malformed or incomplete rows become **findings**; the process never crashes and never mutates input.

## 2. Scope
- In: file format detection, streaming parse, header aliasing, row validation, blank handling, normalised views (`normalize/`), suspicious-content scan, record_key assignment, snapshot persistence, chunk planning, first-stage findings (`malformed_row`, `incomplete_row`).
- Out: business rules (module 02), heuristics (03), upload HTTP handling (04), queue mechanics (06).

## 3. Detailed explanation

### 3.1 Responsibilities
1. Accept a file reference (S3 key) and `batch_id`; stream it row by row with bounded memory (up to 100k rows).
2. Map input headers/fields to the canonical seven fields (aliases from reference data).
3. Validate each row; classify as OK, `incomplete_row`, or `malformed_row`.
4. Build `Record` (raw preserved) and the normalised view `norm`.
5. Persist snapshots (immutable) and per-row findings.
6. Plan chunks of `chunk_size` rows and register them.

### 3.2 Inputs and outputs

| | Description |
|---|---|
| Input | `batch_created` message `{batch_id, s3_key, file_sha256, filename, content_type}`; reference data versions for aliases/blank markers. |
| Output | rows in `record_snapshot`; findings (`malformed_row`, `incomplete_row`); rows in `batch_chunk`; `batch.record_count`, `batch.chunk_count`, `batch.status`; messages `chunk_process` and `batch_scope_checks` on `dqa-ingest`. |

### 3.3 API/contract surface
No public endpoint of its own. The API pre-check contract (module 04) delegates two pure functions to this module: `sniff_format(first_bytes, filename, content_type) -> json|csv|unknown` and `precheck(first_chunk) -> ok | error(position, reason)`.

### 3.4 Internal processing logic (step by step)
1. **Load and mark** — worker sets `batch.status = processing`; audit `ingest_started`.
2. **Format detection** — by extension and content type, confirmed by the first non-whitespace byte (`[` → JSON array, `{` → JSON object, otherwise CSV). Mismatch → batch `failed`, `error_code = parse_error`, reason `format_unrecognised`. Accepted JSON shapes: array of objects; NDJSON/object-wrapped shapes are OQ-104.
3. **Decode** — UTF-8 with optional BOM stripped. A CSV line that cannot be decoded produces a `malformed_row` finding (byte position and line number in `evidence`) and parsing continues at the next line (HLD-PDF 6.3: "partial rows still processed where possible").
4. **Streaming parse**
   - CSV: stdlib `csv` reader; dialect (delimiter, quoting) per OQ-104; first row is the header.
   - JSON: a streaming incremental parser (library selection deferred to implementation; requirement: constant memory). Each array element is one row.
   - A running counter enforces `max_rows` (100,000). Exceeding it aborts with `error_code = too_many_rows` (PROVISIONAL), message "split the file", batch `failed`. Rows already read are kept; no further processing.
5. **Header/field aliasing** — normalise key: trim, lowercase, collapse spaces/hyphens to `_`; look up `alias_map` (`mfr_part_no → manufacturer_part_number`; further aliases OQ-104). Unknown keys stay in `raw` only (A-104). If two keys map to one field, the first in file order wins and `evidence.alias_conflict` is recorded on an `incomplete_row` finding.
6. **Row validation**
   - *Malformed* (record unusable): element not an object/row; field value of unsupported type (object/array); decode error; field longer than `max_field_length` (provisional parameter; value OQ-103); wrong column count in CSV (fewer than header → pad with blanks and flag `incomplete_row`; more → extra values dropped into `raw._overflow` and flag `malformed_row`).
   - *Incomplete* (record usable): any field in `required_fields` is blank. **Constraint from the brief:** `manufacturer_part_number` can't be in `required_fields`, otherwise record 1001 would also yield `incomplete_row`, which the brief does not expect. PROVISIONAL default `required_fields = [item_id, source_system, item_description]` (OQ-103).
   - Numbers in JSON (`"item_id": 1001`) are stringified for the typed field; the original is preserved in `raw`.
7. **`is_blank(value)`** — true for `None`, `""`, any all-whitespace string (including NBSP and other Unicode spaces), and the strings `N/A` / `null` (case-insensitive, trimmed — A-105). Other markers (`n.a.`, `none`, `-`, `NULL`) are NOT treated as blank until confirmed (OQ-103). The raw value is always kept for evidence.
8. **Normalised view** (`norm`, never overwrites raw)
   - `description_tokens`: lowercase, split on non-alphanumeric except `-`/`.` between alphanumerics (so `6205-zz` stays one token); see module 03 for use.
   - `mpn_key = normalize_mpn(mpn)`: upper-case; strip spaces, ASCII dashes, dots and Unicode dashes (U+2010–U+2015, U+2212). `6205-ZZ`, `6205 ZZ`, `6205ZZ` → `6205ZZ`.
   - `uom_key`: trim, upper-case, strip trailing `.` (alias lookup in module 02).
   - `suspicious[]`: reasons from `scan_suspicious(record)`: instruction-like phrases ("ignore previous", "system prompt"), URLs, code-like content (`<script`, backticks, `{{`), field length above `max_ai_field_length`. Pattern list is OQ-121. A non-empty list means "rule-only processing" for this record.
9. **record_key** — per LLD §3.6 (OQ-124).
10. **Persist** — buffer up to 1,000 rows; one transaction per buffer inserts `record_snapshot` (raw + normalised) and the row-level findings (`ON CONFLICT DO NOTHING` on `dedupe_key`). Resuming after a crash is therefore safe: `(batch_id, row_number)` primary key makes snapshot inserts idempotent.
11. **Empty input** — zero rows (empty file, `[]`, header only) → `batch.status = empty`, no findings, no chunks (HTTP contract OQ-111).
12. **Chunk plan** — `chunk_count = ceil(record_count / chunk_size)`; insert `batch_chunk(batch_id, chunk_no, row_from, row_to, status='queued')`; publish `chunk_process` per chunk and one `batch_scope_checks` message (module 06 / OQ-119).
13. **Finish** — update `record_count`, `chunk_count`; audit `ingest_completed`.

### 3.5 Request/response schemas
`chunk_process` message example:
```json
{"type":"chunk_process","batch_id":"b_01J9ZK2A7T","chunk_no":1,"row_from":1,"row_to":50,"trace_id":"7c1e…","attempt":1}
```
Row-level finding example (`incomplete_row`, blank `item_description`):
```json
{"issue_type":"incomplete_row","severity":"medium","confidence":1.0,"source":"deterministic_rule","rule_id":"row_validation","rule_version":"1.0.0",
 "evidence":{"row_number":17,"blank_fields":["item_description"],"raw":{"item_description":"  "}},
 "explanation":"Required field 'item_description' is blank.","suggested_action":"Request the missing value from the source owner."}
```
Severity for `malformed_row` / `incomplete_row` is not defined in the HLD (OQ-106); the values shown are PROVISIONAL.

### 3.6 Database interactions

| Op | Table | Notes |
|---|---|---|
| UPDATE | `batch` | status, counts, `error_code` (batch row updates are audited) |
| INSERT | `record_snapshot` | immutable; PK `(batch_id,row_number)` |
| INSERT | `finding` | row-level findings; `ON CONFLICT (dedupe_key) DO NOTHING` |
| INSERT | `batch_chunk` | chunk plan |
| SELECT | `reference_data` | alias map, blank markers, required fields, limits (versioned; versions stored on batch) |
| INSERT | `audit_event` | ingest start/end |
All run under the worker DB role.

### 3.7 External dependencies
Object storage (S3 read); queue (publish); PostgreSQL; reference-data service (module 10). No LLM.

### 3.8 Error handling

| Situation | Behaviour |
|---|---|
| Unknown format / whole file unparseable | batch `failed`, `parse_error`; position/reason in `error_detail`; no crash |
| Row malformed | `malformed_row` finding, row snapshotted (raw as far as readable), parsing continues |
| > `max_rows` | batch `failed`, `too_many_rows` |
| S3 read timeout | retry (§3.9), then `failed`, `timeout` |
| DB insert failure | transaction rolled back; task retried (idempotent) |
| Reference data missing | batch `failed`, `error_code = config_missing` (PROVISIONAL); alert |

### 3.9 Retry strategy
Ingest task: Celery retry on transient errors (S3, DB connection) — 3 attempts, delay re-queued (HLD-PDF 4.6 chunk-stage policy), then DLQ with reason. Parse errors are non-retryable. Resume point: highest `row_number` already in `record_snapshot` for the batch.

### 3.10 Edge cases

| Case | Handling |
|---|---|
| Duplicate header names | first wins, finding on alias conflict |
| `item_id` numeric in JSON | stringified; raw preserved |
| Mixed `\r\n` / BOM | normalised by the CSV reader / BOM strip |
| Blank-only rows | `incomplete_row` (all required blank); if the entire row is blank → `malformed_row` (PROVISIONAL, OQ-103) |
| Very long description | `malformed_row` over `max_field_length`; between `max_ai_field_length` and that → `suspicious` |
| Unicode dashes in MPN | normalised for matching only; raw shown as evidence |
| Prompt-injection text | `suspicious[]` set; later `suspicious_content` finding (module 03); rule-only processing |
| Same file re-uploaded | handled by API (same `batch_id`), not here |

### 3.11 Logging
`component=ingest`; fields: `batch_id`, `trace_id`, `rows_read`, `rows_malformed`, `rows_incomplete`, `duration_ms`, `error_code`. Never log raw field values; log `row_number` and field names only.

### 3.12 Security
Treat the file as hostile: size cap, row cap, field-length cap, no formula/macros (CSV is parsed, never evaluated), no path or URL following. Records are never passed into prompts here. Raw object is stored under a bucket-policy-protected key; read-only access.

### 3.13 Performance
Target: parse + snapshot 10k rows well inside the 30 s deterministic budget (combined with modules 02/03); memory O(buffer), not O(file). Batch inserts of 1,000 rows; COPY-style bulk insert is an implementation option. Budget split is OQ-concerned only in perf testing.

### 3.14 Test requirements
Unit (pytest + Hypothesis): `is_blank`, `normalize_mpn` (unicode dashes, spaces, case), header aliasing, row classification, `record_key` assignment incl. `#2`. Invariant: input bytes/dicts deep-equal before and after. Integration (Testcontainers Postgres): upload fixture → snapshots exist; kill worker mid-way → resume without duplicates; empty/malformed/null-heavy files → findings or empty batch, never an exception. Fixture: [brief sample](../../testing/fixtures/brief-sample-input.json) → 2 snapshots, 0 row-level findings, `record_key`s `ERP-A:1001` and `ERP-B:1002`.

## 4. Architecture decisions
ADR-009 (PostgreSQL system of record), ADR-005 (workers). Local PROVISIONAL decisions: D-01-1 streaming parse with a hard row cap; D-01-2 duplicates are NOT detected here but in the batch-scope pass (OQ-119); D-01-3 scanner runs at ingest so snapshots carry `norm.suspicious`.

## 5. Dependencies
Module 05 (tables), 06 (messages), 10 (reference data), 02/03 (consumers of `Record`/`norm`).

## 6. Risks and edge cases
Header/alias drift between ERPs; large CSV with embedded newlines; memory in JSON parsing if the chosen library is not truly streaming; unclear required fields → noisy `incomplete_row` (OQ-103).

## 7. Related documents
[LLD.md](../LLD.md) · [02](02-rule-engine.md) · [03](03-heuristic-engine.md) · [05](05-data-layer.md) · [06](06-queue-and-workers.md) · [Security](../../security/SECURITY_AND_GOVERNANCE.md) · [Testing](../../testing/TESTING_AND_EVALUATION.md)

## Open questions (this module)

| ID | Question |
|---|---|
| OQ-103 | Which fields are required vs optional; `max_field_length`, `max_ai_field_length`; extra-column policy; other blank markers (`none`, `-`); fully blank row handling. |
| OQ-104 | Full header alias list beyond `mfr_part_no`; CSV dialect/encoding rules; accepted JSON shapes (array only? NDJSON?); maximum file size in MB; exact row cap behaviour (100k inclusive?). |
| OQ-111 | HTTP contract for empty file (200 vs 202, HLD-PDF 6.3 vs 2.4) and where "422 with line/position" is produced given async parsing. |
| OQ-121 | Suspicious-content pattern list and thresholds. |
| OQ-124 | `record_key` uniqueness for duplicate `(source_system,item_id)` rows (proposed `#n` suffix). |
