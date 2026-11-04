"""InMemoryRepo: full Repo implementation for tests and local dev (no database)."""
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from dqa.db import audit
from dqa.db.common import check_fields, decode_cursor, page_cursor, sort_key
from dqa.db.errors import IntegrityViolation
from dqa.db.ids import new_id
from dqa.models import Finding, Record


def _now() -> datetime:
    return datetime.now(UTC)


class InMemoryRepo:
    # ponytail: one global lock, fine for tests/dev; SqlRepo is the concurrent implementation
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._batches: dict[str, dict[str, Any]] = {}
        self._records: dict[str, dict[int, Record]] = {}
        self._chunks: dict[str, dict[int, str]] = {}
        self._findings: dict[str, Finding] = {}
        self._dedupe: dict[str, str] = {}
        self._audit: list[dict[str, Any]] = []

    # batches
    def create_batch(self, *, batch_id: str, idempotency_key: str, file_sha256: str,
                     created_by: str, object_key: str) -> tuple[str, bool]:
        with self._lock:
            for b in self._batches.values():
                if b["idempotency_key"] == idempotency_key or b["file_sha256"] == file_sha256:
                    return b["batch_id"], False
            now = _now()
            self._batches[batch_id] = {
                "batch_id": batch_id, "idempotency_key": idempotency_key,
                "file_sha256": file_sha256, "object_key": object_key, "status": "queued",
                "ai_status": "not_started", "record_count": None, "chunk_count": None,
                "error_code": None, "error_detail": None, "source_systems": [],
                "created_by": created_by, "created_at": now, "updated_at": now,
                "completed_at": None,
            }
            self._records[batch_id] = {}
            self._chunks[batch_id] = {}
            return batch_id, True

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._lock:
            b = self._batches.get(batch_id)
            return dict(b) if b else None

    def set_batch_status(self, batch_id: str, status: str, **fields: Any) -> None:
        check_fields(fields)
        with self._lock:
            b = self._batches.get(batch_id)
            if b is None:
                raise KeyError(batch_id)
            b.update(fields, status=status, updated_at=_now())

    def list_batches(self, *, owner: str | None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = [b for b in self._batches.values() if owner is None or b["created_by"] == owner]
            rows.sort(key=lambda b: (b["created_at"], b["batch_id"]), reverse=True)
            return [dict(b) for b in rows[:limit]]

    # snapshots and chunks
    def insert_snapshots(self, batch_id: str, records: Sequence[Record]) -> None:
        with self._lock:
            if batch_id not in self._batches:
                raise IntegrityViolation(f"unknown batch {batch_id}")
            snaps = self._records[batch_id]
            keys = {r.record_key for r in snaps.values()}
            for r in records:
                if r.row_number in snaps:
                    continue  # immutable: first write wins
                if r.record_key in keys:
                    raise IntegrityViolation(f"duplicate record_key {r.record_key}")
                snaps[r.row_number] = r
                keys.add(r.record_key)

    def get_records(self, batch_id: str, *, offset: int = 0,
                    limit: int | None = None) -> list[Record]:
        with self._lock:
            rows = [r for _, r in sorted(self._records.get(batch_id, {}).items())]
        return rows[offset:] if limit is None else rows[offset:offset + limit]

    def create_chunks(self, batch_id: str, chunk_size: int, record_count: int) -> int:
        n = -(-record_count // chunk_size)
        with self._lock:
            if batch_id not in self._batches:
                raise IntegrityViolation(f"unknown batch {batch_id}")
            for i in range(1, n + 1):
                self._chunks[batch_id].setdefault(i, "queued")
            self._batches[batch_id].update(record_count=record_count, chunk_count=n)
        return n

    def set_chunk_status(self, batch_id: str, chunk_no: int, status: str) -> None:
        with self._lock:
            if chunk_no not in self._chunks.get(batch_id, {}):
                raise KeyError((batch_id, chunk_no))
            self._chunks[batch_id][chunk_no] = status

    def chunk_statuses(self, batch_id: str) -> dict[int, str]:
        with self._lock:
            return dict(self._chunks.get(batch_id, {}))

    # findings
    def insert_findings(self, findings: Sequence[Finding]) -> int:
        added = 0
        with self._lock:
            for f in findings:  # validate first: a failed unit of work leaves nothing behind
                snaps = self._records.get(f.batch_id)
                if snaps is None or not any(r.record_key == f.record_key for r in snaps.values()):
                    raise IntegrityViolation(f"no snapshot for {f.batch_id}/{f.record_key}")
            for f in findings:
                if f.dedupe_key in self._dedupe:
                    continue
                fid = f.finding_id or new_id("f")
                stored = f.model_copy(update={"finding_id": fid,
                                              "created_at": f.created_at or _now()})
                self._findings[fid] = stored
                self._dedupe[f.dedupe_key] = fid
                added += 1
        return added

    def list_findings(self, batch_id: str, *, issue_type: str | None = None,
                      severity: str | None = None, source: str | None = None,
                      status: str | None = None, cursor: str | None = None,
                      limit: int = 50) -> tuple[list[Finding], str | None]:
        after = decode_cursor(cursor) if cursor else None
        with self._lock:
            rows = [f for f in self._findings.values() if f.batch_id == batch_id
                    and (issue_type is None or f.issue_type.value == issue_type)
                    and (severity is None or f.severity.value == severity)
                    and (source is None or f.source.value == source)
                    and (status is None or f.status.value == status)]
        rows.sort(key=sort_key)
        if after:
            a = (-after[0], -after[1], after[2])
            rows = [f for f in rows if sort_key(f) > a]
        return page_cursor(rows[:limit + 1], limit)

    def get_finding(self, finding_id: str) -> Finding | None:
        with self._lock:
            return self._findings.get(finding_id)

    def count_findings_by_type(self, batch_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        with self._lock:
            for f in self._findings.values():
                if f.batch_id == batch_id:
                    out[f.issue_type.value] = out.get(f.issue_type.value, 0) + 1
        return out

    # audit
    def append_audit(self, *, actor: str, event_type: str, entity: str,
                     payload: dict[str, Any]) -> None:
        with self._lock:
            prev = self._audit[-1] if self._audit else None
            self._audit.append(audit.build_event(
                seq=len(self._audit) + 1, prev_hash=prev["hash"] if prev else audit.GENESIS,
                actor=actor, event_type=event_type, entity=entity, payload=payload))

    def audit_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._audit]
