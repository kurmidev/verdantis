# LLD 03 — Heuristic Engine

**Status:** DRAFT. HLD refs: FR-5, FR-6, FR-7; §2.2 Heuristic Engine; §6.1 steps 4–5; §6.2; §6.3; §5.3 (suspicious content); §11.1 (duplicate-detection scale risk).
Shared models: [LLD.md](../LLD.md).

## 1. Purpose
Produce probable (confidence 0.6–0.9) findings from cheap, explainable heuristics and decide which records are uncertain enough to be sent to AI. Same pure-function contract and registry as [module 02](02-rule-engine.md).

## 2. Scope
- In: `weak_description`, `possible_duplicate`, `category_mismatch_candidate`, `conflicting_source_values`, `suspicious_content`; blocking; AI-triage *inputs* (flags, candidate pairs in the uncertain band).
- Out: the AI calls and pipeline (08), AI output validation (09), taxonomy/reference maintenance (10).

## 3. Detailed explanation

### 3.1 Responsibilities
1. Run record-scope heuristics per chunk, batch-scope heuristics in the batch-scope pass.
2. Emit findings with `source = heuristic`, confidence in the stated range, full evidence.
3. Emit **triage signals** (not findings) for uncertain cases: `needs_ai=[normalise_description | category_check | duplicate_adjudication]` with the candidate data, consumed by the triage function (module 08 owner; OQ-127).
4. Never use AI; never mutate input.

### 3.2 Inputs and outputs

| | |
|---|---|
| Input | records (+ `norm` views), `ctx` (params, `generic_terms`, `category_keywords`, `manufacturer_aliases`, `taxonomy`, thresholds) |
| Output | `list[Finding]` and `list[TriageSignal]`; `TriageSignal = {task, record_key, counterpart_record_key?, reason, similarity?}` |

### 3.3 Heuristics (step by step)

**H1 `weak_description` (FR-5), record scope, v1.0.0**
Triggers (HLD 6.1): T1 token count `< min_description_tokens` (3); T2 every token ∈ `generic_terms` (bearing, valve, part, item, misc, spare); T3 no *attribute token* (a token containing a digit — sizes, numbers).
1. Tokens = `norm.description_tokens`; blank description → no finding (module 01 handles `incomplete_row`).
2. `triggers = {T1,T2,T3}` subset that holds; empty → no finding.
3. Severity: HLD says "low/medium", confidence "0.7–0.9 by rule" without the mapping. **PROVISIONAL (OQ-106):** confidence = 0.7 + 0.1×(|triggers|−1); severity `medium` if |triggers| ≥ 2 else `low`.
4. Evidence `{"item_description": raw, "tokens": [...], "triggers": ["T1","T2","T3"]}`.
5. Emit triage signal `normalise_description` (HLD 6.3: "weak_description + AI normalisation suggestion") unless `norm.suspicious` is non-empty.
Note: T3 alone flags descriptions like "SKF Bearing Deep Groove" (4 tokens, no digits). That is the literal HLD reading; expect false positives to be tuned from steward rejections.

**H2 `possible_duplicate` (FR-6), batch scope, v1.0.0**
1. **Canonical manufacturer** `mk = alias(manufacturer)`: lookup in `manufacturer_aliases` (case-insensitive, trimmed); unknown → lowercase trimmed raw. Blank manufacturer → record excluded from H2 (OQ-113).
2. **Block A (exact MPN):** records with non-blank `norm.mpn_key`, grouped by `(mk, mpn_key)`. Any group with ≥2 members whose members come from **different `source_system`s** → finding, confidence **0.9**, severity per policy (OQ-106). Same-system pairs with different `item_id` are not in the HLD wording ("across systems"); parameter `dup_scope = cross_system_only` (default, literal HLD) vs `any` (OQ-113).
3. **Block B (description similarity):** within the same `mk`, among records not already paired by Block A, compute similarity of `norm.description_tokens`. `sim ≥ dup_similarity_threshold (0.88)` → finding, confidence **0.7**. `ai_uncertain_band[0.75, 0.88)` → no finding, emit triage signal `duplicate_adjudication` (pair).
4. **Scorer:** HLD says "description token-set similarity (RapidFuzz)". The scorer is not named and the scale (0–1 vs 0–100) is unstated → OQ-102. **Critical consequence on the brief sample:** with `token_set_ratio`, `"bearing"` vs `"skf bearing 6205 zz"` scores 100 (one token set is a subset of the other), so (1001,1002) would produce a `possible_duplicate` that the brief does not expect; with `token_sort_ratio` or plain `ratio` the score is ≈54 and nothing fires. PROVISIONAL default: `token_sort_ratio` on lowercased tokens (does not treat subset as identical). To be confirmed.
5. **Candidate generation (scale):** the HLD claims O(n) grouping, but pairwise comparison inside one manufacturer block is O(k²). PROVISIONAL: if block size ≤ `max_block_size` (2,000) compare all pairs with a vectorised scorer; otherwise only compare pairs sharing at least one non-generic token via an inverted index; blocks still above a hard cap are skipped with a logged `block_too_large` warning and a batch-level note (never silent). Alternative (ANN over `item_embedding`) is OQ-129.
6. **One finding per pair**, anchored at the lexicographically smaller `record_key`; `evidence = {"counterpart_record_key", "counterpart_item_id", "match": "exact_mpn"|"description_similarity", "mpn_key"?, "similarity"?, "fields": {...both raw descriptions/MPNs...}}`; `dedupe_key` discriminator = counterpart key (OQ-109). Groups >2: pairs capped by `max_pairs_per_block`; evidence lists the group.
7. Never auto-merged (out-of-scope in v1). `suggested_action`: "Compare the two records and confirm whether they are the same item."

