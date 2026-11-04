import pytest

from dqa.checks.templates import FORBIDDEN, TEMPLATES, render
from dqa.models import IssueType


def test_every_issue_type_has_a_template():
    assert set(TEMPLATES) == set(IssueType)


@pytest.mark.parametrize("issue_type", list(IssueType))
def test_templates_never_contain_forbidden_wording(issue_type):
    explanation, action = TEMPLATES[issue_type]
    for text in (explanation.lower(), action.lower()):
        assert not any(w in text for w in FORBIDDEN)


def test_render_fills_slots_from_evidence():
    exp, act = render(IssueType.MISSING_PART_NUMBER, {"manufacturer": "SKF"})
    assert exp == "Manufacturer 'SKF' is present but manufacturer part number is blank."
    assert act == "Request manufacturer part number from the source owner."


def test_render_tolerates_missing_slot():
    exp, _ = render(IssueType.MISSING_PART_NUMBER, {"other": 1})
    assert "(unknown)" in exp
