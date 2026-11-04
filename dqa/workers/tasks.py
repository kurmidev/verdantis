"""Thin Celery layer over dqa.workers.core. Handlers are idempotent; duplicates are harmless."""
from collections.abc import Callable
from typing import Any

from celery import Task

from dqa.models import ErrorCode
from dqa.workers import core
from dqa.workers.celery_app import DLQ, QUEUE_INGEST, app

MAX_ATTEMPTS = 3  # HLD 4.6: chunk stage retries
MAX_COUNTDOWN = 900  # SQS max delay
# Wired at worker start: deps = (repo, store). Tests set this directly.
deps: dict[str, Any] = {}


class Transient(Exception):
    """Retryable: S3/DB/timeout/provider 5xx/429."""


def backoff(attempt: int) -> int:
    return int(min(30 * 2 ** attempt, MAX_COUNTDOWN))


@app.task(name="dqa.dead_letter")
def dead_letter(message: dict[str, Any]) -> None:  # consumed by ops replay tool
    return None


def _guard(task: Task, fn: Callable[[], Any], message: dict[str, Any]) -> Any:
    try:
        return fn()
    except (Transient, TimeoutError, ConnectionError) as e:
        if task.request.retries >= MAX_ATTEMPTS:
            return _to_dlq(message, ErrorCode.TIMEOUT, e)
        raise task.retry(exc=e, countdown=backoff(task.request.retries)) from e
    except Exception as e:  # noqa: BLE001  # non-retryable: straight to the DLQ with the reason
        return _to_dlq(message, ErrorCode.PARSE_ERROR, e)


def _to_dlq(message: dict[str, Any], code: ErrorCode, err: Exception) -> None:
    dead_letter.apply_async(
        args=[{**message, "reason_code": code.value, "last_error": str(err)[:500]}],
        queue=DLQ[QUEUE_INGEST])


@app.task(bind=True, name="dqa.batch_created", max_retries=MAX_ATTEMPTS)
def batch_created(self: Task, batch_id: str) -> Any:
    return _guard(self, lambda: core.process_batch(
        batch_id, deps["repo"], deps["store"],
        enqueue_chunk=lambda b, n: chunk_process.apply_async(args=[b, n], queue=QUEUE_INGEST)),
        {"type": "batch_created", "batch_id": batch_id})


@app.task(bind=True, name="dqa.chunk_process", max_retries=MAX_ATTEMPTS)
def chunk_process(self: Task, batch_id: str, chunk_no: int) -> Any:
    def run() -> str:
        r = core.process_chunk(batch_id, chunk_no, deps["repo"],
                               last_attempt=self.request.retries >= MAX_ATTEMPTS)
        if r == "retry":
            raise Transient(f"rule error in chunk {chunk_no}")
        return r

    return _guard(self, run,
                  {"type": "chunk_process", "batch_id": batch_id, "chunk_no": chunk_no})
