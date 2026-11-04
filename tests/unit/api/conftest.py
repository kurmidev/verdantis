from typing import Any

import pytest
from fastapi.testclient import TestClient

from dqa.api.app import Settings, create_app
from dqa.api.store import MemoryStore
from dqa.models import Finding, IssueType, Severity, Source


class FakeRepo:
    """Minimal Repo double (dqa.db.memory.InMemoryRepo is built by another worker)."""

    def __init__(self) -> None:
        self.batches: dict[str, dict[str, Any]] = {}
        self.findings: list[Finding] = []
        self.audit: list[dict[str, Any]] = []

    def create_batch(self, *, batch_id, idempotency_key, file_sha256, created_by, object_key):
        for b in self.batches.values():
            if b["idempotency_key"] == idempotency_key or b["file_sha256"] == file_sha256:
                return b["batch_id"], False
        self.batches[batch_id] = {
            "batch_id": batch_id, "idempotency_key": idempotency_key, "file_sha256": file_sha256,
            "created_by": created_by, "object_key": object_key, "status": "queued",
            "record_count": 0, "ai_status": "not_started",
            "created_at": "2026-11-04T09:00:00Z", "completed_at": None,
        }
        return batch_id, True

    def get_batch(self, batch_id):
        return self.batches.get(batch_id)

    def list_batches(self, *, owner, limit=50):
        return list(self.batches.values())[:limit]

    def list_findings(self, batch_id, *, issue_type=None, severity=None, source=None,
                      status=None, cursor=None, limit=50):
        out = [f for f in self.findings if f.batch_id == batch_id
               and (issue_type is None or f.issue_type == issue_type)
               and (severity is None or f.severity == severity)
               and (source is None or f.source == source)
               and (status is None or f.status == status)]
        start = int(cursor or 0)
        page = out[start:start + limit]
        nxt = str(start + limit) if start + limit < len(out) else None
        return page, nxt

    def count_findings_by_type(self, batch_id):
        counts: dict[str, int] = {}
        for f in self.findings:
            if f.batch_id == batch_id:
                counts[f.issue_type.value] = counts.get(f.issue_type.value, 0) + 1
        return counts

    def append_audit(self, *, actor, event_type, entity, payload):
        self.audit.append({"actor": actor, "event_type": event_type, "entity": entity,
                           "payload": payload})


def make_finding(batch_id: str, n: int = 0, **over: Any) -> Finding:
    base: dict[str, Any] = {
        "batch_id": batch_id, "record_key": f"ERP-A:{n}", "item_id": str(n),
        "issue_type": IssueType.MISSING_PART_NUMBER, "severity": Severity.MEDIUM,
        "confidence": 1.0, "explanation": "x", "evidence": {"a": 1}, "suggested_action": "y",
        "source": Source.DETERMINISTIC_RULE, "rule_id": "r", "rule_version": "1.0.0",
        "dedupe_key": f"k{n}",
    }
    return Finding(**{**base, **over})


class Harness:
    def __init__(self) -> None:
        self.repo = FakeRepo()
        self.store = MemoryStore()
        self.queue: list[tuple[str, dict[str, Any]]] = []
        self.app = create_app(
            self.repo, self.store, lambda q, m: self.queue.append((q, m)),
            settings=Settings(auth_mode="dev_header", max_upload_bytes=1000),
        )
        self.client = TestClient(self.app)

    def hdr(self, user: str, role: str, key: str | None = None) -> dict[str, str]:
        h = {"X-Dev-User": user, "X-Dev-Roles": role}
        if key:
            h["Idempotency-Key"] = key
        return h

    def upload(self, user="u1", role="Uploader", key="k1", data=b'[{"item_id":"1"}]',
               name="a.json", ctype="application/json"):
        return self.client.post("/api/v1/batches", headers=self.hdr(user, role, key),
                                files={"file": (name, data, ctype)})


@pytest.fixture
def h() -> Harness:
    return Harness()
