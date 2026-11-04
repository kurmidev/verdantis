from pathlib import Path

import pytest

from dqa.ingest.parser import ParsedRow, ParseIssue, iter_rows, sniff_format

SAMPLE = (Path(__file__).parent.parent.parent / "fixtures" / "brief-sample-input.json").read_bytes()


def rows(data, fmt, **kw):
    return list(iter_rows(data, fmt, **kw))


@pytest.mark.parametrize(
    "head,name,ctype,exp",
    [
        (b'[{"a":1}]', "x.json", None, "json"),
        (b'\xef\xbb\xbf  [', None, "application/json", "json"),
        (b"a,b\n1,2", "x.csv", None, "csv"),
        (b"a,b\n1,2", None, "text/csv", "csv"),
        (b"a,b\n1,2", None, None, "csv"),
        (b'[{"a":1}]', None, None, "json"),
        (b'[{"a":1}]', "x.csv", None, "unknown"),
        (b"a,b\n1,2", "x.json", None, "unknown"),
        (b"", "x.json", None, "json"),
    ],
)
def test_sniff_format(head, name, ctype, exp):
    assert sniff_format(head, name, ctype) == exp


def test_json_brief_sample_two_rows():
    out = rows(SAMPLE, "json")
    assert [r.row_number for r in out] == [1, 2]
    assert all(isinstance(r, ParsedRow) for r in out)
    assert out[0].raw["item_id"] == "1001"


@pytest.mark.parametrize("data", [b"", b"  \n", b"[]", b" [ ] "])
def test_json_empty_inputs_yield_nothing(data):
    assert rows(data, "json") == []


def test_csv_header_only_and_empty_yield_nothing():
    assert rows(b"", "csv") == []
    assert rows(b"a,b\n", "csv") == []
    assert rows(b"a,b\n\n\n", "csv") == []


def test_json_broken_after_first_row_keeps_partial_rows_and_reports_position():
    out = rows(b'[{"a": 1}, {"a": ', "json")
    assert isinstance(out[0], ParsedRow) and out[0].raw == {"a": 1}
    issue = out[-1]
    assert isinstance(issue, ParseIssue) and issue.code == "parse_error"
    assert issue.position is not None and issue.line == 1


def test_json_not_an_array_is_unsupported_shape():
    (issue,) = rows(b'{"a": 1}', "json")
    assert isinstance(issue, ParseIssue) and issue.code == "parse_error"


def test_json_bad_utf8_is_parse_error():
    (issue,) = rows(b'[{"a": "\xff"}]', "json")
    assert isinstance(issue, ParseIssue) and issue.code == "parse_error" and issue.position == 8


def test_json_non_object_elements_are_still_rows():
    out = rows(b'[1, "x", null]', "json")
    assert [r.raw for r in out] == [1, "x", None]


def test_row_cap_keeps_rows_then_too_many_rows():
    out = rows(b"a\n1\n2\n3\n4\n", "csv", max_rows=3)
    assert [type(o) for o in out] == [ParsedRow] * 3 + [ParseIssue]
    assert out[-1].code == "too_many_rows" and "split" in out[-1].message


def test_row_cap_exactly_at_limit_is_fine():
    assert all(isinstance(o, ParsedRow) for o in rows(b"a\n1\n2\n", "csv", max_rows=2))


def test_csv_bom_and_crlf_and_embedded_newline():
    out = rows(b'\xef\xbb\xbfa,b\r\n"x\ny",2\r\n', "csv")
    assert out[0].raw == {"a": "x\ny", "b": "2"}


def test_csv_short_row_padded_and_flagged():
    (r,) = rows(b"a,b,c\n1,2\n", "csv")
    assert r.raw == {"a": "1", "b": "2", "c": ""} and "short_row" in r.problems


def test_csv_long_row_overflow_flagged():
    (r,) = rows(b"a,b\n1,2,3,4\n", "csv")
    assert r.raw["_overflow"] == ["3", "4"] and "overflow" in r.problems


def test_csv_duplicate_header_first_wins_and_flagged():
    (r,) = rows(b"a,a\n1,2\n", "csv")
    assert r.raw == {"a": "1"} and "duplicate_header:a" in r.problems


def test_csv_undecodable_line_becomes_decode_error_row_and_parsing_continues():
    out = rows(b"a,b\n1,2\n3,\xff\n5,6\n", "csv")
    assert [o.raw for o in out if "decode_error" not in "".join(o.problems)] == [
        {"a": "1", "b": "2"}, {"a": "5", "b": "6"}]
    bad = out[1]
    assert bad.row_number == 2 and bad.problems[0].startswith("decode_error:3:")
