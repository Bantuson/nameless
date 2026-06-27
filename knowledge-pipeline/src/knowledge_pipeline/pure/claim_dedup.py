"""``dedup_claims`` — PURE de-duplication of extracted claims (KNOW-06 "distinct sources, not repeats").

Corroboration confidence must come from *independent* sources agreeing, not from one creator (or one
extraction run) saying the same thing twice. Two de-dup layers, both pure:

  1. **Exact** — collapse claims sharing a content-addressed ``id`` (same source + timestamp + normalized
     text). This makes re-mining idempotent and removes verbatim repeats.
  2. **Same-source near-duplicate** — within ONE ``(source_video_id, topic)``, collapse claims whose
     normalized ``claim_text`` is identical (a producer re-stating the same point at two timestamps).
     Claims from DIFFERENT sources are NEVER merged — that asymmetry is the whole point: cross-source
     agreement is signal (it becomes consensus), same-source repetition is noise.

An optional **semantic** refinement (the ``similarity`` hook) collapses same-source near-paraphrases
("roll off the low end" ≈ "high-pass the bottom") above a threshold. It is OFF by default so the core
stays deterministic and testable; the pipeline injects a keyword (or, env-gated, an embedding) similarity
when richer dedup is wanted. Cross-source claims remain untouched regardless — semantic dedup never
fabricates or erases corroboration. (LEARNING §5 covers the trade-off.)
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from ..domain.claims import Claim
from ..domain.keys import normalize_text

# A similarity function: two texts -> 0..1. Injected (keyword fake / embedding real); never required.
SimilarityFn = Callable[[str, str], float]


def dedup_claims(
    claims: Sequence[Claim],
    *,
    similarity: Optional[SimilarityFn] = None,
    threshold: float = 0.9,
) -> tuple[list[Claim], int]:
    """Drop exact + same-source near-duplicate claims. Cross-source claims are preserved. Pure.

    Args:
        claims: the claims to de-duplicate (first occurrence wins — stable order).
        similarity: optional same-source semantic de-dup hook (0..1). ``None`` => exact-text only.
        threshold: similarity at/above which two same-source same-topic claims are treated as duplicates.

    Returns:
        ``(deduped_claims_in_first_seen_order, number_dropped)``.
    """
    # ---- layer 1: exact id collapse ----
    by_id: dict[str, Claim] = {}
    order: list[str] = []
    for c in claims:
        if c.id not in by_id:
            by_id[c.id] = c
            order.append(c.id)
    unique = [by_id[i] for i in order]
    dropped = len(claims) - len(unique)

    # ---- layer 2: same-source (+ optional semantic) near-duplicate collapse ----
    result: list[Claim] = []
    seen_exact: set[tuple[str, str, str]] = set()
    for c in unique:
        key = (c.source_video_id, c.topic, normalize_text(c.claim_text))
        if key in seen_exact:
            dropped += 1
            continue
        if similarity is not None and _is_semantic_dup(c, result, similarity, threshold):
            dropped += 1
            continue
        seen_exact.add(key)
        result.append(c)

    return result, dropped


def _is_semantic_dup(
    candidate: Claim,
    kept: list[Claim],
    similarity: SimilarityFn,
    threshold: float,
) -> bool:
    """True if ``candidate`` near-paraphrases an already-kept claim from the SAME source + topic. Pure."""
    for other in kept:
        if other.source_video_id != candidate.source_video_id:
            continue  # never merge across sources
        if other.topic != candidate.topic:
            continue
        if similarity(other.claim_text, candidate.claim_text) >= threshold:
            return True
    return False
