"""Upload via API -> worker -> findings via API, on the in-memory repo and on Postgres (if configured)."""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from dqa.api.app import Settings, create_app
from dqa.api.store import MemoryStore
from dqa.db.audit import verify_chain
from dqa.db.memory import InMemoryRepo
from dqa.db.sql import SqlRepo
from dqa.workers.core import process_batch

SAMPLE = (Path(__file__).parent.parent / "fixtures" / "brief-sample-input.json").read_bytes()
H: dict[str, str] = {}  # open access (ADR-023): no auth headers
DSN = os.environ.get("DQA_TEST_DATABASE_URL")


def _sql_repo() -> SqlRepo:
    # Tables are append-only (TRUNCATE is rejected by design), so tests use unique data instead.
    return SqlRepo(sa.create_engine(DSN))  # type: ignore[arg-type]


def _unique_sample() -> bytes:
    return SAMPLE + b" " * (int.from_bytes(os.urandom(2)) + 1)  # valid JSON, distinct sha256


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.skipif(
    not DSN, reason="DQA_TEST_DATABASE_URL not set"))])
def stack(request):
    repo = InMemoryRepo() if request.param == "memory" else _sql_repo()
    store = MemoryStore()
    queued: list[tuple[str, dict]] = []
    app = create_app(repo, store, lambda q, m: queued.append((q, m)),
                     settings=Settings())
    return TestClient(app), repo, store, queued


def test_upload_process_and_read_findings(stack):
    client, repo, store, queued = stack
    key = os.urandom(8).hex()
    r = client.post("/api/v1/batches", headers={**H, "Idempotency-Key": key},
                    files={"file": ("sample.json", _unique_sample(), "application/json")})
    assert r.status_code == 202, r.text
    batch_id = r.json()["batch_id"]
    assert queued and queued[0][0] == "dqa-ingest"

    process_batch(batch_id, repo, store)  # what the Celery task does

    b = client.get(f"/api/v1/batches/{batch_id}", headers=H).json()
    assert b["status"] == "done"
    items = client.get(f"/api/v1/batches/{batch_id}/findings", headers=H).json()["items"]
    got = {(i["item_id"], i["issue_type"]) for i in items}
    assert ("1001", "missing_part_number") in got
    assert ("1002", "category_mismatch_candidate") in got
    assert all(i["explanation"] and i["evidence"] for i in items)
    assert verify_chain(repo.audit_events())


def test_same_file_same_key_returns_existing_batch(stack):
    client, *_ = stack
    key = os.urandom(8).hex()
    body = _unique_sample()
    a = client.post("/api/v1/batches", headers={**H, "Idempotency-Key": key},
                    files={"file": ("s.json", body, "application/json")}).json()["batch_id"]
    b = client.post("/api/v1/batches", headers={**H, "Idempotency-Key": key},
                    files={"file": ("s.json", body, "application/json")}).json()["batch_id"]
    assert a == b
