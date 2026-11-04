import pytest
from hypothesis import given
from hypothesis import strategies as st

from dqa.normalize.core import is_blank, normalize_mpn, normalize_uom, tokenize


@pytest.mark.parametrize("v", [None, "", " ", "\t\n", " ", "N/A", "n/a", " null ", "NULL"])
def test_is_blank_true(v):
    assert is_blank(v)


@pytest.mark.parametrize("v", ["SKF", "0", "none", "-", "n.a."])
def test_is_blank_false_for_unconfirmed_markers(v):
    assert not is_blank(v)


@pytest.mark.parametrize("v", ["6205-ZZ", "6205 ZZ", "6205ZZ", "6205.zz", "6205–ZZ", "6205−zz"])
def test_normalize_mpn_equal_across_formats(v):
    assert normalize_mpn(v) == "6205ZZ"


def test_normalize_mpn_blank_is_none():
    assert normalize_mpn("") is None and normalize_mpn(None) is None and normalize_mpn("N/A") is None


@given(st.text())
def test_normalize_mpn_idempotent(s):
    once = normalize_mpn(s)
    assert normalize_mpn(once) == once


@pytest.mark.parametrize("v,exp", [("ea", "EA"), (" Each ", "EACH"), ("EA.", "EA"), ("", None), (None, None)])
def test_normalize_uom(v, exp):
    assert normalize_uom(v) == exp


def test_tokenize_splits_words_and_numbers():
    assert tokenize("SKF Bearing 6205 ZZ") == ("skf", "bearing", "6205", "zz")
    assert tokenize(None) == ()
