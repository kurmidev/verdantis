import copy

from dqa.db.audit import GENESIS, build_event, verify_chain
from dqa.db.ids import new_id


def _chain(n=3):
    ev, prev = [], GENESIS
    for i in range(n):
        e = build_event(seq=i + 1, prev_hash=prev, actor="u", event_type="upload",
                        entity=f"batch:{i}", payload={"n": i, "z": [1, 2]})
        ev.append(e)
        prev = e["hash"]
    return ev


def test_valid_chain_verifies_and_empty_is_valid():
    assert verify_chain(_chain()) and verify_chain([])


def test_payload_tamper_detected():
    ev = copy.deepcopy(_chain())
    ev[1]["payload"]["n"] = 99
    assert not verify_chain(ev)


def test_reorder_gap_and_prev_hash_detected():
    ev = _chain()
    assert not verify_chain([ev[0], ev[2]])  # gap
    assert not verify_chain([ev[1], ev[0]])  # reorder
    bad = copy.deepcopy(ev)
    bad[2]["prev_hash"] = GENESIS
    assert not verify_chain(bad)


def test_hash_independent_of_payload_key_order():
    a = build_event(seq=1, prev_hash=GENESIS, actor="u", event_type="t", entity="e",
                    payload={"a": 1, "b": 2}, created_at="2026-01-01T00:00:00+00:00")
    b = build_event(seq=1, prev_hash=GENESIS, actor="u", event_type="t", entity="e",
                    payload={"b": 2, "a": 1}, created_at="2026-01-01T00:00:00+00:00")
    assert a["hash"] == b["hash"]


def test_new_id_prefixed_unique_sortable():
    ids = [new_id("f") for _ in range(200)]
    assert len(set(ids)) == 200 and all(i.startswith("f_") and len(i) == 28 for i in ids)
