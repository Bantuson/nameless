"""``verify_citation`` — the PURE precursor to Phase 5's hard citation gate (KNOW-05 #2).

Every claim cites ``source_video_id @ timestamp_ms`` with a VERBATIM ``quote``. This function checks
that the quote actually occurs *at or near* the cited timestamp inside the immutable snapshot — the
single most corrosive GIGO failure is **citation drift**: a real-looking citation attached to a claim
the source did not make (PITFALLS #3). It is a pure function (transcript + claim in, verdict out, no
I/O) so it is trivially testable and reusable as the kernel of Phase 5's gate.

Three outcomes it distinguishes (all are ``ok == False`` except the first):
  * **verified**  — the normalized quote is found in a segment whose start is within ``tolerance_ms``
                    of the cited timestamp.
  * **drift**     — the quote *is* in the transcript, but at a timestamp far from the cited one
                    (the citation points at the wrong place — the dangerous case).
  * **not_found** — the quote does not occur in the transcript at all (hallucinated / fabricated).
  * **empty**     — the claim carries no quote (nothing to verify).

Matching is over :func:`knowledge_pipeline.domain.keys.normalize_text` (case/punct/whitespace folded,
**digits and units preserved**) so "Cut around 300 Hz!" verifies "cut around 300 hz" — but a wrong
number never silently passes. A contiguous-substring hit scores coverage 1.0; otherwise we fall back to
token-subset coverage and require ``min_coverage`` (catches minor caption truncation without admitting a
loosely-related sentence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..domain.claims import Claim
from ..domain.keys import normalize_text, tokens
from ..domain.models import RawTranscript


@dataclass(frozen=True)
class CitationCheck:
    """The verdict of :func:`verify_citation` — auditable, not just a bool."""

    ok: bool
    reason: str                                  # verified | drift | not_found | empty
    matched_start_ms: Optional[int] = None       # the segment start where the quote was found
    offset_ms: Optional[int] = None              # |claim.timestamp_ms - matched_start_ms|
    coverage: float = 0.0                        # 0..1 fraction of the quote found in the matched segment


def _coverage(quote_norm: str, segment_norm: str) -> float:
    """1.0 for a contiguous substring hit; else token-subset coverage of the quote. Pure."""
    if not quote_norm:
        return 0.0
    if quote_norm in segment_norm:
        return 1.0
    q = tokens(quote_norm)
    if not q:
        return 0.0
    seg = set(tokens(segment_norm))
    hits = sum(1 for t in q if t in seg)
    return hits / len(q)


def verify_citation(
    claim: Claim,
    snapshot: RawTranscript,
    *,
    tolerance_ms: int = 2000,
    min_coverage: float = 0.8,
) -> CitationCheck:
    """Check ``claim.quote`` occurs at/near ``claim.timestamp_ms`` in ``snapshot``. Pure.

    Args:
        claim: the claim to verify (carries quote + cited timestamp).
        snapshot: the immutable Phase-3 transcript (timestamped segments) the claim was mined from.
        tolerance_ms: how far the matched segment's start may sit from the cited timestamp before it
            counts as DRIFT (default 2s — caption timestamps are coarse).
        min_coverage: minimum token coverage to accept a non-substring match (default 0.8).

    Returns:
        A :class:`CitationCheck`. The *best* matching segment (highest coverage) decides the verdict;
        a high-coverage match at the wrong time is reported as ``drift`` (not silently accepted),
        which is exactly the citation-drift failure Phase 5's gate must reject.
    """
    if not claim.quote or not claim.quote.strip():
        return CitationCheck(ok=False, reason="empty")

    quote_norm = normalize_text(claim.quote)

    best_cov = 0.0
    best_start_ms: Optional[int] = None
    for seg in snapshot.segments:
        cov = _coverage(quote_norm, normalize_text(seg.text))
        if cov > best_cov:
            best_cov = cov
            best_start_ms = int(round(seg.start_s * 1000))
        if best_cov >= 1.0:
            # keep scanning only to prefer the in-tolerance occurrence of an exact substring
            if best_start_ms is not None and abs(claim.timestamp_ms - best_start_ms) <= tolerance_ms:
                break

    if best_start_ms is None or best_cov < min_coverage:
        return CitationCheck(ok=False, reason="not_found", coverage=best_cov)

    offset = abs(claim.timestamp_ms - best_start_ms)
    if offset > tolerance_ms:
        return CitationCheck(
            ok=False, reason="drift", matched_start_ms=best_start_ms, offset_ms=offset, coverage=best_cov
        )

    return CitationCheck(
        ok=True, reason="verified", matched_start_ms=best_start_ms, offset_ms=offset, coverage=best_cov
    )
