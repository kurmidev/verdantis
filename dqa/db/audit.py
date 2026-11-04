"""Hash-chained audit events (LLD 05 3.7). Pure: storage backends call build_event under a lock."""
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

GENESIS = "0" * 64


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _hash(prev_hash: str, e: dict[str, Any]) -> str:
    body = {k: e[k] for k in ("seq", "actor", "event_type", "entity", "payload", "created_at")}
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


def build_event(*, seq: int, prev_hash: str, actor: str, event_type: str, entity: str,
                payload: dict[str, Any], created_at: str | None = None) -> dict[str, Any]:
    e: dict[str, Any] = {
        "seq": seq, "actor": actor, "event_type": event_type, "entity": entity,
        "payload": payload, "created_at": created_at or utc_iso(datetime.now(UTC)),
        "prev_hash": prev_hash,
    }
    e["hash"] = _hash(prev_hash, e)
    return e


def verify_chain(events: Sequence[dict[str, Any]]) -> bool:
    prev = GENESIS
    for i, e in enumerate(events, start=1):
        if e["seq"] != i or e["prev_hash"] != prev or e["hash"] != _hash(prev, e):
            return False
        prev = e["hash"]
    return True
