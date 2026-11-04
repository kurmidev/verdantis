"""Celery app (LLD 06 3.1, 3.5). No result backend: state lives in Postgres."""
import os

from celery import Celery
from kombu.entity import Queue

QUEUE_INGEST, QUEUE_AI, QUEUE_EXPORT = "dqa-ingest", "dqa-ai-tasks", "dqa-export"
# PROVISIONAL(OQ-139): DLQs are broker redrive targets in prod; local dead-letter is a queue too.
DLQ = {q: f"{q}-dlq" for q in (QUEUE_INGEST, QUEUE_AI, QUEUE_EXPORT)}
CHUNK_SOFT_LIMIT, CHUNK_HARD_LIMIT = 270, 300  # HLD 4.6: chunk stage 5 min
VISIBILITY_TIMEOUT = 2 * CHUNK_HARD_LIMIT  # must exceed max task time (HLD 8.5)

app = Celery("dqa")
app.conf.update(
    broker_url=os.environ.get("DQA_BROKER_URL", "memory://"),  # sqs:// prod, ElasticMQ/Redis local
    task_queues=[Queue(q) for q in (*DLQ, *DLQ.values())],
    task_default_queue=QUEUE_INGEST,
    task_routes={"dqa.dead_letter": {"queue": DLQ[QUEUE_INGEST]}},
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=CHUNK_SOFT_LIMIT,
    task_time_limit=CHUNK_HARD_LIMIT,
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT},
)
