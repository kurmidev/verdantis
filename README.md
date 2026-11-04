# Data-Quality Assistant (DQA)

DQA scans uploaded item-master records (JSON/CSV from several ERPs) and produces ranked, explainable **review candidates** for a human data steward: missing part numbers, unsupported units of measure, duplicate IDs, weak descriptions, possible cross-system duplicates and category mismatches. It never changes production data; every finding ends in a human decision, and approved changes leave as a change file.

Access is **open, no sign-in** (ADR-023). Run it only on a private network.

## 1. Implementation / code changes

| Area | Path | State |
|---|---|---|
| Shared models, enums | `dqa/models.py`, `dqa/ports.py` | Done |
| Normalisation, input scanner | `dqa/normalize/` | Done |
| Ingest (JSON/CSV parser, row validation, record keys) | `dqa/ingest/` | Done |
| Deterministic rules and heuristics, rule registry, engine | `dqa/checks/` | Done |
| Repository (in-memory and PostgreSQL), audit hash chain, Alembic migration | `dqa/db/`, `migrations/` | Done |
| API: upload, batch status, findings, reference data, health | `dqa/api/` | Done (no decisions/export yet) |
| Batch/chunk processing, state machine, Celery layer | `dqa/workers/` | Done (Celery not wired to the API) |
| Steward UI (Vite + React + TypeScript) | `ui/` | Built against mocked API |
| Review workflow (decisions, export), AI layer, RAG | n/a | Not started (phases P3, P5 to P7) |

Architecture and design live in `docs/` (start at [docs/README.md](docs/README.md)); decisions are ADR-001..023 in [docs/project/ARCHITECTURE_DECISIONS.md](docs/project/ARCHITECTURE_DECISIONS.md). Architecture changes need an ADR first (see [CLAUDE.md](CLAUDE.md)). 

## 2. How to run or test it

```bash
uv sync                                   # Python 3.12+, installs backend deps

# tests
uv run pytest                             # backend; Postgres tests skip without a DSN
DQA_TEST_DATABASE_URL=postgresql+psycopg://dqa:dqa@localhost:55432/dqa_test uv run pytest
uv run ruff check . && uv run mypy dqa

# run the API (in-memory)
uv run uvicorn dqa.api.main:app --port 8000

# run the API on PostgreSQL
docker run -d --name dqa-test-pg -e POSTGRES_USER=dqa -e POSTGRES_PASSWORD=dqa \
  -e POSTGRES_DB=dqa_test -p 55432:5432 pgvector/pgvector:pg16
export DQA_DATABASE_URL=postgresql+psycopg://dqa:dqa@localhost:55432/dqa_test
uv run alembic upgrade head
uv run uvicorn dqa.api.main:app --port 8000

# UI (proxies /api to localhost:8000)
cd ui && npm install && npm run dev       # or: npm run dev:mock  (mock API, no backend)
cd ui && npm test && npm run build        # UI unit tests, production build
```

## 3. Sample input and output

Input (`tests/fixtures/brief-sample-input.json`, from the brief):

```json
[
  {"item_id": "1001", "item_description": "bearing", "manufacturer": "SKF",
   "manufacturer_part_number": "", "category": "Mechanical",
   "unit_of_measure": "EA", "source_system": "ERP-A"},
  {"item_id": "1002", "item_description": "SKF Bearing 6205 ZZ", "manufacturer": "SKF",
   "manufacturer_part_number": "6205-ZZ", "category": "Electrical",
   "unit_of_measure": "EA", "source_system": "ERP-B"}
]
```

```bash
curl -F "file=@tests/fixtures/brief-sample-input.json" -H "Idempotency-Key: k1" \
  localhost:8000/api/v1/batches                       # 202 {"batch_id": "...", "status": "queued"}
curl localhost:8000/api/v1/batches/<batch_id>/findings
```

Output produced by the current code (issue type, severity, confidence, source):

| Record | Issue | Severity | Confidence | Source |
|---|---|---|---|---|
| 1001 | `missing_part_number` | medium | 1.0 | `deterministic_rule` |
| 1001 | `weak_description` | medium | 0.9 | `heuristic` |
| 1002 | `category_mismatch_candidate` | low | 0.70 | `heuristic` |

Differences from the brief's expected output (all open questions, none hidden):
- Confidence for `missing_part_number` is 1.0 (the HLD says deterministic rules are 1.0); the brief shows 0.95 (OQ-100, a one-line change in `RULE_CONFIDENCE`).
- 1001 also gets `weak_description` ("bearing" is a single generic term under the HLD rule); the brief lists only two findings (OQ-101, OQ-222).
- `source` values differ from the brief's `ai_or_heuristic_candidate` (OQ-130).

Every finding also carries `explanation`, `evidence`, `suggested_action`, `rule_id`/`rule_version` and `status: needs_review`.

## 4. Tests added and run

Last full run (backend with Postgres): **292 passed, 1 skipped, 1 expected failure**, 96% coverage (gate 85%), ruff and strict mypy clean.

