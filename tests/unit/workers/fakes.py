"""Minimal in-memory Repo/Store for worker tests (dqa.db.memory may not exist yet)."""
from collections import Counter
from typing import Any

from dqa.models import Finding, Record


class FakeStore:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = files or {}

    def get(self, key: str) -> bytes:
        return self.files[key]


class FakeRepo:
    def __init__(self) -> None:
        self.batches: dict[str, dict[str, Any]] = {}
        self.records: dict[str, list[Record]] = {}
        self.chunks: dict[str, dict[int, str]] = {}
        self.findings: dict[str, Finding] = {}
        self.audit: list[dict[str, Any]] = []

    def add_batch(self, batch_id: str, object_key: str = "f") -> None:
        self.batches[batch_id] = {"id": batch_id, "status": "queued", "object_key": object_key}

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        return self.batches.get(batch_id)

    def set_batch_status(self, batch_id: str, status: str, **fields: Any) -> None:
        self.batches[batch_id].update(status=status, **fields)

    def insert_snapshots(self, batch_id: str, records: Any) -> None:
        self.records[batch_id] = list(records)

    def get_records(self, batch_id: str, *, offset: int = 0, limit: int | None = None) -> list[Record]:
        recs = self.records.get(batch_id, [])
        return recs[offset:offset + limit] if limit else recs[offset:]

    def create_chunks(self, batch_id: str, chunk_size: int, record_count: int) -> int:
        n = -(-record_count // chunk_size)
        self.chunks[batch_id] = {i: "queued" for i in range(n)}
        return n

    def set_chunk_status(self, batch_id: str, chunk_no: int, status: str) -> None:
        self.chunks[batch_id][chunk_no] = status

    def chunk_statuses(self, batch_id: str) -> dict[int, str]:
        return dict(self.chunks.get(batch_id, {}))

    def insert_findings(self, findings: Any) -> int:
        new = [f for f in findings if f.dedupe_key not in self.findings]
        self.findings.update({f.dedupe_key: f for f in new})
        return len(new)

    def count_findings_by_type(self, batch_id: str) -> dict[str, int]:
        return dict(Counter(f.issue_type.value for f in self.findings.values()
                            if f.batch_id == batch_id))

    def append_audit(self, *, actor: str, event_type: str, entity: str,
                     payload: dict[str, Any]) -> None:
        self.audit.append({"actor": actor, "event_type": event_type, "entity": entity,
                           "payload": payload})
