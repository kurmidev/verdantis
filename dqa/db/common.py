"""Helpers shared by InMemoryRepo and SqlRepo so both order, page and shape results identically."""
import base64
import json
from typing import Any

from dqa.models import Finding

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
BATCH_FIELDS = {"record_count", "chunk_count", "ai_status", "error_code", "error_detail",
                "source_systems", "completed_at", "reference_versions", "trace_id"}


def sort_key(f: Finding) -> tuple[int, float, str]:
    """Review-queue order: severity desc, confidence desc, id asc (LLD 05 3.4)."""
    return (-SEVERITY_RANK[f.severity.value], -round(f.confidence, 3), f.finding_id or "")


def encode_cursor(rank: int, confidence: float, fid: str) -> str:
    raw = json.dumps([rank, round(confidence, 3), fid]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[int, float, str]:
    try:
        rank, conf, fid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return int(rank), float(conf), str(fid)
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise ValueError("invalid cursor") from e


def check_fields(fields: dict[str, Any]) -> None:
    bad = set(fields) - BATCH_FIELDS
    if bad:
        raise ValueError(f"unknown batch fields: {sorted(bad)}")


def page_cursor(items: list[Finding], limit: int) -> tuple[list[Finding], str | None]:
    """items fetched with limit+1; trim and build next cursor from the last returned row."""
    if len(items) <= limit:
        return items, None
    page = items[:limit]
    last = page[-1]
    return page, encode_cursor(SEVERITY_RANK[last.severity.value], last.confidence,
                               last.finding_id or "")