**H3 `category_mismatch_candidate` (FR-7), record scope, rule_id `category_mismatch`, v1.0.0**
1. Tokenise description (lowercase; whole-word match; plural/stem handling is OQ-107).
2. `matches = {category_keywords[token]}` for tokens in the map (e.g. `bearing → Mechanical`). No match → no finding.
3. If current `category` is blank → no finding (incomplete handling elsewhere).
4. If every matched expected category equals the current category, or the current category is a descendant of the expected node in the taxonomy (depth OQ-107) → no finding.
5. Otherwise finding: severity `low`; confidence **0.7** if exactly one distinct expected category, **0.6** if several (keyword-ambiguous) — PROVISIONAL split of the HLD range 0.6–0.7 (OQ-106). `suggested_value={"category": <expected>}` (only when unambiguous), action "Review category assignment before approval."
6. Triage signal `category_check` when ambiguous (HLD 6.1.5: "keyword-ambiguous categories") and not suspicious. An unambiguous single-keyword mismatch (brief 1002) does not trigger AI under the literal HLD rule (OQ-127).

**H4 `conflicting_source_values`, batch scope, v1.0.0**
1. Reuse Block A groups (`(mk, mpn_key)`, ≥2 source systems).
2. Compare fields across members (PROVISIONAL set: `category`, `unit_of_measure` after alias mapping; OQ-123). Any field with >1 distinct value → one finding per member listing each system's value.
3. Severity per policy (OQ-106), confidence 0.9 (same basis as the block), source `heuristic`.

**H5 `suspicious_content`, record scope, v1.0.0**
Emit when `norm.suspicious` is non-empty. Evidence = reasons only (not content). Effect: record excluded from every AI task (rule-only), per HLD 5.3. Severity/confidence OQ-106/OQ-121.

### 3.4 Triage signals
Signals are produced for: weak description → `normalise_description`; ambiguous category → `category_check`; pair in uncertain band → `duplicate_adjudication`. Records with `norm.suspicious` never produce signals. The mapping signals → `ai_task` rows and messages is in modules 06/08; target is <30% of records reaching AI (HLD 11.4).

### 3.5 Walk-through: brief sample (exact output of this LLD)

| Record/pair | Check | Result |
|---|---|---|
| 1001 | R1 (module 02) | `missing_part_number`, medium, 1.0, `deterministic_rule` |
| 1001 | H1: tokens `[bearing]`; T1 ✔(1<3) T2 ✔ T3 ✔ | `weak_description`, **medium, 0.9**, `heuristic` + triage `normalise_description` |
| 1001 | H3: `bearing→Mechanical`, current Mechanical | none |
| 1002 | H1: tokens `[skf, bearing, 6205, zz]` (≥3, not all generic, has `6205`) | none |
| 1002 | H3: `bearing→Mechanical` ≠ `Electrical` | `category_mismatch_candidate`, low, **0.7**, `heuristic`, `suggested_value {"category":"Mechanical"}`, action "Review category assignment before approval." |
| (1001,1002) | H2: `mk` = SKF both, cross-system ✔; 1001 `mpn_key` blank → no Block A; Block B | with default `token_sort_ratio` ≈0.54 → none (with `token_set_ratio` → `possible_duplicate`, 0.7) |
| both | H5 | none |

**Differences from the brief's expected output (to resolve):**
1. 1001 `missing_part_number` confidence 1.0 vs brief 0.95 → **OQ-100**.
2. 1001 additionally yields `weak_description` (the description "bearing" meets all three triggers), absent from the brief's expected list → **OQ-101**: is the acceptance test exact-match or "must include"? HLD 1.6 says the sample "yields" the two findings (superset-compatible); the brief says "Expected output will be" (exact-compatible).
3. 1002 matches the brief (low, 0.70, wording identical) except `source`: brief `ai_or_heuristic_candidate`, this LLD `heuristic` → **OQ-130**.
4. A `possible_duplicate` for (1001,1002) appears only under a subset-tolerant scorer → **OQ-102**.

