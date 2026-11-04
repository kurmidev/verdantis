"""Repo contract suite: every Repo implementation must pass it (memory, SQLite, Postgres)."""
import threading
import time
from typing import Any

import pytest

from dqa.db.audit import verify_chain
from dqa.db.errors import IntegrityViolation
from dqa.models import Finding, IssueType, NormView, Record, Severity, Source

B = "b_1"


def rec(n: int, system: str = "ERP-A", **over: Any) -> Record:
    raw = {"item_id": str(n), "item_description": f"bearing {n}", "source_system": system}
    base: dict[str, Any] = {
        "row_number": n, "record_key": f"{system}:{n}", "source_system": system,
        "item_id": str(n), "item_description": f"bearing {n}", "manufacturer": "SKF",
        "raw": raw, "norm": NormView(description_tokens=("bearing", str(n)), mpn_key=None),
    }
    return Record(**{**base, **over})


def fnd(n: int, *, sev: Severity = Severity.MEDIUM, conf: float = 1.0,
        issue: IssueType = IssueType.MISSING_PART_NUMBER, source: Source = Source.HEURISTIC,
        key: str | None = None, batch: str = B, **over: Any) -> Finding:
    base: dict[str, Any] = {
        "batch_id": batch, "record_key": f"ERP-A:{n}", "item_id": str(n), "issue_type": issue,
        "severity": sev, "confidence": conf, "explanation": "x", "evidence": {"k": "v"},
        "suggested_action": "y", "source": source, "rule_id": "r", "rule_version": "1.0.0",
        "dedupe_key": key or f"dk-{batch}-{n}-{issue.value}-{sev.value}-{conf}",
    }
    return Finding(**{**base, **over})


