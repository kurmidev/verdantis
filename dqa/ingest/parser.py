"""Streaming-friendly JSON/CSV row iterator (LLD 01 steps 2-4). Pure: bytes in, rows/issues out."""
import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

Format = Literal["json", "csv", "unknown"]
MAX_ROWS = 100_000  # PROVISIONAL(OQ-104): inclusive cap; the 100,001st row aborts with too_many_rows


@dataclass(frozen=True)
class ParsedRow:
    row_number: int  # 1-based data row (header and skipped blank lines not counted)
    raw: Any  # dict for object/CSV rows; anything else is malformed downstream
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseIssue:
    code: str  # parse_error | too_many_rows (PROVISIONAL)
    message: str
    position: int | None = None
    line: int | None = None
    column: int | None = None


def sniff_format(first_bytes: bytes, filename: str | None = None, content_type: str | None = None) -> Format:
    """Hint from extension/content type, confirmed by the first non-whitespace byte."""
    name, ctype = (filename or "").lower(), (content_type or "").lower()
    hint: Format | None = (
        "json" if name.endswith(".json") or "json" in ctype
        else "csv" if name.endswith(".csv") or "csv" in ctype
        else None
    )
    head = first_bytes.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if not head:
        return hint or "csv"
    shape: Format = "json" if head in (b"[", b"{") else "csv"
    return "unknown" if hint and hint != shape else shape


def iter_rows(data: bytes, fmt: Format, max_rows: int = MAX_ROWS) -> Iterator[ParsedRow | ParseIssue]:
    if fmt == "json":
        yield from _iter_json(data, max_rows)
    elif fmt == "csv":
        yield from _iter_csv(data, max_rows)
    else:
        yield ParseIssue("parse_error", "format_unrecognised")


def _too_many(max_rows: int) -> ParseIssue:
    return ParseIssue("too_many_rows", f"file exceeds {max_rows} rows; split the file and upload again")


def _at(text: str, pos: int) -> tuple[int, int]:
    return text.count("\n", 0, pos) + 1, pos - (text.rfind("\n", 0, pos) + 1) + 1


def _json_issue(text: str, pos: int, msg: str) -> ParseIssue:
    line, col = _at(text, pos)
    return ParseIssue("parse_error", msg, position=pos, line=line, column=col)


def _iter_json(data: bytes, max_rows: int) -> Iterator[ParsedRow | ParseIssue]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        yield ParseIssue("parse_error", "file is not valid UTF-8", position=e.start)
        return
    decoder = json.JSONDecoder()

    def skip(i: int) -> int:
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i

    i = skip(0)
    if i >= len(text):
        return
    if text[i] != "[":  # PROVISIONAL(OQ-104): only an array of rows is accepted
        yield _json_issue(text, i, "unsupported JSON shape: expected an array of objects")
        return
    i = skip(i + 1)
    if i < len(text) and text[i] == "]":
        return
    n = 0
    while True:
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError as e:
            yield _json_issue(text, e.pos, e.msg)
            return
        if n == max_rows:
            yield _too_many(max_rows)
            return
        n += 1
        yield ParsedRow(n, obj)
        i = skip(end)
        if i >= len(text):
            yield _json_issue(text, i, "unterminated array")
            return
        if text[i] == "]":
            return
        if text[i] != ",":
            yield _json_issue(text, i, "expected ',' or ']'")
            return
        i = skip(i + 1)


def _csv_row(n: int, header: list[str], cells: list[str]) -> ParsedRow:
    raw: dict[str, Any] = {}
    problems: list[str] = []
    for idx, h in enumerate(header):
        if h in raw:
            problems.append(f"duplicate_header:{h}")
            continue
        raw[h] = cells[idx] if idx < len(cells) else ""
    if len(cells) < len(header):
        problems.append("short_row")
    elif len(cells) > len(header):
        raw["_overflow"] = cells[len(header):]
        problems.append("overflow")
    return ParsedRow(n, raw, tuple(problems))


def _iter_csv(data: bytes, max_rows: int) -> Iterator[ParsedRow | ParseIssue]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        yield from _iter_csv_lines(data, max_rows)
        return
    reader = csv.reader(io.StringIO(text, newline=""))
    header: list[str] | None = None
    n = 0
    try:
        for cells in reader:
            if not cells:  # blank line
                continue
            if header is None:
                header = cells
                continue
            if n == max_rows:
                yield _too_many(max_rows)
                return
            n += 1
            yield _csv_row(n, header, cells)
    except csv.Error as e:
        yield ParseIssue("parse_error", str(e), line=reader.line_num)


def _iter_csv_lines(data: bytes, max_rows: int) -> Iterator[ParsedRow | ParseIssue]:
    # ponytail: line-wise fallback only runs for non-UTF-8 files; quoted fields spanning lines are not
    # reassembled there. Add a byte-level CSV state machine if real files need it.
    header: list[str] | None = None
    n = 0
    pos = 0
    for line_no, line in enumerate(data.split(b"\n"), start=1):
        start, pos = pos, pos + len(line) + 1
        line = line.rstrip(b"\r")
        if not line.strip():
            continue
        try:
            text = line.decode("utf-8-sig" if line_no == 1 else "utf-8")
        except UnicodeDecodeError:
            if header is None:
                yield ParseIssue("parse_error", "header line is not valid UTF-8", position=start, line=line_no)
                return
            if n == max_rows:
                yield _too_many(max_rows)
                return
            n += 1
            yield ParsedRow(n, {"_line": line_no, "_byte_position": start}, (f"decode_error:{line_no}:{start}",))
            continue
        try:
            cells = next(csv.reader([text]), [])
        except csv.Error as e:
            yield ParseIssue("parse_error", str(e), line=line_no)
            return
        if header is None:
            header = cells
            continue
        if n == max_rows:
            yield _too_many(max_rows)
            return
        n += 1
        yield _csv_row(n, header, cells)
