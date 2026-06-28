"""The authored-skill schema — EXTENDS the same local ``registry.sqlite`` (KNOW-09/11 persistence).

Phase 5 writes into the SAME ``registry.sqlite`` the Phase-3/4 stages produced: the claims/clusters are
the input, the authored skills are the output of synthesizing them. Additive (``CREATE TABLE IF NOT
EXISTS``) so it coexists with ``sources`` / ``snapshots`` / ``extractability`` / ``claims`` / ``clusters``
and applies cleanly to a fresh DB (the offline ``--fixtures`` path). Still deliberately OFF the runtime
Postgres — build-time authoring data; the runtime agent loads the emitted SKILL.md FILES, not this table.

Two tables:
  * ``skills``          — one row per authored ``(stage, genre)`` cell: identity, status (draft|promoted),
                          the on-disk ``relpath`` + ``body_sha256``, and the audit roll-up (distinct
                          sources, default corroboration, contested-default) the spot-audit reads.
  * ``skill_citations`` — the skill↔claim receipts (which claims a skill cites, in which section/stance),
                          so a skill's evidence trail is queryable from the registry without re-parsing the
                          SKILL.md.

The full SKILL.md body lives in the FILE on disk (the durable, human-/agent-readable artifact); the
registry stores ``body_sha256`` + ``relpath`` (drift-detectable, lean). The in-memory fake keeps the body
in object form so both stores round-trip identically.
"""

from __future__ import annotations

SKILLS_SCHEMA_VERSION = 2   # v2: + skills.grounded (KNOW-10 sparse-genre skills, LOW by construction)

SKILLS_DDL = """
CREATE TABLE IF NOT EXISTS skill_schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per authored (stage, genre) skill (KNOW-09). id = cell-addressed => idempotent re-synthesis.
CREATE TABLE IF NOT EXISTS skills (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    stage                TEXT NOT NULL,
    genre                TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'draft',   -- draft | promoted (human-gated)
    relpath              TEXT NOT NULL,                   -- skills/production/<stage>/<genre>/SKILL.md
    prompt_version       TEXT NOT NULL DEFAULT '',
    grounded             INTEGER NOT NULL DEFAULT 0,      -- KNOW-10: decomposition+audio grounded ⇒ LOW conf
    citation_count       INTEGER NOT NULL DEFAULT 0,
    distinct_sources     INTEGER NOT NULL DEFAULT 0,
    default_source_count INTEGER NOT NULL DEFAULT 0,
    default_contested    INTEGER NOT NULL DEFAULT 0,
    consensus_topics     INTEGER NOT NULL DEFAULT 0,
    conflict_topics      INTEGER NOT NULL DEFAULT 0,
    body_sha256          TEXT NOT NULL DEFAULT '',
    authored_at          TEXT NOT NULL,                   -- ISO-8601 UTC
    promoted_at          TEXT                             -- ISO-8601 UTC, set on promotion
);

CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_genre  ON skills(genre);
CREATE INDEX IF NOT EXISTS idx_skills_stage  ON skills(stage);

-- The skill<->claim receipts: which claims a skill cites, in which layer/stance (KNOW-08 evidence trail).
CREATE TABLE IF NOT EXISTS skill_citations (
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL,
    kind     TEXT NOT NULL,        -- default | consensus | conflict
    stance   TEXT,
    topic    TEXT NOT NULL,
    PRIMARY KEY (skill_id, claim_id, kind, topic)
);

CREATE INDEX IF NOT EXISTS idx_skill_citations_claim ON skill_citations(claim_id);
"""


def ensure_skill_columns(conn) -> None:
    """Idempotently add columns introduced after v1 to a pre-existing ``skills`` table (additive migration).

    ``CREATE TABLE IF NOT EXISTS`` gives a FRESH DB every column, but a registry created by an earlier
    schema version would be missing ``grounded``. This adds it if absent (SQLite ``ALTER TABLE ADD COLUMN``
    is cheap + non-destructive), so re-opening an existing corpus DB never KeyErrors on the new column.
    """
    have = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
    if "grounded" not in have:
        conn.execute("ALTER TABLE skills ADD COLUMN grounded INTEGER NOT NULL DEFAULT 0")
