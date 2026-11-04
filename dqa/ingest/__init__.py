"""Ingestion: bytes -> frozen Records + row-level findings (LLD 01). Never raises on bad input."""
from dataclasses import dataclass

from dqa.ingest.keys import KeyAssigner
from dqa.ingest.parser import ParseIssue, iter_rows, sniff_format
from dqa.ingest.validate import IngestConfig, validate_row
from dqa.models import Finding, Record

__all__ = ["IngestConfig", "IngestError", "IngestResult", "ingest"]


@dataclass(frozen=True)
class IngestError:
    code: str  # parse_error | too_many_rows (PROVISIONAL)
    message: str
    position: int | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class IngestResult:
    records: tuple[Record, ...] = ()
    findings: tuple[Finding, ...] = ()
    errors: tuple[IngestError, ...] = ()


def ingest(
    data: bytes,
    batch_id: str,
    filename: str | None = None,
    content_type: str | None = None,
    config: IngestConfig | None = None,
) -> IngestResult:
    config = config or IngestConfig()
    fmt = sniff_format(data[:4096], filename, content_type)
    keys = KeyAssigner()
    records: list[Record] = []
    findings: list[Finding] = []
    errors: list[IngestError] = []
    for item in iter_rows(data, fmt, config.max_rows):
        if isinstance(item, ParseIssue):
            errors.append(IngestError(item.code, item.message, item.position, item.line, item.column))
            break  # rows read so far are kept
        rec, row_findings = validate_row(item, keys, batch_id, config)
        records.append(rec)
        findings.extend(row_findings)
    return IngestResult(tuple(records), tuple(findings), tuple(errors))
