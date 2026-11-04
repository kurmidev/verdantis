"""SqlRepo: Repo on SQLAlchemy 2.x Core. Each method is one transaction (unit of work)."""
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from dqa.db import audit
from dqa.db.common import check_fields, decode_cursor, page_cursor
from dqa.db.errors import IntegrityViolation
from dqa.db.ids import new_id
from dqa.db.schema import audit_event, batch, batch_chunk, finding, record_snapshot
from dqa.models import Finding, NormView, Record

AUDIT_LOCK_ID = 0x44514101  # pg_advisory_xact_lock key for the single global audit chain
_FIELDS = ("source_system", "item_id", "item_description", "manufacturer",
           "manufacturer_part_number", "category", "unit_of_measure")


def _now() -> datetime:
    return datetime.now(UTC)


def _ins(conn: sa.Connection, table: sa.Table) -> Any:
    mod = postgresql if conn.dialect.name == "postgresql" else sqlite
    return mod.insert(table)


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt  # SQLite drops tzinfo


def _batch_dict(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    d["batch_id"], d["object_key"] = d.pop("id"), d.pop("s3_key")
    for k in ("created_at", "updated_at", "completed_at"):
        d[k] = _utc(d[k]) if d[k] else None
    return d


def _finding(r: Any) -> Finding:
    d = dict(r._mapping)
    d.pop("severity_rank", None)
    d["finding_id"] = d.pop("id")
    d["created_at"] = _utc(d["created_at"])
    d.pop("updated_at")
    return Finding.model_validate(d)


class SqlRepo:
    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine

    # batches
    def create_batch(self, *, batch_id: str, idempotency_key: str, file_sha256: str,
                     created_by: str, object_key: str) -> tuple[str, bool]:
        now = _now()
        with self.engine.begin() as c:
            res = c.execute(_ins(c, batch).values(
                id=batch_id, idempotency_key=idempotency_key, file_sha256=file_sha256,
                s3_key=object_key, source_systems=[], status="queued", ai_status="not_started",
                created_by=created_by, created_at=now, updated_at=now,
            ).on_conflict_do_nothing().returning(batch.c.id))
            if res.first():  # rowcount is unreliable with implicit RETURNING
                return batch_id, True
            row = c.execute(sa.select(batch.c.id).where(sa.or_(
                batch.c.idempotency_key == idempotency_key,
                batch.c.file_sha256 == file_sha256))).first()
            return row[0], False  # type: ignore[index]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as c:
            r = c.execute(sa.select(batch).where(batch.c.id == batch_id)).first()
        return _batch_dict(r) if r else None

    def set_batch_status(self, batch_id: str, status: str, **fields: Any) -> None:
        check_fields(fields)
        with self.engine.begin() as c:
            res = c.execute(sa.update(batch).where(batch.c.id == batch_id)
                            .values(**fields, status=status, updated_at=_now()))
            if not res.rowcount:
                raise KeyError(batch_id)

    def list_batches(self, *, owner: str | None, limit: int = 50) -> list[dict[str, Any]]:
        q = sa.select(batch).order_by(batch.c.created_at.desc(), batch.c.id.desc()).limit(limit)
        if owner is not None:
            q = q.where(batch.c.created_by == owner)
        with self.engine.begin() as c:
            return [_batch_dict(r) for r in c.execute(q)]

    # snapshots and chunks
    def insert_snapshots(self, batch_id: str, records: Sequence[Record]) -> None:
        rows = [{
            "batch_id": batch_id, "row_number": r.row_number, "record_key": r.record_key,
            "source_system": r.source_system, "item_id": r.item_id, "raw": r.raw,
            # PROVISIONAL(OQ-126): typed fields live under normalised["fields"] to rebuild Record
            "normalised": {**r.norm.model_dump(mode="json"),
                           "fields": {k: getattr(r, k) for k in _FIELDS}},
        } for r in records]
        if not rows:
            return
        try:
            with self.engine.begin() as c:  # first write wins: snapshots are immutable
                c.execute(_ins(c, record_snapshot).on_conflict_do_nothing(
                    index_elements=["batch_id", "row_number"]), rows)
        except sa.exc.IntegrityError as e:
            raise IntegrityViolation(str(e.orig)) from e

    def get_records(self, batch_id: str, *, offset: int = 0,
                    limit: int | None = None) -> list[Record]:
        q = (sa.select(record_snapshot).where(record_snapshot.c.batch_id == batch_id)
             .order_by(record_snapshot.c.row_number).offset(offset))
        if limit is not None:
            q = q.limit(limit)
        with self.engine.begin() as c:
            out = []
            for r in c.execute(q):
                norm = dict(r.normalised)
                fields = norm.pop("fields")
                out.append(Record(row_number=r.row_number, record_key=r.record_key, raw=r.raw,
                                  norm=NormView.model_validate(norm), **fields))
            return out

    def create_chunks(self, batch_id: str, chunk_size: int, record_count: int) -> int:
        n = -(-record_count // chunk_size)
        rows = [{"batch_id": batch_id, "chunk_no": i, "row_from": (i - 1) * chunk_size + 1,
                 "row_to": min(i * chunk_size, record_count), "status": "queued"}
                for i in range(1, n + 1)]
        try:
            with self.engine.begin() as c:
                if rows:
                    c.execute(_ins(c, batch_chunk).on_conflict_do_nothing(), rows)
                res = c.execute(sa.update(batch).where(batch.c.id == batch_id).values(
                    record_count=record_count, chunk_count=n, updated_at=_now()))
                if not res.rowcount:
                    raise IntegrityViolation(f"unknown batch {batch_id}")
        except sa.exc.IntegrityError as e:
            raise IntegrityViolation(str(e.orig)) from e
        return n

    def set_chunk_status(self, batch_id: str, chunk_no: int, status: str) -> None:
        with self.engine.begin() as c:
            res = c.execute(sa.update(batch_chunk).where(
                batch_chunk.c.batch_id == batch_id, batch_chunk.c.chunk_no == chunk_no
            ).values(status=status))
            if not res.rowcount:
                raise KeyError((batch_id, chunk_no))

    def chunk_statuses(self, batch_id: str) -> dict[int, str]:
        with self.engine.begin() as c:
            rows = c.execute(sa.select(batch_chunk.c.chunk_no, batch_chunk.c.status)
                             .where(batch_chunk.c.batch_id == batch_id))
            return {n: s for n, s in rows}

    # findings
    def insert_findings(self, findings: Sequence[Finding]) -> int:
        now = _now()
        rows = [{
            "id": f.finding_id or new_id("f"), "batch_id": f.batch_id,
            "record_key": f.record_key, "item_id": f.item_id, "issue_type": f.issue_type.value,
            "severity": f.severity.value, "confidence": round(f.confidence, 3),
            "explanation": f.explanation, "evidence": f.evidence,
            "suggested_action": f.suggested_action, "suggested_value": f.suggested_value,
            "source": f.source.value, "also_detected_by": [s.value for s in f.also_detected_by],
            "rule_id": f.rule_id, "rule_version": f.rule_version, "model_id": f.model_id,
            "prompt_version": f.prompt_version, "status": f.status.value,
            "dedupe_key": f.dedupe_key, "created_at": f.created_at or now, "updated_at": now,
        } for f in findings]
        if not rows:
            return 0
        added = 0
        try:
            with self.engine.begin() as c:
                for row in rows:  # rowcount per row: executemany does not report inserted count
                    added += len(c.execute(_ins(c, finding).on_conflict_do_nothing(
                        index_elements=["dedupe_key"]).values(**row)
                        .returning(finding.c.id)).all())
        except sa.exc.IntegrityError as e:
            raise IntegrityViolation(str(e.orig)) from e
        return added

    def list_findings(self, batch_id: str, *, issue_type: str | None = None,
                      severity: str | None = None, source: str | None = None,
                      status: str | None = None, cursor: str | None = None,
                      limit: int = 50) -> tuple[list[Finding], str | None]:
        f = finding.c
        q = sa.select(finding).where(f.batch_id == batch_id)
        for col, val in ((f.issue_type, issue_type), (f.severity, severity),
                         (f.source, source), (f.status, status)):
            if val is not None:
                q = q.where(col == val)
        if cursor:  # keyset on (severity_rank desc, confidence desc, id asc)
            rank, conf, fid = decode_cursor(cursor)
            q = q.where(sa.or_(
                f.severity_rank < rank,
                sa.and_(f.severity_rank == rank, f.confidence < conf),
                sa.and_(f.severity_rank == rank, f.confidence == conf, f.id > fid)))
        q = q.order_by(f.severity_rank.desc(), f.confidence.desc(), f.id).limit(limit + 1)
        with self.engine.begin() as c:
            items = [_finding(r) for r in c.execute(q)]
        return page_cursor(items, limit)

    def get_finding(self, finding_id: str) -> Finding | None:
        with self.engine.begin() as c:
            r = c.execute(sa.select(finding).where(finding.c.id == finding_id)).first()
        return _finding(r) if r else None

    def count_findings_by_type(self, batch_id: str) -> dict[str, int]:
        with self.engine.begin() as c:
            rows = c.execute(sa.select(finding.c.issue_type, sa.func.count())
                             .where(finding.c.batch_id == batch_id)
                             .group_by(finding.c.issue_type))
            return {t: n for t, n in rows}

    # audit
    def append_audit(self, *, actor: str, event_type: str, entity: str,
                     payload: dict[str, Any]) -> None:
        with self.engine.begin() as c:
            if c.dialect.name == "postgresql":  # serialise appends; released at commit
                c.execute(sa.select(sa.func.pg_advisory_xact_lock(AUDIT_LOCK_ID)))
            last = c.execute(sa.select(audit_event.c.seq, audit_event.c.hash)
                             .order_by(audit_event.c.seq.desc()).limit(1)).first()
            ev = audit.build_event(
                seq=last.seq + 1 if last else 1, prev_hash=last.hash if last else audit.GENESIS,
                actor=actor, event_type=event_type, entity=entity, payload=payload)
            # created_at is part of the hash: store exactly what was hashed
            c.execute(audit_event.insert().values(
                **{**ev, "created_at": datetime.fromisoformat(ev["created_at"])}))

    def audit_events(self) -> list[dict[str, Any]]:
        with self.engine.begin() as c:
            rows = c.execute(sa.select(audit_event).order_by(audit_event.c.seq))
            return [{
                "seq": r.seq, "actor": r.actor, "event_type": r.event_type, "entity": r.entity,
                "payload": r.payload, "created_at": audit.utc_iso(_utc(r.created_at)),
                "prev_hash": r.prev_hash, "hash": r.hash,
            } for r in rows]