### 3.6 API contracts
None; library. Triage signals are handed to the worker.

### 3.7 Database interactions
Reads only: batch-scope heuristics read `record_snapshot` via `(batch_id, normalised->>'mpn_key')` index and by manufacturer key; may read `item_embedding` if OQ-129 selects ANN. Writes happen in the worker (findings, `ai_task`) in the same per-chunk transaction and with the same `dedupe_key` idempotency and `audit_event` per finding as module 02 (module 05); the heuristic functions are side-effect free.

### 3.8 External dependencies
Reference data (`generic_terms`, `category_keywords`, `taxonomy`, `manufacturer_aliases`, thresholds); RapidFuzz (or equivalent) per ADR (library choice with scorer OQ-102).

### 3.9 Error handling
Per-heuristic isolation (as module 02). Oversized blocks: skipped with warning, never an exception; marks batch note `heuristic_partial` (PROVISIONAL, OQ-129). Missing keyword map → H3 disabled and alert; other checks continue.

### 3.10 Retry strategy
Idempotent; chunk-level retry from module 06; `dedupe_key` prevents duplicate findings.

### 3.11 Edge cases
Same item in 3 systems (pairs/group cap); MPN formats `6205-ZZ` / `6205 ZZ` / `6205ZZ` all block together (normalised for matching only; raw shown as evidence); manufacturer aliases (`SKF`, `S.K.F.`); description with keyword of two categories; description in non-English (keywords miss → no finding; AI/abbreviation dictionary later); 100k records in one manufacturer (block cap path); empty tokens.

### 3.12 Logging
Counts per heuristic, block size histogram (max/p95), pairs compared, blocks skipped, `triage_signals_by_task`. No descriptions in logs.

### 3.13 Security
No egress. `suspicious_content` isolates likely injection text from AI paths. Evidence for pair findings includes another record's raw values — same batch only.

### 3.14 Performance
Target within the 10k-record < 30 s deterministic+heuristic budget. Blocking keeps exact-MPN grouping O(n); description similarity bounded by `max_block_size` and token-inverted index. 100k-record perf test is mandatory (HLD 7.8). Memory: process block by block.

### 3.15 Test requirements
Unit: each heuristic with positive/negative/edge; MPN format trio; weak-description trigger matrix; keyword ambiguity; scorer behaviour table (`"valve"`, `"bearing"` subset cases); alias handling. Property: heuristic output deterministic; no finding references a record outside the batch. Golden: brief sample asserting §3.5 table. Perf: 10k and 100k synthetic with one huge manufacturer block. Labelled duplicate set for recall ≥ 80% (HLD 1.6). Coverage ≥85%.

## 4. Architecture decisions
D-03-1 blocking-first duplicate detection (HLD); D-03-2 PROVISIONAL scorer and candidate cap (OQ-102, OQ-129); D-03-3 pair findings anchored on one record. ADR-003 (pgvector) relevant only if OQ-129 chooses ANN.

## 5. Dependencies
01 (norm), 02 (registry), 05, 06, 08 (triage consumer), 10 (reference data).

## 6. Risks and edge cases
O(k²) blow-up in large manufacturer blocks (HLD 11.1); `weak_description` T3 false positives; subset-tolerant scorer false positives; alias coverage; confidence ranges not calibrated until steward data exists.

## 7. Related documents
[LLD.md](../LLD.md) · [02](02-rule-engine.md) · [06](06-queue-and-workers.md) · [08](08-agent-orchestrator.md) · [10](10-rag-and-reference-data.md) · [Testing](../../testing/TESTING_AND_EVALUATION.md)

## Open questions (this module)

| ID | Question |
|---|---|
| OQ-101 | Brief sample acceptance: exact two findings, or at least those two (1001 also yields `weak_description`)? |
| OQ-102 | RapidFuzz scorer (`token_set_ratio` gives 100 for a subset, flagging 1001/1002) and scale (0–1 vs 0–100) for the 0.88 / 0.75 thresholds. |
| OQ-107 | Keyword→expected-category map contents, taxonomy depth/hierarchy, plural/stem matching. |
| OQ-113 | Duplicate scope: cross-system only (HLD wording) vs same-system different `item_id`; behaviour for blank manufacturer; max group size. |
| OQ-122 | Issue type/finding shape for FR-8 normalised-description suggestion. |
| OQ-123 | Which fields `conflicting_source_values` compares and how "same item" is decided. |
| OQ-127 | Where triage runs and whether an unambiguous category mismatch (brief 1002) goes to AI. |
| OQ-129 | Candidate generation for description similarity inside large manufacturer blocks (inverted index vs ANN vs cap). |
