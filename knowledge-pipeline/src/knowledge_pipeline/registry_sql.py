"""The ``registry.sqlite`` schema — build-time corpus provenance, DELIBERATELY OFF the runtime Postgres.

Research ARCHITECTURE.md is explicit: the production-knowledge layer shares NO tables and NO read path
with the runtime fragment graph. The corpus registry is build-time audit data that the runtime agent
never queries — so it lives in a pipeline-local SQLite file, not Postgres. This module is the single
source of truth for that schema (DDL as code, applied by :meth:`FilesystemCorpusStore.init_schema`).

Three tables, mirroring the three domain artifacts of one ingested video:
  * ``sources``        — the video + HOW discovery found it (grid cell / artist anchor) [KNOW-01 provenance].
  * ``snapshots``      — the immutable evidence fingerprint: content sha256 + retrieval date + span [KNOW-02].
  * ``extractability`` — the gate result: score, component sub-scores, verdict, flags [KNOW-03].

The full timestamped transcript text lives in a snapshot FILE on disk (see :data:`SNAPSHOT_LAYOUT`),
NOT in sqlite — the registry stays lean and token-cheap, and the heavy text is loaded by ID only when
Phase 4 actually mines it. ``video_id`` is the primary key everywhere (idempotent upsert on re-run).
"""

from __future__ import annotations

# Filesystem layout the FilesystemCorpusStore materializes (documented so it is reviewable in one place):
#
#   <corpus_root>/
#     registry.sqlite                 # the three tables below
#     snapshots/
#       <video_id>.json               # { video_id, caption_source, language, fetched_via,
#                                       #   content_sha256, retrieval_date, segments:[{start_s,duration_s,text}] }
#
# The snapshot JSON is the immutable evidence: full per-segment timestamps survive a YouTube takedown so
# Phase 4 can still cite `video_id @ ts`. The registry rows are the compact index over those files.
SNAPSHOT_LAYOUT = "snapshots/<video_id>.json"

SCHEMA_VERSION = 1

# PRAGMAs applied on connect — WAL for safe incremental re-runs, FK enforcement for referential integrity.
CONNECT_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA foreign_keys=ON;",
)

DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per UNIQUE candidate video + the discovery provenance that surfaced it (KNOW-01).
CREATE TABLE IF NOT EXISTS sources (
    video_id      TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    channel       TEXT,
    url           TEXT NOT NULL,
    duration_s    INTEGER,
    query_origin  TEXT,              -- comma-joined union of queries that surfaced it (dedup merge)
    genre         TEXT,              -- north-star GENRES label (for --by-genre + KNOW-04 concentration)
    stage         TEXT,              -- production STAGES label
    artist_anchor TEXT,              -- the anchor name, if found via an artist search
    ingested_at   TEXT NOT NULL      -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_sources_genre ON sources(genre);

-- The immutable evidence fingerprint captured at ingest (KNOW-02). Full segments live in the file.
CREATE TABLE IF NOT EXISTS snapshots (
    video_id        TEXT PRIMARY KEY REFERENCES sources(video_id) ON DELETE CASCADE,
    content_sha256  TEXT NOT NULL,
    retrieval_date  TEXT NOT NULL,   -- ISO-8601; "when WE retrieved it" (injected clock)
    caption_source  TEXT NOT NULL,   -- manual | auto | asr | none
    language        TEXT NOT NULL DEFAULT 'en',
    segment_count   INTEGER NOT NULL DEFAULT 0,
    char_count      INTEGER NOT NULL DEFAULT 0,
    first_segment_s REAL,
    last_segment_s  REAL,
    snapshot_path   TEXT NOT NULL    -- relative path to the snapshots/<video_id>.json evidence file
);

-- The extractability gate result (KNOW-03): score + component sub-scores + verdict + flags.
CREATE TABLE IF NOT EXISTS extractability (
    video_id              TEXT PRIMARY KEY REFERENCES sources(video_id) ON DELETE CASCADE,
    score                 REAL NOT NULL,
    verdict               TEXT NOT NULL,   -- keep | low_signal | reject
    caption_source_weight REAL NOT NULL,
    word_density          REAL NOT NULL,
    vocab_presence        REAL NOT NULL,
    actionable_ratio      REAL NOT NULL,
    visual_only_penalty   REAL NOT NULL,
    word_count            INTEGER NOT NULL DEFAULT 0,
    vocab_hits            INTEGER NOT NULL DEFAULT 0,
    flags_json            TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_extractability_verdict ON extractability(verdict);
CREATE INDEX IF NOT EXISTS idx_extractability_score   ON extractability(score);
"""
