from dqa.ingest.keys import KeyAssigner


def test_first_occurrence_has_no_suffix_and_duplicates_get_numbered():
    k = KeyAssigner()
    assert k.assign(1, "ERP-A", "1001") == "ERP-A:1001"
    assert k.assign(2, "ERP-B", "1001") == "ERP-B:1001"
    assert k.assign(3, "ERP-A", "1001") == "ERP-A:1001#2"
    assert k.assign(4, "ERP-A", "1001") == "ERP-A:1001#3"


def test_blank_key_parts_fall_back_to_row_number():
    k = KeyAssigner()
    assert k.assign(7, None, "1") == "row:7"
    assert k.assign(8, "ERP-A", "  ") == "row:8"
    assert k.assign(9, "N/A", "1") == "row:9"


def test_surrounding_whitespace_is_stripped():
    k = KeyAssigner()
    assert k.assign(1, " ERP-A ", " 1001 ") == "ERP-A:1001"
    assert k.assign(2, "ERP-A", "1001") == "ERP-A:1001#2"
