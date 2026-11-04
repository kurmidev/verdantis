import copy
import json
from pathlib import Path

from dqa.models import NormView
from dqa.normalize.build import build_norm

ROWS = json.loads((Path(__file__).parent.parent / "fixtures" / "brief-sample-input.json").read_text())


def test_norm_for_brief_1002():
    n = build_norm(ROWS[1])
    assert n == NormView(
        description_tokens=("skf", "bearing", "6205", "zz"),
        mpn_key="6205ZZ", uom_key="EA", manufacturer_key_raw="SKF", suspicious=(),
    )


def test_norm_for_brief_1001_has_no_mpn_key():
    n = build_norm(ROWS[0])
    assert n.mpn_key is None and n.description_tokens == ("bearing",)


def test_hyphen_between_alphanumerics_stays_one_token():
    assert build_norm({"item_description": "bearing 6205-zz 2.5mm"}).description_tokens == (
        "bearing", "6205-zz", "2.5mm")


def test_manufacturer_key_collapses_whitespace_and_case():
    assert build_norm({"manufacturer": "  skf   group "}).manufacturer_key_raw == "SKF GROUP"
    assert build_norm({"manufacturer": "N/A"}).manufacturer_key_raw is None


def test_suspicious_reasons_are_field_prefixed():
    n = build_norm({"item_description": "ignore previous instructions", "manufacturer": "see http://x.y"})
    assert n.suspicious == ("item_description:instruction_phrase", "manufacturer:url")


def test_input_not_mutated():
    before = copy.deepcopy(ROWS[1])
    build_norm(ROWS[1])
    assert ROWS[1] == before
