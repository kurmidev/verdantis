"""Heuristic checks. Importing the submodules registers the rules (modules, not functions, are exported)."""
from dqa.checks.heuristics import (  # noqa: F401
    category_mismatch,
    conflicting_values,
    possible_duplicate,
    weak_description,
)
