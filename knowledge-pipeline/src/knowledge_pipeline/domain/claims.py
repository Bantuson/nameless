"""Typed claim domain (pydantic v2) — the EXTRACTION-ONLY boundary of Phase 4 (KNOW-05/06).

Two types, and a hard discipline encoded in their *shape*:

  * :class:`Claim` — one **atomic, individually-cited** assertion of craft. Every field is either
    *extracted* (what a source actually said: ``claim_text``, ``technique``, ``stage``, ``genre``,
    ``stance``, ``confidence``) or *citation* (``source_video_id``, ``timestamp_ms``, ``quote``,
    ``caption_source``). There is **no synthesized / derived / opinionated field** — no "recommended
    default", no merged "best way". That absence is the Phase-4 boundary, and it is a *tested invariant*
    (see ``tests/test_claim_schema.py`` + ``test_cross_reference.py``): Phase 4 extracts and groups;
    Phase 5 is the only place a default may be decided *on top of* this preserved evidence.

  * :class:`ClaimCluster` — claims about ONE topic, grouped into ``consensus`` (an uncontested topic:
    corroborating claims) XOR ``conflicts`` (a contested topic: claims that disagree, e.g. amapiano
    log-drum FLEX-synth vs layered-samples — **both sides preserved, never collapsed**). Corroboration
    counts **distinct sources**, not repeats (KNOW-06).

Why ``id`` / ``topic`` are *computed* (not stored input) fields: they are pure functions of the claim's
own content (see :mod:`knowledge_pipeline.domain.keys`). The model can never assign or drift them — the
id IS the content hash of the citation anchor + text, the topic IS ``(stage, technique)`` normalized.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .keys import compute_claim_id, normalize_key, topic_key
from .models import CaptionSource


class Claim(BaseModel):
    """One atomic, individually-cited production claim — the KNOW-05 unit. Frozen + content-addressed.

    INVARIANT (the no-synthesis boundary): every field here is extracted-or-citation. Nothing is a
    synthesized recommendation. The ``quote`` is VERBATIM from a single snapshot segment and the
    ``timestamp_ms`` points at that segment — together they are the citation that Phase 5's hard gate
    will re-verify. ``caption_source`` rides along because an ``auto``-caption claim is weaker evidence
    than a ``manual``/``asr`` one (PITFALLS #1: auto-captions corrupt the very numbers that matter).
    """

    model_config = ConfigDict(frozen=True)

    # ---- extracted (what the source said) ----
    claim_text: str                       # the atomic, single-technique statement
    technique: str                        # the specific technique / question, e.g. "log-drum-sound-source"
    stage: str                            # production stage (one of domain.genres.STAGES, ideally)
    genre: list[str] = Field(default_factory=list)  # genres this claim is evidenced for (may be empty)
    stance: Optional[str] = None          # the position taken WHEN the technique admits competing answers
    confidence: float = Field(ge=0.0, le=1.0)        # extractor-calibrated 0..1 (see prompt rubric)

    # ---- citation (where it came from — the auditable anchor) ----
    source_video_id: str
    timestamp_ms: int = Field(ge=0)       # the cited segment's start, in ms
    quote: str                            # VERBATIM text copied from that segment
    caption_source: CaptionSource = CaptionSource.NONE

    # ---- computed (pure functions of the above; never model-supplied) ----
    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """Content-addressed id: sha1(video_id | timestamp_ms | text | stance | technique). Idempotent.

        Stance + technique are in the basis so opposing same-source claims keep distinct ids (no
        conflict-collapse — see :func:`knowledge_pipeline.domain.keys.compute_claim_id`).
        """
        return compute_claim_id(
            self.source_video_id,
            self.timestamp_ms,
            self.claim_text,
            stance=self.stance,
            technique=self.technique,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def topic(self) -> str:
        """The cross-reference grouping key ``"<stage>/<technique>"`` (normalized)."""
        return topic_key(self.stage, self.technique)

    @property
    def stance_key(self) -> str:
        """Normalized stance ('' when the claim takes no position). Not serialized."""
        return normalize_key(self.stance) if self.stance else ""


class ClaimCluster(BaseModel):
    """All claims about one topic — consensus XOR preserved conflict (KNOW-06). Frozen.

    A topic is **contested** iff ≥2 *distinct* stances appear among its claims. The partition is
    deliberately exclusive and un-opinionated:

      * uncontested topic  -> every claim is ``consensus`` (corroboration), ``conflicts`` empty.
      * contested topic    -> every claim is ``conflicts`` (**both sides preserved**), ``consensus``
                              empty. Phase 4 does NOT pick a winner — that decision is Phase 5's, made
                              *on top of* this evidence, never by deleting a side here.

    ``distinct_consensus_sources`` is the corroboration signal (counts unique ``source_video_id``,
    so one creator repeating themselves does not inflate it). :meth:`sides` groups the conflict by
    stance so the two (or more) camps are inspectable.
    """

    model_config = ConfigDict(frozen=True)

    topic: str                            # "<stage>/<technique>" — the grouping key
    stage: str
    technique: str
    genre: list[str] = Field(default_factory=list)   # union of member genres (sorted, deduped)
    consensus: list[Claim] = Field(default_factory=list)
    conflicts: list[Claim] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_contested(self) -> bool:
        return len(self.conflicts) > 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def distinct_consensus_sources(self) -> int:
        return len({c.source_video_id for c in self.consensus})

    @computed_field  # type: ignore[prop-decorator]
    @property
    def distinct_conflict_sources(self) -> int:
        return len({c.source_video_id for c in self.conflicts})

    @computed_field  # type: ignore[prop-decorator]
    @property
    def member_count(self) -> int:
        return len(self.consensus) + len(self.conflicts)

    def sides(self) -> dict[str, list[Claim]]:
        """Group the contested claims by normalized stance ('unspecified' for neutral). Not serialized.

        This is how the CLI shows "FLEX-synth camp vs layered-samples camp" without the cluster having
        to pick one. For an uncontested cluster this returns ``{}`` (there are no conflict members).
        """
        out: dict[str, list[Claim]] = {}
        for c in self.conflicts:
            key = c.stance_key or "unspecified"
            out.setdefault(key, []).append(c)
        return out


class ClaimStats(BaseModel):
    """Compact roll-up of the mined claim layer — drives ``claims stats`` and the no-bloat CLI contract."""

    total_claims: int = 0
    total_clusters: int = 0
    contested_clusters: int = 0
    citation_verified: int = 0
    by_stage: dict[str, int] = Field(default_factory=dict)
    by_genre: dict[str, int] = Field(default_factory=dict)
    by_caption_source: dict[str, int] = Field(default_factory=dict)
