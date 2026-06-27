"""The claims/clusters schema — EXTENDS the Phase-3 ``registry.sqlite`` (KNOW-05/06 persistence).

Phase 4 writes into the SAME local ``registry.sqlite`` the Phase-3 corpus stage produced (the corpus is
the input; the claims are the output of mining it). These tables are additive (``CREATE TABLE IF NOT
EXISTS``) so they coexist with ``sources`` / ``snapshots`` / ``extractability`` and apply cleanly to a
fresh DB too (the offline ``--fixtures`` path). Still deliberately OFF the runtime Postgres — this is
build-time audit data the runtime agent never queries (research ARCHITECTURE.md).

Three tables mirror the three Phase-4 artifacts:
  * ``claims``          — one row per atomic cited claim (KNOW-05). ``id`` is the content hash (idempotent).
  * ``clusters``        — one row per topic, with its consensus/conflict roll-up (KNOW-06).
  * ``cluster_members`` — the claim↔cluster edge, tagged ``side`` (consensus|conflict) + ``stance`` so the
                          two camps of a contested topic are reconstructable.

The full transcript text still lives in the Phase-3 snapshot files; a claim stores only its verbatim
``quote`` + ``timestamp_ms`` + ``source_video_id`` — enough to trace ``claims show <id>`` back to source
without re-opening the snapshot, and lean enough to stay token-cheap.
"""

from __future__ import annotations

CLAIMS_SCHEMA_VERSION = 1

CLAIMS_DDL = """
CREATE TABLE IF NOT EXISTS claim_schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per atomic, individually-cited claim (KNOW-05). id = content hash => idempotent upsert.
CREATE TABLE IF NOT EXISTS claims (
    id                TEXT PRIMARY KEY,
    claim_text        TEXT NOT NULL,
    technique         TEXT NOT NULL,
    stage             TEXT NOT NULL,
    genre_json        TEXT NOT NULL DEFAULT '[]',
    stance            TEXT,                       -- the position taken on a contested technique (nullable)
    confidence        REAL NOT NULL,
    source_video_id   TEXT NOT NULL,
    timestamp_ms      INTEGER NOT NULL,
    quote             TEXT NOT NULL,              -- verbatim citation substrate
    caption_source    TEXT NOT NULL,              -- manual | auto | asr | none (evidence trust)
    topic             TEXT NOT NULL,              -- "<stage>/<technique>" (the cross-ref key)
    citation_verified INTEGER NOT NULL DEFAULT 0, -- pure verify_citation result at mine time (precursor to P5 gate)
    mined_at          TEXT NOT NULL               -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_claims_stage  ON claims(stage);
CREATE INDEX IF NOT EXISTS idx_claims_topic  ON claims(topic);
CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_video_id);

-- One row per topic cluster (KNOW-06): consensus XOR preserved conflict, rolled up.
CREATE TABLE IF NOT EXISTS clusters (
    topic                      TEXT PRIMARY KEY,
    stage                      TEXT NOT NULL,
    technique                  TEXT NOT NULL,
    genre_json                 TEXT NOT NULL DEFAULT '[]',
    is_contested               INTEGER NOT NULL DEFAULT 0,
    consensus_count            INTEGER NOT NULL DEFAULT 0,
    conflict_count             INTEGER NOT NULL DEFAULT 0,
    distinct_consensus_sources INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_clusters_contested ON clusters(is_contested);
CREATE INDEX IF NOT EXISTS idx_clusters_stage     ON clusters(stage);

-- The claim<->cluster edge. side preserves which claims agree vs disagree; stance preserves the camp.
CREATE TABLE IF NOT EXISTS cluster_members (
    topic    TEXT NOT NULL REFERENCES clusters(topic) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id)      ON DELETE CASCADE,
    side     TEXT NOT NULL,                            -- 'consensus' | 'conflict'
    stance   TEXT,
    PRIMARY KEY (topic, claim_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_members_claim ON cluster_members(claim_id);
"""
