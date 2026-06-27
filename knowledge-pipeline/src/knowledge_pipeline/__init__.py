"""Nameless offline knowledge pipeline — ingestion stage (Phase 3).

A BUILD-TIME authoring tool (sibling of ``workers/``, NOT a runtime plane): discover north-star
production tutorials, fetch transcripts LOCALLY (throttled) with snapshot-on-ingest, fall back to ASR
when captions are missing/poor, score each source's extractability (flagging visual-only/low-signal
rather than faking it), and register everything in a local ``registry.sqlite`` corpus the later stages
cite. Requirements: KNOW-01..04.

Architecture: ports + adapters (real, heavy-imports-lazy; and deterministic fakes) + a pure core +
pure orchestration — mirroring the Phase-2 ``workers/`` testability pattern. See README.md / LEARNING.md.

Phase 4 EXTENDS this same package with cited claim mining + cross-reference (KNOW-05/06): a typed
``Claim`` / ``ClaimCluster`` domain, a ``ClaimExtractor`` (real Claude tool-use + deterministic fake),
pure ``verify_citation`` / ``cross_reference`` / ``dedup_claims``, a ``ClaimStore`` (sqlite + in-memory),
the ``MiningPipeline``, and the ``claims`` CLI — extraction + grouping only, ZERO synthesis (Phase 5).
"""

__version__ = "0.4.0"
