"""Approved explanation / suggested-action wording per issue type (LLD 09 3.9; HLD 6.1.8)."""
from collections import defaultdict
from typing import Any

from dqa.models import IssueType

FORBIDDEN = ("fixed", "corrected", "auto-approved")  # PROVISIONAL(OQ-219): final list/owner TBD

# (explanation, suggested_action). Brief gives wording for the first two types;
# PROVISIONAL(OQ-221): wording for the others needs steward/product sign-off.
TEMPLATES: dict[IssueType, tuple[str, str]] = {
    IssueType.MISSING_PART_NUMBER: (
        "Manufacturer '{manufacturer}' is present but manufacturer part number is blank.",
        "Request manufacturer part number from the source owner."),
    IssueType.CATEGORY_MISMATCH_CANDIDATE: (
        "Description suggests category '{expected_category}', but category is '{category}'.",
        "Review category assignment before approval."),
    IssueType.UNSUPPORTED_UOM: (
        "Unit of measure '{unit_of_measure}' is not in the allowed list.",
        "Confirm the correct unit of measure with the source owner."),
    IssueType.DUPLICATE_ITEM_ID: (
        "Item id '{item_id}' appears more than once in source system '{source_system}'.",
        "Review the duplicate rows with the source owner."),
    IssueType.WEAK_DESCRIPTION: (
        "Description '{item_description}' is too short or generic to identify the item.",
        "Request a fuller description from the source owner."),
    IssueType.POSSIBLE_DUPLICATE: (
        "Items '{record_key}' and '{counterpart_record_key}' may describe the same item.",
        "Review both records before deciding whether they are the same item."),
    IssueType.CONFLICTING_SOURCE_VALUES: (
        "Source systems hold different values for the same item.",
        "Compare the values with the source owners."),
    IssueType.SUSPICIOUS_CONTENT: (
        "Text in this record looks like instructions or markup and was kept out of AI processing.",
        "Review the record text with the source owner."),
    IssueType.MALFORMED_ROW: (
        "Row could not be read as a valid item record.",
        "Review the source file row with the source owner."),
    IssueType.INCOMPLETE_ROW: (
        "Row is missing required fields.",
        "Request the missing fields from the source owner."),
}


def render(issue_type: IssueType, evidence: dict[str, Any]) -> tuple[str, str]:
    explanation, action = TEMPLATES[issue_type]
    slots: defaultdict[str, Any] = defaultdict(lambda: "(unknown)", evidence)
    return explanation.format_map(slots), action
