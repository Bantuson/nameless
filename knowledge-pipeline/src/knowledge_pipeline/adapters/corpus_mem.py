"""InMemoryCorpusStore — the RAM-safe fake for :class:`~knowledge_pipeline.ports.CorpusStore`.

Backed by plain dicts; no filesystem, no sqlite. It is a FAITHFUL double for the filesystem+sqlite store:
same idempotency (``has`` / ``known_ids``), same snapshot round-trip (``write_snapshot`` /
``load_snapshot`` preserve the full timestamped segments), same filter/sort semantics on ``list_entries``,
and the same ``stats`` roll-up. So a pipeline/registry test written against this fake proves the behavior
the real store will reproduce — with zero I/O.
"""

from __future__ import annotations

from typing import Optional

from ..domain.models import (
    CorpusEntry,
    CorpusStats,
    RawTranscript,
    SnapshotRecord,
    Verdict,
)


class InMemoryCorpusStore:
    """An in-memory corpus: snapshots (full transcripts) + compact registry entries."""

    def __init__(self) -> None:
        self._snapshots: dict[str, RawTranscript] = {}
        self._entries: dict[str, CorpusEntry] = {}

    # ---- schema / idempotency ----
    def init_schema(self) -> None:
        return None

    def has(self, video_id: str) -> bool:
        return video_id in self._entries

    def known_ids(self) -> set[str]:
        return set(self._entries.keys())

    # ---- snapshot (immutable evidence) ----
    def write_snapshot(self, transcript: RawTranscript, record: SnapshotRecord) -> str:
        # store a copy so later mutation of the caller's object cannot corrupt the snapshot
        self._snapshots[transcript.video_id] = transcript.model_copy(deep=True)
        return f"mem://snapshots/{transcript.video_id}"

    def load_snapshot(self, video_id: str) -> Optional[RawTranscript]:
        snap = self._snapshots.get(video_id)
        return snap.model_copy(deep=True) if snap is not None else None

    # ---- registry ----
    def register(self, entry: CorpusEntry) -> None:
        self._entries[entry.video.video_id] = entry

    def get(self, video_id: str) -> Optional[CorpusEntry]:
        return self._entries.get(video_id)

    def list_entries(
        self,
        *,
        genre: Optional[str] = None,
        verdict: Optional[Verdict] = None,
        min_score: Optional[float] = None,
        order_by_score: bool = False,
    ) -> list[CorpusEntry]:
        rows = list(self._entries.values())
        if genre is not None:
            rows = [e for e in rows if e.video.genre == genre]
        if verdict is not None:
            rows = [e for e in rows if e.extractability.verdict is verdict]
        if min_score is not None:
            rows = [e for e in rows if e.extractability.score >= min_score]
        if order_by_score:
            rows.sort(key=lambda e: e.extractability.score, reverse=True)
        else:
            rows.sort(key=lambda e: e.ingested_at)
        return rows

    def stats(self) -> CorpusStats:
        by_verdict: dict[str, int] = {}
        by_genre: dict[str, int] = {}
        by_caption: dict[str, int] = {}
        for e in self._entries.values():
            v = e.extractability.verdict.value
            by_verdict[v] = by_verdict.get(v, 0) + 1
            g = e.video.genre or "unknown"
            by_genre[g] = by_genre.get(g, 0) + 1
            c = e.snapshot.caption_source.value
            by_caption[c] = by_caption.get(c, 0) + 1
        return CorpusStats(
            total=len(self._entries),
            by_verdict=by_verdict,
            by_genre=by_genre,
            by_caption_source=by_caption,
        )
