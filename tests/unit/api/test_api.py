import hashlib

import pytest

from dqa.api.app import Settings, create_app
from dqa.api.store import MemoryStore
from tests.unit.api.conftest import Harness, make_finding

ROLES = ["Uploader", "Data Steward", "Data Owner", "Auditor", "Platform Admin"]


def test_upload_happy_path(h: Harness):
    r = h.upload()
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["batch_id"].startswith("b_")
    bid = body["batch_id"]
    assert h.store.get(f"uploads/{bid}") == b'[{"item_id":"1"}]'
    assert h.queue == [("dqa-ingest", {"type": "batch_created", "batch_id": bid})]
    assert h.repo.audit[0]["event_type"] == "upload" and h.repo.audit[0]["actor"] == "u1"
    assert h.repo.batches[bid]["file_sha256"] == hashlib.sha256(b'[{"item_id":"1"}]').hexdigest()


def test_upload_replay_returns_existing_and_enqueues_once(h: Harness):
    a = h.upload().json()["batch_id"]
    b = h.upload().json()["batch_id"]
    assert a == b and len(h.queue) == 1 and len(h.repo.audit) == 1


def test_same_file_new_key_returns_existing(h: Harness):
    a = h.upload(key="k1").json()["batch_id"]
    assert h.upload(key="k2").json()["batch_id"] == a


