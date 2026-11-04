"""H2 possible_duplicate (batch scope): exact-MPN blocks, then description similarity.

Scorer: rapidfuzz token_sort_ratio / 100 (PROVISIONAL OQ-11, OQ-102, OQ-248). token_set_ratio scores
100 when one description's tokens are a subset of the other's ("bearing" vs "skf bearing 6205 zz"),
which would pair brief records 1001/1002; token_sort_ratio does not.
"""
import logging
from collections import defaultdict
from collections.abc import Iterator, Sequence
from itertools import combinations

from rapidfuzz import fuzz, process

from dqa.checks.heuristics._build import VERSION, make_finding, mfr_key, mpn_key, severity, tokens
from dqa.checks.registry import rule
from dqa.models import Context, Finding, IssueType, Record, Severity

RULE_ID = "possible_duplicate"
EXACT_MPN_CONFIDENCE = 0.9
SIMILARITY_CONFIDENCE = 0.7
MAX_BLOCK_SIZE = 2_000  # PROVISIONAL(OQ-129): full pairwise compare up to here, inverted index above
HARD_BLOCK_CAP = 20_000  # PROVISIONAL(OQ-129): blocks above this are skipped with a warning
MAX_PAIRS_PER_BLOCK = 1_000  # PROVISIONAL(OQ-113): cap on pairs from one exact-MPN group

log = logging.getLogger(__name__)


def _finding(a: Record, b: Record, ctx: Context, match: str, conf: float, extra: dict[str, object]) -> Finding:
    a, b = sorted((a, b), key=lambda r: r.record_key)
    return make_finding(
        a, ctx, issue_type=IssueType.POSSIBLE_DUPLICATE, rule_id=RULE_ID,
        sev=severity(ctx, IssueType.POSSIBLE_DUPLICATE, Severity.MEDIUM), confidence=conf,
        explanation="These records from different source systems may describe the same item.",
        evidence={
            "counterpart_record_key": b.record_key, "counterpart_item_id": b.item_id, "match": match,
            **extra,
            "fields": {
                x.record_key: {"item_description": x.item_description,
                               "manufacturer_part_number": x.manufacturer_part_number}
                for x in (a, b)
            },
        },
        action="Compare the two records and confirm whether they are the same item.",
        discriminator=b.record_key,
    )


def _candidate_pairs(strs: list[str], toks: list[tuple[str, ...]], generic: set[str], thr: float
) -> Iterator[tuple[int, int, float]]:
    """Yield (i, j, similarity) with i < j and similarity >= thr."""
    n = len(strs)
    if n <= MAX_BLOCK_SIZE:
        for i in range(n):
            for _, score, j in process.extract(
                strs[i], strs, scorer=fuzz.token_sort_ratio, score_cutoff=thr * 100, limit=None
            ):
                if j > i:
                    yield i, j, score / 100
        return
    # ponytail: tokens shared by > MAX_BLOCK_SIZE records are ignored; ANN over embeddings if needed (OQ-129)
    postings: dict[str, list[int]] = defaultdict(list)
    for i, ts in enumerate(toks):
        for t in set(ts) - generic:
            postings[t].append(i)
    for i, ts in enumerate(toks):
        cands = {j for t in set(ts) - generic if len(postings[t]) <= MAX_BLOCK_SIZE
                 for j in postings[t] if j > i}
        for j in cands:
            score = fuzz.token_sort_ratio(strs[i], strs[j])
            if score >= thr * 100:
                yield i, j, score / 100


@rule(RULE_ID, VERSION, IssueType.POSSIBLE_DUPLICATE, layer="heuristic", scope="batch")
def possible_duplicate(records: Sequence[Record], ctx: Context) -> list[Finding]:
    generic = {g.lower() for g in ctx.reference.generic_terms}
    thr = ctx.params.dup_similarity_threshold
    by_mfr: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        if (mk := mfr_key(r, ctx)) is not None:
            by_mfr[mk].append(r)

    out: list[Finding] = []
    seen: set[frozenset[str]] = set()
    # Block A: exact normalised MPN within canonical manufacturer, cross-system pairs only.
    for mk in sorted(by_mfr):
        groups: dict[str, list[Record]] = defaultdict(list)
        for r in by_mfr[mk]:
            if (k := mpn_key(r)) is not None:
                groups[k].append(r)
        for k in sorted(groups):
            members = sorted(groups[k], key=lambda r: r.record_key)
            pairs = [(a, b) for a, b in combinations(members, 2) if a.source_system != b.source_system]
            for a, b in pairs[:MAX_PAIRS_PER_BLOCK]:
                seen.add(frozenset((a.record_key, b.record_key)))
                out.append(_finding(a, b, ctx, "exact_mpn", EXACT_MPN_CONFIDENCE, {"mpn_key": k}))

    # Block B: description similarity within manufacturer, pairs not already found by Block A.
    for mk in sorted(by_mfr):
        block = [r for r in by_mfr[mk] if tokens(r)]
        if len(block) > HARD_BLOCK_CAP:
            log.warning("block_too_large manufacturer_block_size=%d skipped", len(block))
            continue
        toks = [tokens(r) for r in block]
        strs = [" ".join(t) for t in toks]
        for i, j, sim in _candidate_pairs(strs, toks, generic, thr):
            a, b = block[i], block[j]
            pair = frozenset((a.record_key, b.record_key))
            if a.source_system == b.source_system or pair in seen:
                continue
            seen.add(pair)
            out.append(_finding(a, b, ctx, "description_similarity", SIMILARITY_CONFIDENCE,
                                {"similarity": round(sim, 3)}))
    return sorted(out, key=lambda f: (f.record_key, f.evidence["counterpart_record_key"]))
