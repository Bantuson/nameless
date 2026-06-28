---
status: issues
phase: 04-cited-claim-mining-cross-reference
depth: standard
files_reviewed: 20
findings:
  critical: 0
  warning: 6
  info: 3
  total: 9
---

# Phase 4: Code Review Report — Cited Claim Mining + Cross-Reference

**Depth:** standard (Python-specific)
**Status:** issues_found

## Summary

The no-synthesis boundary is structurally sound: identity/citation fields are taken from the transcript (never the model) in `parse_extractor_output`, the tool schema sets `additionalProperties: false`, the extraction prompt is extract-only, SQL is fully parameterized, and cross-reference/dedup are pure and never drop a cross-source claim. No security issues and no Critical defects were found by reading.

The defects cluster on the two surfaces the phase cares most about: the **citation gate kernel** (`verify_citation` has both an over-reject and an under-reject path) and **conflict preservation** (conflict detection is entirely dependent on the `stance` field, and the content-addressed id + dedup keys are blind to `stance`/`technique`, opening a same-source conflict-collapse hole). None of these lose a *cross-source* contradiction, which is why they are Warnings rather than Blockers — but they directly weaken the anti-GIGO guarantees the phase is built to provide.

## Warnings

### WR-01: `verify_citation` never prefers the in-tolerance occurrence of a recurring quote (false DRIFT)

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation.py:85-95`
**Issue:** `best_start_ms` is only reassigned on a strict `cov > best_cov`. Once the FIRST coverage-1.0 segment is seen, `best_cov` is 1.0 and every later coverage-1.0 segment fails `cov > best_cov`, so `best_start_ms` is frozen on the first occurrence. The docstring at line 92-93 promises "keep scanning only to prefer the in-tolerance occurrence of an exact substring," but that switch is never performed. If a quoted phrase recurs (an earlier filler occurrence + the real cited one), and the cited `timestamp_ms` matches a LATER occurrence, the function reports `drift` against the first occurrence even though the claim is correctly anchored. `_reanchor` (extraction_schema.py:131) snaps the claim ts to the *closest* occurrence, so the real extractor path can produce a correctly-anchored claim that this gate then falsely flags — and with `require_citation=True` it would be dropped.
**Why it matters:** This is the kernel of Phase 5's hard citation gate. A wrong verdict here propagates. Over-rejection of legitimately-cited claims silently erodes the corpus.
**Fix:** Track the best in-tolerance match separately, e.g. prefer a candidate whose `|claim.timestamp_ms - start| <= tolerance_ms` at equal coverage:
```python
better = cov > best_cov or (
    cov == best_cov and best_start_ms is not None
    and abs(claim.timestamp_ms - seg_start) < abs(claim.timestamp_ms - best_start_ms)
)
if better:
    best_cov, best_start_ms = cov, seg_start
```

### WR-02: token-subset coverage scores 1.0 for scattered (non-substring) matches — under-rejection in the gate

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/citation.py:45-56` (used at 88-98)
**Issue:** `_coverage` returns 1.0 only for a contiguous substring, but the token-subset branch returns `hits/len(q)`, which also reaches 1.0 when every quote token merely *appears somewhere* in the segment, in any order, non-contiguously. `verify_citation` then treats `best_cov >= 1.0` as an exact hit and, if the segment start is within tolerance, returns `verified`. So a quote whose words are all present but scrambled/scattered in a nearby line is marked `verified`, contradicting the docstring claim that token-subset coverage avoids "admitting a loosely-related sentence." This is the dangerous direction (a fabricated/paraphrased quote passing the gate).
**Why it matters:** Citation drift / fabrication is the phase's stated worst GIGO failure; a verified-but-not-actually-quoted claim defeats the audit trail.
**Fix:** Distinguish substring hits from token-subset hits — only the substring path should yield 1.0 and short-circuit; cap token-subset coverage below 1.0 (e.g. return `min(0.99, hits/len(q))`) or require order/contiguity for high coverage. Reserve the `break` fast-path for true substring matches.

