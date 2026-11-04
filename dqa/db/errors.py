class IntegrityViolation(Exception):
    """A referential or uniqueness rule was broken (missing batch/snapshot, etc.)."""