class RepoContract:
    concurrent = True

    def make(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def batch(self, repo: Any, bid: str = B, key: str = "k1", sha: str = "a" * 64,
              by: str = "u1") -> str:
        return repo.create_batch(batch_id=bid, idempotency_key=key, file_sha256=sha,
                                 created_by=by, object_key=f"raw/{bid}")[0]

    def seeded(self, n: int = 5) -> Any:
        repo = self.make()
        self.batch(repo)
        repo.insert_snapshots(B, [rec(i) for i in range(1, n + 1)])
        return repo

    # batches
    def test_create_batch_idempotent_by_key_and_sha(self):
        repo = self.make()
        assert repo.create_batch(batch_id="b_1", idempotency_key="k", file_sha256="a" * 64,
                                 created_by="u", object_key="o") == ("b_1", True)
        assert repo.create_batch(batch_id="b_2", idempotency_key="k", file_sha256="b" * 64,
                                 created_by="u", object_key="o") == ("b_1", False)
        assert repo.create_batch(batch_id="b_3", idempotency_key="k3", file_sha256="a" * 64,
                                 created_by="u", object_key="o") == ("b_1", False)
        assert repo.get_batch("b_2") is None and repo.get_batch("b_3") is None

    def test_batch_defaults_and_status_update(self):
        repo = self.make()
        self.batch(repo)
        b = repo.get_batch(B)
        assert (b["status"], b["ai_status"], b["created_by"], b["object_key"]) == (
            "queued", "not_started", "u1", "raw/b_1")
        assert b["record_count"] is None and b["completed_at"] is None and b["created_at"]
        repo.set_batch_status(B, "failed", error_code="parse_error", record_count=0)
        b = repo.get_batch(B)
        assert (b["status"], b["error_code"], b["record_count"]) == ("failed", "parse_error", 0)

    def test_set_batch_status_rejects_unknown_batch_and_field(self):
        repo = self.make()
        with pytest.raises(KeyError):
            repo.set_batch_status("nope", "done")
        self.batch(repo)
        with pytest.raises(ValueError):
            repo.set_batch_status(B, "done", id="x")

    def test_list_batches_owner_filter_newest_first_limit(self):
        repo = self.make()
        self.batch(repo, "b_1", "k1", "1" * 64, "u1")
        time.sleep(0.002)
        self.batch(repo, "b_2", "k2", "2" * 64, "u2")
        time.sleep(0.002)
        self.batch(repo, "b_3", "k3", "3" * 64, "u1")
        assert [b["batch_id"] for b in repo.list_batches(owner=None)] == ["b_3", "b_2", "b_1"]
        assert [b["batch_id"] for b in repo.list_batches(owner="u1")] == ["b_3", "b_1"]
        assert len(repo.list_batches(owner=None, limit=2)) == 2

    # snapshots and chunks
    def test_snapshots_roundtrip_ordered_paged(self):
        repo = self.make()
        self.batch(repo)
        recs = [rec(i) for i in (3, 1, 2)]
        repo.insert_snapshots(B, recs)
        got = repo.get_records(B)
        assert got == sorted(recs, key=lambda r: r.row_number)
        assert [r.row_number for r in repo.get_records(B, offset=1, limit=1)] == [2]
        assert [r.row_number for r in repo.get_records(B, offset=1)] == [2, 3]

    def test_snapshots_immutable_and_idempotent(self):
        repo = self.make()
        self.batch(repo)
        repo.insert_snapshots(B, [rec(1)])
        repo.insert_snapshots(B, [rec(1, manufacturer="CHANGED")])
        assert repo.get_records(B)[0].manufacturer == "SKF"

    def test_snapshots_need_batch_and_unique_record_key(self):
        repo = self.make()
        with pytest.raises(IntegrityViolation):
            repo.insert_snapshots("nope", [rec(1)])
        self.batch(repo)
        with pytest.raises(IntegrityViolation):
            repo.insert_snapshots(B, [rec(1), rec(2, record_key="ERP-A:1")])

    def test_chunks(self):
        repo = self.seeded()
        assert repo.create_chunks(B, 50, 120) == 3
        assert repo.chunk_statuses(B) == {1: "queued", 2: "queued", 3: "queued"}
        assert repo.create_chunks(B, 50, 120) == 3  # idempotent
        repo.set_chunk_status(B, 2, "done")
        assert repo.chunk_statuses(B)[2] == "done"
        b = repo.get_batch(B)
        assert (b["record_count"], b["chunk_count"]) == (120, 3)
        with pytest.raises(KeyError):
            repo.set_chunk_status(B, 9, "done")

    def test_zero_records_zero_chunks_and_unknown_batch(self):
        repo = self.seeded()
        assert repo.create_chunks(B, 50, 0) == 0 and repo.chunk_statuses(B) == {}
        with pytest.raises(IntegrityViolation):
            repo.create_chunks("nope", 50, 10)

    # findings
    def test_insert_findings_idempotent_and_roundtrip(self):
        repo = self.seeded()
        f = fnd(1, sev=Severity.HIGH, conf=0.7, evidence={"a": [1, 2], "b": {"c": None}},
                suggested_value={"category": "Mechanical"}, also_detected_by=(Source.AI_SUGGESTION,))
        assert repo.insert_findings([f, fnd(2)]) == 2
        assert repo.insert_findings([f, fnd(2)]) == 0
        assert repo.insert_findings([]) == 0
        got, _ = repo.list_findings(B, issue_type="missing_part_number", severity="high")
        assert len(got) == 1 and got[0].finding_id.startswith("f_") and got[0].created_at
        stored = got[0]
        assert stored.model_copy(update={"finding_id": None, "created_at": None}) == f
        assert repo.get_finding(stored.finding_id) == stored
        assert repo.get_finding("f_nope") is None

    def test_findings_need_snapshot(self):
        repo = self.seeded(1)
        with pytest.raises(IntegrityViolation):
            repo.insert_findings([fnd(1), fnd(99)])
        assert repo.insert_findings([fnd(1)]) == 1  # failed unit of work left nothing behind

    def test_findings_order_filters_and_cursor_paging(self):
        repo = self.seeded(6)
        repo.insert_findings([
            fnd(1, sev=Severity.LOW, conf=0.9), fnd(2, sev=Severity.HIGH, conf=0.5),
            fnd(3, sev=Severity.HIGH, conf=0.9), fnd(4, sev=Severity.MEDIUM, conf=1.0),
            fnd(5, sev=Severity.MEDIUM, conf=1.0, issue=IssueType.WEAK_DESCRIPTION,
                source=Source.DETERMINISTIC_RULE),
            fnd(6, sev=Severity.MEDIUM, conf=0.8)])
        full, nxt = repo.list_findings(B, limit=50)
        assert nxt is None
        assert [(f.severity.value, f.confidence) for f in full] == [
            ("high", 0.9), ("high", 0.5), ("medium", 1.0), ("medium", 1.0), ("medium", 0.8),
            ("low", 0.9)]
        ties = [f.finding_id for f in full if f.severity is Severity.MEDIUM and f.confidence == 1.0]
        assert ties == sorted(ties)
        seen, cursor = [], None
        while True:
            page, cursor = repo.list_findings(B, limit=2, cursor=cursor)
            seen += [f.finding_id for f in page]
            if cursor is None:
                break
        assert seen == [f.finding_id for f in full]
        assert len(repo.list_findings(B, issue_type="weak_description")[0]) == 1
        assert len(repo.list_findings(B, source="deterministic_rule")[0]) == 1
        assert len(repo.list_findings(B, status="needs_review")[0]) == 6
        assert repo.list_findings(B, status="approved") == ([], None)
        assert repo.list_findings("other") == ([], None)

    def test_exact_page_boundary_has_no_next_cursor(self):
        repo = self.seeded(4)
        repo.insert_findings([fnd(i) for i in range(1, 5)])
        page, cursor = repo.list_findings(B, limit=4)
        assert len(page) == 4 and cursor is None

    def test_invalid_cursor(self):
        repo = self.seeded(1)
        with pytest.raises(ValueError):
            repo.list_findings(B, cursor="!!notacursor")

    def test_count_findings_by_type(self):
        repo = self.seeded(3)
        repo.insert_findings([fnd(1), fnd(2), fnd(3, issue=IssueType.WEAK_DESCRIPTION)])
        assert repo.count_findings_by_type(B) == {"missing_part_number": 2, "weak_description": 1}
        assert repo.count_findings_by_type("other") == {}

    # audit
    def test_audit_chain_gapless_and_valid(self):
        repo = self.make()
        for i in range(3):
            repo.append_audit(actor="u", event_type="upload", entity=f"batch:{i}",
                              payload={"i": i, "nested": {"z": [1.5, None, "é"]}})
        ev = repo.audit_events()
        assert [e["seq"] for e in ev] == [1, 2, 3] and verify_chain(ev)
        ev[1]["payload"]["i"] = 99
        assert not verify_chain(ev)

    def test_concurrent_audit_appends_keep_chain_valid(self):
        if not self.concurrent:
            pytest.skip("backend not safe for concurrent writers")
        repo = self.make()
        ts = [threading.Thread(target=lambda i=i: [repo.append_audit(
            actor="u", event_type="t", entity=f"e{i}", payload={"j": j}) for j in range(5)])
            for i in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        ev = repo.audit_events()
        assert len(ev) == 20 and verify_chain(ev)
