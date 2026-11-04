import pytest

from dqa.workers import tasks
from dqa.workers.celery_app import app
from tests.unit.workers.fakes import FakeRepo, FakeStore
from tests.unit.workers.test_core import BRIEF


@pytest.fixture
def eager():
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    repo = FakeRepo()
    tasks.deps.update(repo=repo, store=FakeStore({"f": BRIEF}))
    repo.add_batch("b1")
    yield repo
    tasks.deps.clear()
    app.conf.task_always_eager = False


def test_batch_created_flows_to_done(eager):
    tasks.batch_created.delay("b1")
    assert eager.batches["b1"]["status"] == "done" and eager.findings


def test_duplicate_delivery_is_noop(eager):
    tasks.batch_created.delay("b1")
    n = len(eager.findings)
    tasks.batch_created.delay("b1")
    assert len(eager.findings) == n and len(eager.audit) == 1


def test_non_retryable_goes_to_dlq(eager, monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.dead_letter, "apply_async", lambda **kw: sent.append(kw))
    eager.batches["b1"]["object_key"] = "nope"
    tasks.batch_created.delay("b1")
    assert sent[0]["queue"] == "dqa-ingest-dlq"
    assert sent[0]["args"][0]["reason_code"] == "parse_error"


def test_backoff_capped():
    assert [tasks.backoff(n) for n in (0, 1, 2, 9)] == [30, 60, 120, 900]


def test_config_matches_lld():
    c = app.conf
    assert c.task_acks_late and c.task_reject_on_worker_lost and c.worker_prefetch_multiplier == 1
    assert c.broker_transport_options["visibility_timeout"] > c.task_time_limit
    assert {q.name for q in c.task_queues} >= {"dqa-ingest", "dqa-ai-tasks", "dqa-export",
                                               "dqa-ingest-dlq"}
