"""FakeClaimExtractor — the deterministic :class:`~knowledge_pipeline.ports.ClaimExtractor` for tests.

Stands in for Claude with ZERO API. Two modes, both grounded (never synthesized):

  * **scripted** — return preset, citation-anchored claims per video id (from the claim fixtures). The
    quotes are literal transcript-segment text, so :func:`verify_citation` passes — this is how the
    pipeline e2e + CLI fixtures exercise the *real* control flow with deterministic data.
  * **rule-based fallback** — when a video has no script, delegate to
    :func:`knowledge_pipeline.pure.extraction_schema.rule_based_extract` (LLM-free, lexicon-driven).

INVARIANT (the no-synthesis boundary, tested): this fake emits only cited atoms — every claim's quote is
verbatim transcript text, no claim carries an opinionated "default"/merged field, and it never returns a
cluster or a reconciled "best way". That boundary is what Phase 4 is, made checkable.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from ..domain.claims import Claim
from ..domain.models import RawTranscript
from ..pure.extraction_schema import rule_based_extract


class FakeClaimExtractor:
    """Deterministic extractor over preset (scripted) claims, falling back to rule-based extraction."""

    def __init__(self, scripted: Optional[Mapping[str, list[Claim]]] = None) -> None:
        self._scripted = {k: list(v) for k, v in (scripted or {}).items()}
        self.calls: list[str] = []  # which videos were extracted (test assertions)

    def extract(self, transcript: RawTranscript, *, genres: Iterable[str] = ()) -> list[Claim]:
        self.calls.append(transcript.video_id)
        preset = self._scripted.get(transcript.video_id)
        if preset is not None:
            return list(preset)
        return rule_based_extract(transcript, genres=list(genres))
