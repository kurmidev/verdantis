"""record_key derivation (LLD 3.6, PROVISIONAL OQ-124)."""
from dqa.normalize.core import is_blank


class KeyAssigner:
    """Stateful per batch: first occurrence of (source_system, item_id) keeps the plain key, later ones get #2, #3..."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def assign(self, row_number: int, source_system: str | None, item_id: str | None) -> str:
        if source_system is None or item_id is None or is_blank(source_system) or is_blank(item_id):
            return f"row:{row_number}"
        base = f"{source_system.strip()}:{item_id.strip()}"
        n = self._seen.get(base, 0) + 1
        self._seen[base] = n
        # ponytail: an item_id that literally ends in '#2' could collide; add escaping if real data does that.
        return base if n == 1 else f"{base}#{n}"
