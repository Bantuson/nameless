"""Pure core — deterministic, I/O-free functions; the testable heart of the ingestion stage.

  * :mod:`query_grid`     — (genre x stage) grid + artist anchors -> discovery queries (KNOW-01).
  * :mod:`extractability` — transcript -> 0..1 score + flags + verdict (KNOW-03); the visual-only gate.
  * :mod:`fallback`       — caption availability -> use-captions | ASR | reject (KNOW-03).
  * :mod:`snapshot`       — transcript + injected now -> sha256 + retrieval-date record (KNOW-02).
  * :mod:`dedup`          — de-duplicate discovery results + drop already-ingested (idempotency).
  * :mod:`captions`       — pure VTT/SRT parser for the yt-dlp subtitle fallback path.
  * :mod:`vocab`          — the lexicons/patterns the scorer reads (data, not logic).

Phase-4 pure core (KNOW-05/06) — extraction + grouping, ZERO synthesis, no ``anthropic``, no I/O:
  * :mod:`extraction_schema` — the ``emit_claims`` tool schema + normalization (model output -> Claim)
                               + the deterministic rule-based fallback extractor.
  * :mod:`citation`          — ``verify_citation`` (quote occurs at/near the cited ts; the P5-gate kernel).
  * :mod:`cross_reference`   — ``cross_reference`` (consensus XOR preserved conflict; distinct sources).
  * :mod:`claim_dedup`       — ``dedup_claims`` (exact + same-source near-dup; never cross-source).

Nothing here imports an adapter, a network client, or sqlite. Side effects live at the boundary.
"""

from .citation import CitationCheck, verify_citation
from .claim_dedup import dedup_claims
from .cross_reference import cross_reference
from .dedup import dedup_already_ingested, dedup_video_refs
from .extractability import DEFAULT_CONFIG, ScoringConfig, extractability_score
from .extraction_schema import (
    EXTRACTION_TOOL_NAME,
    EXTRACTION_TOOL_SCHEMA,
    parse_extractor_output,
    rule_based_extract,
)
from .fallback import fallback_decision
from .query_grid import grid_coverage, query_grid
from .snapshot import content_hash, snapshot_record

__all__ = [
    # Phase 3
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
    # Phase 4
    "verify_citation",
    "CitationCheck",
    "cross_reference",
    "dedup_claims",
    "parse_extractor_output",
    "rule_based_extract",
    "EXTRACTION_TOOL_NAME",
    "EXTRACTION_TOOL_SCHEMA",
]
