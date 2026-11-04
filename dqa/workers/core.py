"""Framework-free batch/chunk processing (LLD 06 3.3-3.4). Deps injected; every step idempotent."""
import logging
from collections.abc import Callable
from typing import Any, Protocol

from dqa.checks.engine import RuleError, run_checks
from dqa.ingest import ingest
from dqa.models import Context, ErrorCode, Params
from dqa.ports import Repo

log = logging.getLogger("dqa.workers")
SYSTEM = "system"


class Store(Protocol):
    def get(self, key: str) -> bytes: ...


def _ctx(batch_id: str, params: Params) -> Context:
    return Context(batch_id=batch_id, params=params)


def process_batch(batch_id: str, repo: Repo, store: Store, *, params: Params | None = None,
                  enqueue_chunk: Callable[[str, int], None] | None = None) -> str:
    """Ingest, snapshot, batch-scope checks, chunking. Without `enqueue_chunk` chunks run inline.

    Returns the batch status after this call ('processing' while chunks are outstanding).
    """
    params = params or Params()
    batch = repo.get_batch(batch_id)
    if batch is None or batch["status"] not in ("queued", "processing"):
        return batch["status"] if batch else "missing"  # duplicate delivery: no-op
    repo.set_batch_status(batch_id, "processing")
    try:
        data = store.get(batch["object_key"])
    except Exception as e:  # unreadable upload: non-retryable here, retry belongs to the task layer
        repo.set_batch_status(batch_id, "failed", error_code=ErrorCode.TIMEOUT.value
                              if isinstance(e, TimeoutError) else ErrorCode.PARSE_ERROR.value,
                              error_detail=str(e))
        raise
    res = ingest(data, batch_id, filename=batch.get("filename"))
    if res.errors and not res.records:
        repo.set_batch_status(batch_id, "failed", error_code=ErrorCode.PARSE_ERROR.value,
                              error_detail=[e.message for e in res.errors])
        _audit(repo, batch_id, "failed", 0)
        return "failed"
    repo.insert_snapshots(batch_id, res.records)
    repo.insert_findings(res.findings)
    if not res.records:
        repo.set_batch_status(batch_id, "empty", record_count=0)
        _audit(repo, batch_id, "empty", 0)
        return "empty"
    extra: dict[str, Any] = {"record_count": len(res.records)}
    if res.errors:  # rows read before the error are kept (LLD 01)
        extra["error_detail"] = [e.message for e in res.errors]
    repo.set_batch_status(batch_id, "processing", **extra)
    ctx = _ctx(batch_id, params)
    # PROVISIONAL(OQ-119): batch-scope pass runs once here, before any chunk, over all records.
    # ponytail: in-memory over the whole batch; move to indexed SQL group-by at 100k+ records.
    repo.insert_findings(run_checks(res.records, ctx, "batch"))
    n = repo.create_chunks(batch_id, params.chunk_size, len(res.records))
    log.info("batch_chunked batch_id=%s records=%d chunks=%d", batch_id, len(res.records), n)
    for chunk_no in sorted(repo.chunk_statuses(batch_id)):
        if enqueue_chunk:
            enqueue_chunk(batch_id, chunk_no)
        else:
            process_chunk(batch_id, chunk_no, repo, params=params)
    return str((repo.get_batch(batch_id) or {})["status"])


def process_chunk(batch_id: str, chunk_no: int, repo: Repo, *, params: Params | None = None,
                  last_attempt: bool = True) -> str:
    """Record-scope checks for one chunk; safe to run twice (findings dedupe by dedupe_key).

    A rule error returns 'retry' (chunk re-queued) unless `last_attempt`, then 'failed'.
    """
    params = params or Params()
    statuses = repo.chunk_statuses(batch_id)
    if chunk_no not in statuses:
        raise ValueError(f"unknown chunk {chunk_no} for {batch_id}")
    if statuses[chunk_no] == "done":
        return "done"
    repo.set_chunk_status(batch_id, chunk_no, "running")
    # chunk index = rank among the batch's chunks, so numbering base (0/1) doesn't matter
    offset = sorted(statuses).index(chunk_no) * params.chunk_size
    records = repo.get_records(batch_id, offset=offset, limit=params.chunk_size)
    errors: list[RuleError] = []
    findings = run_checks(records, _ctx(batch_id, params), "record", on_error=errors.append)
    repo.insert_findings(findings)
    status = ("failed" if last_attempt else "retry") if errors else "done"
    repo.set_chunk_status(batch_id, chunk_no, "queued" if status == "retry" else status)
    if status == "retry":  # findings of healthy rules are kept either way
        return status
    finalize_batch(batch_id, repo)
    return status


def finalize_batch(batch_id: str, repo: Repo) -> str:
    """Complete the batch once no chunk is outstanding. Idempotent; only acts on 'processing'."""
    batch = repo.get_batch(batch_id)
    if batch is None or batch["status"] != "processing":
        return batch["status"] if batch else "missing"
    chunks = repo.chunk_statuses(batch_id)
    if not chunks or any(s not in ("done", "failed") for s in chunks.values()):
        return "processing"
    failed = sorted(n for n, s in chunks.items() if s == "failed")
    if len(failed) == len(chunks):  # PROVISIONAL(OQ-139): failed only if every chunk failed
        repo.set_batch_status(batch_id, "failed", error_code=ErrorCode.PARSE_ERROR.value,
                              error_detail={"failed_chunks": failed})
        _audit(repo, batch_id, "failed", batch.get("record_count", 0))
        return "failed"
    fields: dict[str, Any] = {"error_detail": {"failed_chunks": failed}} if failed else {}
    repo.set_batch_status(batch_id, "done", **fields)  # 'ai_partial' reserved for the AI phase
    _audit(repo, batch_id, "done", batch.get("record_count", 0))
    return "done"


def _audit(repo: Repo, batch_id: str, outcome: str, records: int) -> None:
    repo.append_audit(actor=SYSTEM, event_type="batch_processed", entity=f"batch:{batch_id}",
                      payload={"outcome": outcome, "records": records,
                               "findings_by_type": repo.count_findings_by_type(batch_id)})

