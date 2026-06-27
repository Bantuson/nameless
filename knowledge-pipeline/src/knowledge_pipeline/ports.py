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
from typing import Iterable, Optional, Protocol, runtime_checkable

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


# Convenience: the set of network-ish ports a live ingest needs, documented in one place.
__all__ = [
    "DiscoverySource",
    "TranscriptFetcher",
    "Transcriber",
    "CorpusStore",
    "Clock",
    "RateLimiter",
]
