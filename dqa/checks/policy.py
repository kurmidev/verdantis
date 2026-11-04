"""Default severity policy. Only 3 values are firm in the HLD (6.1); the rest are PROVISIONAL."""
from dqa.models import Context, IssueType, Severity

# PROVISIONAL(OQ-106): full table + "business impact" input are not defined by the HLD.
DEFAULT_SEVERITY: dict[IssueType, Severity] = {
    IssueType.MISSING_PART_NUMBER: Severity.MEDIUM,  # HLD 6.1
    IssueType.UNSUPPORTED_UOM: Severity.HIGH,  # HLD 6.1
    IssueType.DUPLICATE_ITEM_ID: Severity.HIGH,  # HLD 6.1
    IssueType.WEAK_DESCRIPTION: Severity.MEDIUM,
    IssueType.POSSIBLE_DUPLICATE: Severity.MEDIUM,
    IssueType.CATEGORY_MISMATCH_CANDIDATE: Severity.LOW,  # brief
    IssueType.CONFLICTING_SOURCE_VALUES: Severity.MEDIUM,
    IssueType.MALFORMED_ROW: Severity.HIGH,
    IssueType.INCOMPLETE_ROW: Severity.MEDIUM,
    IssueType.SUSPICIOUS_CONTENT: Severity.MEDIUM,
}


def severity_for(ctx: Context, issue_type: IssueType) -> Severity:
    return ctx.reference.severity_policy.get(issue_type, DEFAULT_SEVERITY[issue_type])