def test_upload_requires_idempotency_key(h: Harness):
    r = h.client.post("/api/v1/batches", headers=h.hdr("u1", "Uploader"),
                      files={"file": ("a.json", b"[]", "application/json")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_upload_too_large(h: Harness):
    r = h.upload(data=b"x" * 1001)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_upload_unrecognised_format(h: Harness):
    r = h.upload(data=b"[1]", name="a.csv", ctype="text/csv")
    assert r.status_code == 422 and r.json()["error"]["details"]["reason"] == "format_unrecognised"


def test_empty_file_accepted_provisional(h: Harness):  # PROVISIONAL(OQ-17)
    assert h.upload(data=b"").status_code == 202


def test_missing_file_is_validation_error(h: Harness):
    r = h.client.post("/api/v1/batches", headers=h.hdr("u1", "Uploader", "k"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


UPLOAD_ROLES = {"Uploader", "Data Steward", "Data Owner"}
READ_ROLES = {"Uploader", "Data Steward", "Data Owner", "Auditor"}


@pytest.mark.parametrize("role", ROLES)
def test_rbac_upload(h: Harness, role: str):
    r = h.upload(role=role, key=f"k-{role}", data=f"[{{\"item_id\":\"{role}\"}}]".encode())
    assert r.status_code == (202 if role in UPLOAD_ROLES else 403)
    if r.status_code == 403:
        assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", ROLES)
def test_rbac_findings_and_status(h: Harness, role: str):
    bid = h.upload(user="owner1", role="Data Steward").json()["batch_id"]
    h.repo.findings.append(make_finding(bid))
    f = h.client.get(f"/api/v1/batches/{bid}/findings", headers=h.hdr("someone", role))
    s = h.client.get(f"/api/v1/batches/{bid}", headers=h.hdr("someone", role))
    if role == "Uploader":  # not the owner -> 404, no existence leak
        assert f.status_code == 404 and s.status_code == 404
    elif role == "Platform Admin":  # PROVISIONAL(OQ-405): metadata only, no findings
        assert f.status_code == 403 and s.status_code == 200
    else:
        assert f.status_code == 200 and s.status_code == 200


def test_uploader_reads_own_batch(h: Harness):
    bid = h.upload(user="u1", role="Uploader").json()["batch_id"]
    assert h.client.get(f"/api/v1/batches/{bid}", headers=h.hdr("u1", "Uploader")).status_code == 200
    assert h.client.get(f"/api/v1/batches/{bid}", headers=h.hdr("u2", "Uploader")).status_code == 404


def test_unauthenticated_and_unknown_role(h: Harness):
    assert h.client.get("/api/v1/batches/b_x").status_code == 401
    r = h.client.get("/api/v1/batches/b_x", headers=h.hdr("u", "Wizard"))
    assert r.status_code == 401


def test_batch_status_body(h: Harness):
    bid = h.upload().json()["batch_id"]
    h.repo.findings.append(make_finding(bid))
    b = h.client.get(f"/api/v1/batches/{bid}", headers=h.hdr("u1", "Uploader")).json()
    assert b["batch_id"] == bid and b["status"] == "queued"
    assert b["findings_by_type"] == {"missing_part_number": 1}
    assert {"records", "ai_status", "created_at", "completed_at"} <= b.keys()


def test_unknown_batch_404(h: Harness):
    r = h.client.get("/api/v1/batches/b_nope", headers=h.hdr("s", "Data Steward"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_findings_filters_and_cursor(h: Harness):
    bid = h.upload(user="s", role="Data Steward").json()["batch_id"]
    for n in range(5):
        h.repo.findings.append(make_finding(bid, n))
    h.repo.findings.append(make_finding(bid, 9, severity="high"))
    hd = h.hdr("s", "Data Steward")
    p1 = h.client.get(f"/api/v1/batches/{bid}/findings?limit=4", headers=hd).json()
    assert len(p1["items"]) == 4 and p1["next_cursor"]
    p2 = h.client.get(f"/api/v1/batches/{bid}/findings?limit=4&cursor={p1['next_cursor']}",
                      headers=hd).json()
    assert len(p2["items"]) == 2 and p2["next_cursor"] is None
    hi = h.client.get(f"/api/v1/batches/{bid}/findings?severity=high", headers=hd).json()
    assert [i["item_id"] for i in hi["items"]] == ["9"]
    assert h.client.get(f"/api/v1/batches/{bid}/findings?limit=201", headers=hd).status_code == 422
    assert h.client.get(f"/api/v1/batches/{bid}/findings?severity=bogus", headers=hd).status_code == 422


@pytest.mark.parametrize("role", ROLES)
def test_reference_data_any_role(h: Harness, role: str):
    r = h.client.get("/api/v1/reference-data/allowed_uom", headers=h.hdr("u", role))
    assert r.status_code == 200
    assert r.json()["type"] == "allowed_uom" and "EA" in r.json()["values"]
    assert r.json()["version"] == 1


def test_reference_data_unknown_type_404(h: Harness):
    r = h.client.get("/api/v1/reference-data/nope", headers=h.hdr("u", "Auditor"))
    assert r.status_code == 404


def test_health_unauthenticated(h: Harness):
    assert h.client.get("/healthz").status_code == 200
    assert h.client.get("/readyz").status_code == 200


def test_trace_id_in_header_and_error_body(h: Harness):
    r = h.client.get("/api/v1/batches/b_x", headers={"X-Request-Id": "abc123"})
    assert r.headers["X-Request-Id"] == "abc123"
    assert r.json()["error"]["trace_id"] == "abc123"
    assert h.client.get("/healthz").headers["X-Request-Id"]


def _open_client():
    from fastapi.testclient import TestClient

    from tests.unit.api.conftest import FakeRepo
    repo = FakeRepo()
    queued: list = []
    app = create_app(repo, MemoryStore(), lambda q, m: queued.append((q, m)))  # type: ignore[arg-type]
    return TestClient(app), repo


def test_open_mode_is_default_and_needs_no_headers():
    c, repo = _open_client()
    r = c.post("/api/v1/batches", headers={"Idempotency-Key": "k"},
               files={"file": ("a.json", b'[{"item_id":"1"}]', "application/json")})
    assert r.status_code == 202
    bid = r.json()["batch_id"]
    assert c.get(f"/api/v1/batches/{bid}").status_code == 200
    assert c.get(f"/api/v1/batches/{bid}/findings").status_code == 200
    assert c.get("/api/v1/reference-data/allowed_uom").status_code == 200
    assert repo.batches[bid]["created_by"] == "anonymous"


def test_open_mode_ignores_ownership():
    c, repo = _open_client()
    repo.create_batch(batch_id="b_other", idempotency_key="x", file_sha256="y",
                      created_by="someone-else", object_key="o")
    assert c.get("/api/v1/batches/b_other").status_code == 200


def test_open_mode_logs_warning(caplog):
    with caplog.at_level("WARNING"):
        _open_client()
    assert "auth disabled: open access" in caplog.text


def test_unknown_auth_mode_rejected():
    from tests.unit.api.conftest import FakeRepo
    with pytest.raises(ValueError):
        create_app(FakeRepo(), MemoryStore(), lambda q, m: None,  # type: ignore[arg-type]
                   settings=Settings(auth_mode="bogus"))