### WR-03: conflict detection depends entirely on the `stance` field — contradictory claims with null stance become false consensus

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/cross_reference.py:50-51`
**Issue:** A topic is contested iff `len({normalize_key(c.stance) for ... if c.stance})` >= 2. Two genuinely opposed claims ("boost 2 kHz" vs "cut 2 kHz") that both carry `stance=None` produce zero distinct stances → `contested=False` → both land in `consensus`. Nothing detects the semantic contradiction; the disagreement is laundered into apparent agreement. The claims are still *present* (not deleted), so this is not data loss, but the cluster mislabels a conflict as consensus — exactly the "laundering disagreement into false consensus" failure the prompt warns the LLM against, now reproduced deterministically when the extractor omits a stance.
**Why it matters:** Conflict preservation is the central deliverable of this phase. The guarantee silently degrades to "only as good as the extractor's stance labeling," which the real (env-gated) LLM may not populate reliably.
**Fix:** This is partly env-gated (it depends on real extractor output), but the cross-reference layer should not present unverifiable consensus. Consider (a) treating divergent load-bearing numbers under one topic as a candidate conflict signal, or (b) surfacing `distinct_consensus_sources` vs a "single-source / unstanced" caveat so an unstanced topic is never reported as corroborated consensus.

### WR-04: content-addressed id and dedup keys are blind to `stance`/`technique` — same-source conflict-collapse hole

**File:** `knowledge-pipeline/src/knowledge_pipeline/domain/keys.py:94` and `knowledge-pipeline/src/knowledge_pipeline/pure/claim_dedup.py:61`
**Issue:** `compute_claim_id` hashes only `source_video_id | timestamp_ms | normalize_text(claim_text)`. Two claims from the same video at the same timestamp with identical `claim_text` but different `stance` (or `technique`) collapse to the same id, and layer-1 dedup (claim_dedup.py:48-55) silently drops one. Layer-2's key `(source_video_id, topic, normalize_text(claim_text))` (line 61) likewise ignores `stance`, so the same point restated at a *different* timestamp with an opposing stance is dropped as a "repeat." Both paths can erase a side of a same-source disagreement.
**Why it matters:** The phase forbids ever collapsing a conflict. This is same-source only (cross-source ids differ, so cross-source contradictions are safe), but it is still a silent conflict-deletion vector that contradicts the no-collapse invariant.
**Fix:** Include `normalize_key(stance)` (and ideally `technique`) in `compute_claim_id`'s basis and in the layer-2 dedup key, so claims that differ in stance are never deduplicated against each other.

### WR-05: `require_citation` defaults to False and is never set live — citation-failing/hallucinated claims persist by default

**File:** `knowledge-pipeline/src/knowledge_pipeline/mining_pipeline.py:57,135` (with `pure/extraction_schema.py:158-159`)
**Issue:** When the real extractor emits a `quote` that does not occur in the transcript, `_reanchor` returns `None` and `parse_extractor_output` keeps the *model's* unvalidated `timestamp_ms` (extraction_schema.py:159). `verify_citation` then returns `not_found`, but because `MiningConfig.require_citation` defaults to `False` and `claims_cli` never sets it on the live path, the claim is still upserted (flagged `citation_verified=0`) with a timestamp the source never supports. The default mode admits effectively-forged citations into the store.
**Why it matters:** "A claim with no locatable source is rejected" is a stated requirement; the default behavior keeps it. The flag exists but the live CLI never enables it, so the safe path is opt-in only.
**Fix:** Default `require_citation=True` (or have the live CLI set it), or at minimum refuse to store a claim whose quote is absent from the transcript rather than persisting the model's invented timestamp. [partially env-gated — only the real LLM fabricates; the fake/rule-based extractor always anchors verbatim]

### WR-06: semantic (embedding) dedup ignores numeric parameters — can collapse distinct same-source values

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/claim_dedup.py:74-88` (+ `adapters/similarity_embeddings.py`)
**Issue:** `_is_semantic_dup` collapses same-source same-topic claims whose `similarity >= threshold`. An embedding model rates "high-pass at 30 Hz" and "high-pass at 40 Hz" as near-identical (well above 0.9), so two distinct, load-bearing numeric parameters from the same source can be deduplicated to one — discarding a number the project treats as craft. Unlike `verify_citation`/`numbers()`, the similarity hook has no number-aware guard. (Keyword Jaccard is mostly safe here because the differing digit lowers overlap, but the embedding adapter is the intended upgrade path.)
**Why it matters:** Inventing/erasing numbers is the worst GIGO failure the phase guards against; semantic dedup creates a new way to silently erase one.
**Fix:** Before treating two claims as semantic duplicates, require their numeric token sets (`domain.keys.numbers`) to be equal; if the numbers differ, never collapse. [env-gated for the embedding adapter; off by default]

## Info

### IN-01: `claims mine` help advertises fixtures as the default, but the default mode is live (env-gated)

**File:** `knowledge-pipeline/src/knowledge_pipeline/claims_cli.py:101-104,260-263`
**Issue:** `--fixtures` uses `default=None`, and `_build_pipeline` routes `args.fixtures is None` to `_live_plane`. So `claims mine` with no flags runs the live Anthropic plane and `SystemExit`s without a key — yet the arg help says "OFFLINE mode over the bundled claim fixtures (default)" and the module docstring (lines 11-14) calls fixtures the default. Misleading for the offline/CI demo path.
**Fix:** Either make fixtures the actual default (e.g. `default=""`/sentinel routing to offline) or correct the help/docstring to state that live is the default and `--fixtures` is required for offline.

### IN-02: cross-reference cluster `stage`/`technique` taken from `members[0]` raw labels

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/cross_reference.py:55-56`
**Issue:** Members share a *normalized* topic key, but the cluster's displayed `stage`/`technique` are the raw labels of the arbitrary first member. Two claims with raw stages "Mixing" and "mixing" map to one topic but the cluster shows whichever sorted first. Cosmetic/display inconsistency only.
**Fix:** Store the normalized stage/technique (split the topic key) for the cluster's representative labels.

### IN-03: `clusters.distinct_consensus_sources` column is written but never read back

**File:** `knowledge-pipeline/src/knowledge_pipeline/claims_sql.py:61` (+ `adapters/claim_store_sqlite.py:143,186-206`)
**Issue:** `replace_clusters` persists `distinct_consensus_sources`, but `_build_cluster` recomputes it from the joined claims (it is a computed field) and `stats()` uses COUNT queries — the stored column is never consumed, so it can silently drift from the recomputed value with no effect. Dead/redundant persisted state.
**Fix:** Drop the column, or read it back instead of recomputing, to keep one source of truth.

---

_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
