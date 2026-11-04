"""Input scanner (HLD 5.3, LLD 01 step 8): flags content that must get rule-only processing."""
import re

# PROVISIONAL(OQ-121, OQ-315): pattern list and limit are placeholders until the owner confirms them.
MAX_AI_FIELD_LENGTH = 1000

_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "instruction_phrase": tuple(
        re.compile(p, re.IGNORECASE)
        for p in (
            r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\b",
            r"\bdisregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\b",
            r"\bsystem\s+prompt\b",
            r"\byou\s+are\s+now\b",
            r"\bmark\s+(?:this\s+)?as\s+approved\b",
        )
    ),
    "url": (re.compile(r"https?://|\bwww\.", re.IGNORECASE),),
    "code_like": tuple(
        re.compile(p, re.IGNORECASE) for p in (r"<\s*script", r"```", r"\{\{", r"\$\{")
    ),
}


def scan_suspicious(text: str | None, *, max_len: int = MAX_AI_FIELD_LENGTH) -> tuple[str, ...]:
    """Sorted, de-duplicated reason codes; empty tuple means clean."""
    if not text:
        return ()
    reasons = {r for r, pats in _PATTERNS.items() if any(p.search(text) for p in pats)}
    if len(text) > max_len:
        reasons.add("too_long")
    return tuple(sorted(reasons))
