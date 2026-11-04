import json
import time
from pathlib import Path

import pytest

from dqa.checks import registry
from dqa.models import IssueType, Params
from dqa.workers.core import finalize_batch, process_batch, process_chunk
from tests.unit.workers.fakes import FakeRepo, FakeStore

BRIEF = (Path(__file__).parents[2] / "fixtures" / "brief-sample-input.json").read_bytes()


def run(data: bytes, **kw):
    repo, store = FakeRepo(), FakeStore({"f": data})
    repo.add_batch("b1")
    return repo, process_batch("b1", repo, store, **kw)


def test_brief_sample_end_to_end():
    repo, status = run(BRIEF)
    kinds = {(f.record_key, f.issue_type) for f in repo.findings.values()}
    assert status == "done" and repo.batches["b1"]["record_count"] == 2
    assert ("ERP-A:1001", IssueType.MISSING_PART_NUMBER) in kinds
    assert ("ERP-B:1002", IssueType.CATEGORY_MISMATCH_CANDIDATE) in kinds
    assert repo.audit[-1]["event_type"] == "batch_processed"


@pytest.mark.parametrize("data", [b"", b"[]"])
def test_empty_file_is_empty_with_no_findings(data):
    repo, status = run(data)
    assert status in ("empty", "failed") and not repo.findings
    if data == b"[]":
        assert status == "empty"


@pytest.mark.parametrize("data", [b"not json {{", b"\xff\xfe\x00", b'[{"item_id": 1}, 5, null]'])
def test_malformed_never_crashes(data):
    _repo, status = run(data)
    assert status in ("done", "failed", "empty")


def test_rerun_is_idempotent():
    repo, _ = run(BRIEF)
    before = len(repo.findings)
    process_chunk("b1", 0, repo)
    assert process_batch("b1", repo, FakeStore({"f": BRIEF})) == "done"
    assert len(repo.findings) == before


def test_chunk_twice_no_duplicates_and_batch_waits_for_all_chunks():
    repo, store = FakeRepo(), FakeStore({"f": json.dumps(
        [{"item_id": str(i), "source_system": "S", "item_description": "SKF Bearing 6205 ZZ",
          "manufacturer": "SKF", "manufacturer_part_number": "", "category": "Mechanical",
          "unit_of_measure": "EA"} for i in range(5)]).encode()})
    repo.add_batch("b1")
    queued: list[tuple[str, int]] = []
    p = Params(chunk_size=2)
    assert process_batch("b1", repo, store, params=p,
                         enqueue_chunk=lambda b, n: queued.append((b, n))) == "processing"
    assert len(queued) == 3
    process_chunk("b1", 0, repo, params=p)
    process_chunk("b1", 0, repo, params=p)
    n = len(repo.findings)
    process_chunk("b1", 0, repo, params=p)
    assert len(repo.findings) == n and repo.batches["b1"]["status"] == "processing"
    process_chunk("b1", 1, repo, params=p)
    assert finalize_batch("b1", repo) == "processing"
    process_chunk("b1", 2, repo, params=p)
    assert repo.batches["b1"]["status"] == "done"
    assert len(repo.audit) == 1  # finalised exactly once


def test_failing_rule_retries_then_fails_chunk_keeping_healthy_findings():
    saved = dict(registry._REGISTRY)

    @registry.rule("boom", "1.0.0", IssueType.WEAK_DESCRIPTION, layer="heuristic", scope="record")
    def boom(records, ctx):
        raise RuntimeError("x")

    try:
        repo, store = FakeRepo(), FakeStore({"f": BRIEF})
        repo.add_batch("b1")
        process_batch("b1", repo, store, enqueue_chunk=lambda b, n: None)
        assert process_chunk("b1", 0, repo, last_attempt=False) == "retry"
        assert repo.chunks["b1"][0] == "queued" and repo.batches["b1"]["status"] == "processing"
        assert process_chunk("b1", 0, repo) == "failed"
        assert repo.batches["b1"]["status"] == "failed"  # only chunk failed (OQ-139)
        assert repo.findings  # healthy rules' findings kept
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


def test_unreadable_upload_marks_failed_and_raises():
    repo = FakeRepo()
    repo.add_batch("b1", "missing")
    with pytest.raises(KeyError):
        process_batch("b1", repo, FakeStore())
    assert repo.batches["b1"]["status"] == "failed"


def test_10k_records_under_30s():
    rows = [{"item_id": str(i), "source_system": "ERP-A", "item_description": f"widget {i} size {i % 7}mm",
             "manufacturer": f"M{i % 50}", "manufacturer_part_number": f"P-{i}", "category": "Mechanical",
             "unit_of_measure": "EA"} for i in range(10_000)]
    t = time.perf_counter()
    _repo, status = run(json.dumps(rows).encode())
    assert status == "done" and time.perf_counter() - t < 30
