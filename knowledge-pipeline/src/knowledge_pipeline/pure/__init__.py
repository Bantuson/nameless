"""Pure core — deterministic, I/O-free functions; the testable heart of the ingestion stage.

  * :mod:`query_grid`     — (genre x stage) grid + artist anchors -> discovery queries (KNOW-01).
  * :mod:`extractability` — transcript -> 0..1 score + flags + verdict (KNOW-03); the visual-only gate.
  * :mod:`fallback`       — caption availability -> use-captions | ASR | reject (KNOW-03).
  * :mod:`snapshot`       — transcript + injected now -> sha256 + retrieval-date record (KNOW-02).
  * :mod:`dedup`          — de-duplicate discovery results + drop already-ingested (idempotency).
  * :mod:`captions`       — pure VTT/SRT parser for the yt-dlp subtitle fallback path.
  * :mod:`vocab`          — the lexicons/patterns the scorer reads (data, not logic).

Nothing here imports an adapter, a network client, or sqlite. Side effects live at the boundary.
"""

from .dedup import dedup_already_ingested, dedup_video_refs
from .extractability import DEFAULT_CONFIG, ScoringConfig, extractability_score
from .fallback import fallback_decision
from .query_grid import grid_coverage, query_grid
from .snapshot import content_hash, snapshot_record

__all__ = [
    "query_grid",
    "grid_coverage",
    "extractability_score",
    "ScoringConfig",
    "DEFAULT_CONFIG",
    "fallback_decision",
    "snapshot_record",
    "content_hash",
    "dedup_video_refs",
    "dedup_already_ingested",
]
