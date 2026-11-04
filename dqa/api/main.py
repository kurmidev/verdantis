"""Local runner: `uv run uvicorn dqa.api.main:app --port 8000`.

DQA_DATABASE_URL set -> PostgreSQL (run `uv run alembic upgrade head` first); unset -> in-memory.
Uploads are processed in a background thread, so no broker is needed locally (Celery wiring is P3).
"""
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import sqlalchemy as sa

from dqa.api.app import Settings, create_app
from dqa.api.store import MemoryStore
from dqa.db.memory import InMemoryRepo
from dqa.db.sql import SqlRepo
from dqa.ports import Repo
from dqa.workers.core import process_batch


def build() -> Any:
    url = os.environ.get("DQA_DATABASE_URL")
    repo: Repo = SqlRepo(sa.create_engine(url)) if url else InMemoryRepo()
    store = MemoryStore()  # PROVISIONAL: local only; S3 store comes with deployment
    pool = ThreadPoolExecutor(max_workers=2)

    def enqueue(queue: str, message: dict[str, Any]) -> None:
        if queue == "dqa-ingest":
            pool.submit(process_batch, message["batch_id"], repo, store)

    return create_app(repo, store, enqueue, settings=Settings())  # open access (ADR-023)


app = build()
