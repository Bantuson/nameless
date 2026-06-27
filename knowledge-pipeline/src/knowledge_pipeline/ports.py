"""Ports — the ``typing.Protocol`` seam between the ingestion orchestration and the outside world.

Every network/heavy/time dependency sits behind one of these structural interfaces, each with a REAL
adapter (``adapters/*.py``, heavy imports LAZY) and a deterministic FAKE. The pipeline
(:class:`~knowledge_pipeline.pipeline.IngestPipeline`) depends only on these protocols, never on a
concrete adapter — so the whole discover -> dedup -> fetch+fallback -> snapshot -> score -> register flow
runs in tests with no yt-dlp / youtube-transcript-api / faster-whisper / real clock.

Ports (mirrors the Phase-3 CONTEXT decisions):
  * :class:`DiscoverySource`    — a query -> candidate ``VideoRef``s (yt-dlp ytsearch / fixture fake).
  * :class:`TranscriptFetcher`  — a ``VideoRef`` -> ``CaptionFetch`` (youtube-transcript-api primary,
                                  yt-dlp subs secondary / fixture fake).
  * :class:`Transcriber`        — a ``VideoRef`` -> ``RawTranscript`` (faster-whisper / fixed-text fake);
                                  the ASR fallback, invoked ONLY when ``fallback_decision`` says so.
  * :class:`CorpusStore`        — snapshot + registry persistence (filesystem + registry.sqlite / in-mem).
  * :class:`Clock`              — ``now`` / ``monotonic`` / ``sleep`` (system / fake virtual time).
  * :class:`RateLimiter`        — ``acquire`` throttle gate (interval+jitter over a Clock / no-op fake).

Mirrors the Phase-2 ``workers/`` pattern (ports + real+fake adapters + lazy heavy imports) exactly.
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable, Optional, Protocol, Sequence, runtime_checkable

from .domain.claims import Claim, ClaimCluster, ClaimStats
from .domain.models import (
    CaptionFetch,
    CorpusEntry,
    CorpusStats,
    DiscoveryQuery,
    RawTranscript,
    SnapshotRecord,
    VideoRef,
    Verdict,
)
from .domain.skills import AuthoredSkill, ProductionCell, SkillDraft, SkillStats, SkillStatus


@runtime_checkable
class DiscoverySource(Protocol):
    """Resolve a discovery query into candidate videos (KNOW-01).

    The real adapter runs ``yt-dlp`` ``ytsearch{limit}:{query}`` with flat extraction (IDs/titles only,
    no media download). The fake returns a fixture list. Both must stamp the query's genre/stage/anchor
    onto each :class:`VideoRef` (discovery provenance) so corpus concentration stays inspectable.
    """

    def search(self, query: DiscoveryQuery, limit: int) -> list[VideoRef]: ...


@runtime_checkable
class TranscriptFetcher(Protocol):
    """Fetch the best available captions for a video + report what tracks exist (KNOW-02).

    Returns a :class:`CaptionFetch` carrying the availability (for :func:`fallback_decision`) and the
    best transcript actually pulled (manual preferred over auto), or ``None`` transcript when only ASR
    can recover anything. The real adapter is youtube-transcript-api primary, yt-dlp subs secondary.
    """

    def fetch(self, video: VideoRef) -> CaptionFetch: ...


@runtime_checkable
class Transcriber(Protocol):
    """ASR fallback: a video -> a timestamped :class:`RawTranscript` with ``caption_source = asr``.

    The real adapter pulls audio with yt-dlp and transcribes with faster-whisper (large-v3). Invoked
    ONLY on the fallback path (``fallback_decision`` returned FETCH_AND_ASR) — Whisper is GPU cost, so
    we never run it when usable captions already exist (PITFALLS: "only re-transcribe high-value videos").
    """

    def transcribe(self, video: VideoRef) -> RawTranscript: ...


@runtime_checkable
class CorpusStore(Protocol):
    """Snapshot + registry persistence — the corpus the later stages cite (KNOW-02/KNOW-04).

    The real adapter writes immutable snapshot files (full timestamped segments) + a ``registry.sqlite``
    of compact rows; the fake is in-memory. Both back the same contract, so a pipeline/registry test runs
    with no filesystem. ``has`` powers idempotent re-runs; ``load_snapshot`` is how Phase 4 re-reads the
    timestamped text to mine ``video_id @ ts`` claims after a takedown.
    """

    def init_schema(self) -> None: ...

    def has(self, video_id: str) -> bool: ...

    def known_ids(self) -> set[str]: ...

    def write_snapshot(self, transcript: RawTranscript, record: SnapshotRecord) -> str:
        """Persist the full timestamped transcript immutably; return its snapshot id/path."""
        ...

    def register(self, entry: CorpusEntry) -> None:
        """Upsert one compact registry row (video + snapshot fingerprint + extractability)."""
        ...

    def get(self, video_id: str) -> Optional[CorpusEntry]: ...

    def load_snapshot(self, video_id: str) -> Optional[RawTranscript]:
        """Re-read the immutable snapshot (full segments) — the durable evidence for Phase-4 citation."""
        ...

    def list_entries(
        self,
        *,
        genre: Optional[str] = None,
        verdict: Optional[Verdict] = None,
        min_score: Optional[float] = None,
        order_by_score: bool = False,
    ) -> list[CorpusEntry]: ...

    def stats(self) -> CorpusStats: ...


@runtime_checkable
class Clock(Protocol):
    """Time as a port — so retrieval dates and throttling are deterministic in tests.

    ``now`` stamps snapshot retrieval dates (injected into the pure ``snapshot_record``); ``monotonic``
    + ``sleep`` drive the rate limiter. The fake advances VIRTUAL time on ``sleep`` (no real waiting), so
    a throttle test asserting "waited 2s between requests" runs instantly and deterministically.
    """

    def now(self) -> _dt.datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class RateLimiter(Protocol):
    """A throttle gate. ``acquire`` blocks (via the Clock) until the next request is allowed (KNOW-02).

    Local-first ingestion must be slow and polite to avoid YouTube's 429/bot defenses (PITFALLS #2).
    Behind this port so the pipeline calls ``acquire`` before every network step, and tests inject a
    fake-clock-backed limiter (asserts the spacing) or a no-op limiter (fast paths).
    """

    def acquire(self) -> None: ...


# ============================================================================================
# Phase-4 ports — claim mining + cross-reference (KNOW-05/06). Same ports-and-adapters discipline:
# each has a REAL adapter (heavy import LAZY) AND a deterministic FAKE, and MiningPipeline depends only
# on these protocols. The Anthropic call is the heavy/external leaf (key + tokens) => env-gated.
# ============================================================================================


@runtime_checkable
class ClaimExtractor(Protocol):
    """Extract atomic, individually-cited claims from one transcript (KNOW-05).

    The real adapter is Claude (Anthropic SDK) with **structured tool-use** (``emit_claims``, forced
    ``tool_choice``) — reliable LLM output comes from structure, not prose; the SDK import is LAZY and the
    call is env-gated (``ANTHROPIC_API_KEY`` + tokens). The fake is a deterministic, rule-based extractor
    over the producer-jargon lexicon, so the whole mining flow runs in tests with no API.

    ``genres`` is the discovery-provenance context (the grid/anchor genre that surfaced the video); it
    seeds a claim's ``genre`` only when the source itself does not tie the claim to a genre. The extractor
    must never invent numbers or synthesize — it emits cited atoms only.
    """

    def extract(self, transcript: RawTranscript, *, genres: Iterable[str] = ()) -> list[Claim]: ...


@runtime_checkable
class SimilarityIndex(Protocol):
    """Optional text-similarity (0..1) for semantic dedup refinement (KNOW-06).

    Real = embeddings (cosine); fake = keyword/Jaccard. The pure cross-reference + default dedup do NOT
    require it (they use deterministic topic keys + exact text) — semantic similarity is a pluggable
    refinement so the core stays testable. Whatever the impl, it only ever collapses SAME-source
    near-paraphrases; it never merges across sources (that would fabricate/erase corroboration).
    """

    def similarity(self, a: str, b: str) -> float: ...


@runtime_checkable
class ClaimStore(Protocol):
    """Persist + query claims and clusters (KNOW-05/06). Real = sqlite (extends registry); fake = in-memory.

    ``upsert_claims`` is idempotent on the content-addressed claim id; ``replace_clusters`` rewrites the
    cluster set wholesale (clusters are a pure function of ALL claims, so they are recomputed globally
    after every mine and replaced, never accreted). ``get_claim`` powers ``claims show <id>`` (trace a
    claim back to its source quote + timestamp + video).
    """

    def init_schema(self) -> None: ...

    def upsert_claims(self, claims: Iterable[Claim], *, verified: Optional[dict[str, bool]] = None) -> int:
        """Insert/replace claims by id; ``verified`` maps claim id -> citation-verification result."""
        ...

    def replace_clusters(self, clusters: Iterable[ClaimCluster]) -> int:
        """Clear and rewrite all clusters + members (clusters are global over the full claim set)."""
        ...

    def get_claim(self, claim_id: str) -> Optional[Claim]: ...

    def list_claims(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        technique: Optional[str] = None,
        source_video_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> list[Claim]: ...

    def get_cluster(self, topic: str) -> Optional[ClaimCluster]: ...

    def list_clusters(
        self,
        *,
        contested_only: bool = False,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
    ) -> list[ClaimCluster]: ...

    def stats(self) -> ClaimStats: ...


# ============================================================================================
# Phase-5 ports — skill synthesis + authored-skill persistence (KNOW-07/08/09/11). Same discipline:
# the REAL SkillSynthesizer is Claude (heavy import LAZY, env-gated); its FAKE is a deterministic
# template. SynthesisPipeline depends only on these protocols. The citation GATE is a pure function, not
# a port — it must run identically for the real and fake synthesizer (you never want a "fake gate").
# ============================================================================================


@runtime_checkable
class SkillSynthesizer(Protocol):
    """Author a layered :class:`SkillDraft` for one cell over its clusters (KNOW-07).

    The real adapter is Claude (Anthropic SDK) with forced ``emit_skill`` tool-use, constrained by the
    versioned synthesis prompt to synthesize ONLY over the provided claims and never invent a number; its
    output is re-grounded (citations rebuilt from the real claims) and then must still pass the citation
    gate. The SDK import is LAZY and the call is env-gated. The fake is the deterministic
    :func:`~knowledge_pipeline.pure.synthesis_template.template_synthesize` — structurally incapable of
    introducing a claim/number not in ``clusters`` — so the whole synthesis flow runs in tests with no API.
    """

    def synthesize(self, cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> SkillDraft: ...


@runtime_checkable
class SkillStore(Protocol):
    """Persist + query authored skills and their draft/promoted status (KNOW-09/11).

    Real = filesystem (``skills/production/<stage>/<genre>/SKILL.md``) + a registry extending
    ``registry.sqlite``; fake = in-memory. ``upsert_skill`` is idempotent on the cell-addressed skill id
    (re-synthesis replaces in place). ``set_status`` is the ONLY status mutator — the human-gated
    ``draft -> promoted`` transition flows through it (and rewrites the file's frontmatter banner).
    """

    def init_schema(self) -> None: ...

    def upsert_skill(self, skill: AuthoredSkill) -> None:
        """Insert/replace a skill by id; the filesystem adapter also (re)writes its SKILL.md file."""
        ...

    def get_skill(self, skill_id: str) -> Optional[AuthoredSkill]: ...

    def set_status(self, skill_id: str, status: SkillStatus) -> Optional[AuthoredSkill]:
        """Flip a skill's status (the human-gated promotion); returns the updated skill or ``None``."""
        ...

    def list_skills(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        status: Optional[SkillStatus] = None,
    ) -> list[AuthoredSkill]: ...

    def stats(self) -> SkillStats: ...


# Convenience: the ports each plane needs, documented in one place.
__all__ = [
    # Phase 3 — ingestion
    "DiscoverySource",
    "TranscriptFetcher",
    "Transcriber",
    "CorpusStore",
    "Clock",
    "RateLimiter",
    # Phase 4 — claim mining
    "ClaimExtractor",
    "SimilarityIndex",
    "ClaimStore",
    # Phase 5 — skill synthesis
    "SkillSynthesizer",
    "SkillStore",
]
