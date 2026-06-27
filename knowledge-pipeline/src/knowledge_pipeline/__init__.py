"""Nameless offline knowledge pipeline — ingestion stage (Phase 3).

A BUILD-TIME authoring tool (sibling of ``workers/``, NOT a runtime plane): discover north-star
production tutorials, fetch transcripts LOCALLY (throttled) with snapshot-on-ingest, fall back to ASR
when captions are missing/poor, score each source's extractability (flagging visual-only/low-signal
rather than faking it), and register everything in a local ``registry.sqlite`` corpus the later stages
cite. Requirements: KNOW-01..04.

Architecture: ports + adapters (real, heavy-imports-lazy; and deterministic fakes) + a pure core +
pure orchestration — mirroring the Phase-2 ``workers/`` testability pattern. See README.md / LEARNING.md.
"""

__version__ = "0.3.0"