| Suite | Tests | What it covers |
|---|---|---|
| Unit: models, normalisation, scanner, registry, templates, engine | about 90 | Frozen models, part-number normalisation (`6205-ZZ`/`6205 ZZ`/`6205ZZ` equal), injection scanner, forbidden wording, deterministic ordering |
| Unit: ingest | 52 | JSON/CSV parsing, header aliases, empty/malformed/bad-encoding files never crash, 100k-row cap, record keys |
| Unit: rules and heuristics | 49 | Each rule and heuristic, the golden brief sample, 20k-record scale |
| Unit: repository, audit chain | 38 | One shared contract suite on memory and SQLite; tamper detection |
| Unit: workers | 16 | Brief sample end to end, idempotent re-runs, failing rule, DLQ routing, 10k records under 30 s |
| Unit: API | 35 | All endpoints, error bodies, open access, role matrix (header mode) |
| Integration (real PostgreSQL 16 + pgvector) | 25 | Contract suite, append-only triggers, constraints, grants, concurrent audit appends, upload to findings through API and worker |
| UI unit (Vitest) | 47 | API client incl. 207 bulk, URL-state filters, decisions, bulk, keyboard |
| UI end to end (Playwright, Chromium) | 8 | Smoke, filters surviving reload, keyboard-only use, no overflow at 320 px, axe on 4 routes |

The expected failure is `test_exact_match_mode`: it asserts exact equality with the brief's output, which is undecided (OQ-12). Not covered: Firefox/WebKit, visual regression, real broker, real backend behind the UI, per-role database logins.

## 5. Assumptions and trade-offs

- **Unknowns are recorded, not guessed.** Every assumption is `A-xx` and every open decision is `OQ-xx` in [docs/project/OPEN_QUESTIONS.md](docs/project/OPEN_QUESTIONS.md); provisional code carries a `PROVISIONAL(OQ-xxx)` comment.
- **Single entity, no tenants** (ADR-016): simpler schema, no row-level security; multi-tenancy later needs a new ADR.
- **Open access** (ADR-023): no authentication; the audit actor is always `anonymous`, and four-eyes approval cannot be enforced. Network controls are the only protection.
- **Simplified AI layer** (ADR-017 to 021): in-process access layer, one provider, two model tiers, plain Python pipeline instead of LangGraph, 2 LLM calls max per task, rule-only mode when the provider is down. Not built yet.
- **Provisional choices:** required input fields (`item_id`, `source_system`, `item_description`), RapidFuzz `token_sort_ratio` rather than `token_set_ratio` (which would pair 1001 and 1002), `record_key` `#2` suffix for duplicate ids, `dedupe_key` derivation, and the severity table beyond the three values the HLD gives.
- **Trade-offs:** batch-scope checks (duplicates) run once in memory per batch, separate from the 50-record chunks, which keeps them correct but limits batch size; uploads are processed in a background thread locally and raw files are held in memory, so there is no broker or object storage yet.

## 6. How AI tools were used

Built with Claude Code, documentation first. I had it read the HLD PDF, ask scoping questions, then write the architecture docs and ADRs before any code. After approval, work was split into independent modules and built by parallel Claude agents, each test first (failing test, code, then pytest, ruff, strict mypy), with shared interfaces fixed beforehand and provisional choices tagged with open-question ids. Results were not taken on trust: the full suite was re-run, a real PostgreSQL container was started, and an end-to-end API-worker-database test was added. AI output was corrected where it was wrong (for example a test that tried to `TRUNCATE` an append-only table). Decisions that changed the architecture were recorded as ADRs and the docs updated to match.

## 7. What I would improve next

1. Phase 3: decisions, bulk decisions, export and ticket webhook endpoints, so the UI can run against the real backend; decide what replaces four-eyes under open access.
2. Wire the API to Celery with a real broker (SQS or ElasticMQ locally), plus an outbox/sweeper for the crash window between creating a batch and enqueueing it.
3. Resolve the brief mismatches: confidence 0.95 vs 1.0, the extra `weak_description` on 1001, and the `source` labels; then make the exact-match golden test pass.
4. Build the AI layer (access layer with PII masking, task handlers, validation, RAG) and the golden-set evaluations it needs before go-live.
5. Add network or authentication protection before any shared deployment; reintroducing sign-in would go through the authenticator hook and a new ADR.
6. Hardening: UI screenshot and cross-browser tests, CSP and security headers, observability, CI pipeline, S3 object storage, load and soak tests.

## Document map
[docs/README.md](docs/README.md) is the full index: [BRD](docs/business/BRD.md), [HLD](docs/hld/HLD.md), [LLD](docs/lld/LLD.md), [AI architecture](docs/ai/AI_ARCHITECTURE.md), [security](docs/security/SECURITY_AND_GOVERNANCE.md), [testing](docs/testing/TESTING_AND_EVALUATION.md), [infrastructure](docs/infra/INFRASTRUCTURE.md), [operations](docs/operations/OBSERVABILITY_AND_OPERATIONS.md), [decisions](docs/project/ARCHITECTURE_DECISIONS.md), [plan](docs/project/IMPLEMENTATION_PLAN.md), [tasks](docs/project/TASK_BREAKDOWN.md), [risks](docs/project/RISKS_AND_DEPENDENCIES.md).
