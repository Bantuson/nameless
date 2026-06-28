-- Nameless control plane — Phase 8 schema delta (Stem Library + Attributed Sampling).
--
-- Applied with: DATABASE_URL=postgres://... cargo sqlx migrate run
-- (or psql -f) AFTER 0001..0003. Additive only.
--
-- A producer separates any uploaded track (the SAME `reference_tracks` row Phase 7 analyzes for
-- vibe) into a retained stem library, then promotes a stem to an attribution-complete `sampled`
-- fragment at any time. Two new tables + one enum:
--
--   1. stems              — Demucs stems of an uploaded track, retained indefinitely, browsable.
--   2. sample_attribution — the COMPLETE attribution bound to a `sampled` fragment.
--
-- The integrity boundary (SAMP-03) is enforced in TWO mutually-reinforcing places:
--   * Rust types: only a `CompleteAttribution` (every field non-Option) can be persisted, and the
--     state machine refuses to place a sampled fragment without one (crates/nameless-core/src/
--     attribution.rs + state_machine.rs::place). Incomplete-attribution placement is unrepresentable.
--   * This schema: every credited field on `sample_attribution` is NOT NULL. The DB cannot hold a
--     partial attribution row either — the type-level guarantee and the column constraints agree.
--
-- Writers (mirrors the Phase 2/7 split — Python writes the derived rows, Rust owns the graph):
--   * Python `DemucsStemSeparator` writes `stems` (one row per separated stem; audio retained in
--     object storage by content-hash, with separator_model+version provenance).
--   * Rust control plane writes `sample_attribution` (on `sample add`, after validating attribution
--     completeness) and creates the `sampled` fragment row.

-- ---------------------------------------------------------------------------------------------
-- Rights/clearance status of a sample's source — honest from day one (SAMP-04). Clearance GATING
-- is out of scope (v2); recording the status is cheap and makes a future commercial step tractable.
-- The system NEVER treats any value here as permission (the credits sheet states "attribution ≠
-- permission"). Must stay in lockstep with nameless_core::attribution::RightsStatus.
-- ---------------------------------------------------------------------------------------------
create type rights_status as enum (
    'copyrighted_uncleared',
    'royalty_free',
    'own_work',
    'unknown'
);

-- ---------------------------------------------------------------------------------------------
-- 1. stems — the persistent stem library (SAMP-01). One row per separated stem of an uploaded
--    track. Audio referenced by content-hash uri (immutable, retained indefinitely). stem_type is
--    the Demucs output label (vocals|drums|bass|other, plus piano|guitar under htdemucs_6s).
--    separator_model+version capture HOW the stem was isolated (provenance; swap to BS-RoFormer is
--    detectable). NO provenance / fragment_state / kind columns — a stem is not a fragment until it
--    is promoted.
-- ---------------------------------------------------------------------------------------------
create table stems (
    id                 uuid primary key,
    reference_track_id uuid not null references reference_tracks (id) on delete cascade,
    stem_type          text not null,             -- StemType label (vocals|drums|bass|other|piano|guitar)
    audio_uri          text not null,             -- SHA-256 content-hash object key of the stem audio
    separator_model    text not null,             -- e.g. 'htdemucs_ft' / 'htdemucs_6s'
    separator_version  text not null,             -- e.g. '4.0.1' — bumped ⇒ a re-separation is detectable
    duration_ms        int,
    sample_rate        int,
    created_at_ms      bigint not null,
    -- Re-separating the same track with the same (deterministic) model yields the same stem bytes,
    -- hence the same content-hash uri. This makes re-runs idempotent: the worker's insert hits this
    -- constraint and does nothing, rather than duplicating the stem library (Demucs is deterministic).
    constraint stems_track_audio_unique unique (reference_track_id, audio_uri)
);

-- Browse a track's stems (the `stems list <track>` read path).
create index stems_reference_track_idx on stems (reference_track_id, created_at_ms desc);

-- ---------------------------------------------------------------------------------------------
-- 2. sample_attribution — the COMPLETE attribution for a `sampled` fragment (SAMP-03/SAMP-05).
--    Present iff fragments.provenance = 'sampled'. EVERY credited field is NOT NULL — the DB mirror
--    of the Rust CompleteAttribution type (no partial row is representable). project_id is
--    denormalized onto the row so `credits <project>` enumerates a project's samples directly.
--    fragments.audio_uri for a sampled fragment points at the (full or trimmed) stem slice; the
--    [start_ms, end_ms) range here records which part of the stem was used.
-- ---------------------------------------------------------------------------------------------
create table sample_attribution (
    fragment_id        uuid primary key references fragments (id) on delete cascade,
    project_id         uuid not null references projects (id) on delete cascade,
    reference_track_id uuid not null references reference_tracks (id),
    stem_id            uuid not null references stems (id),
    source_title       text not null,             -- never blank (validated before insert)
    source_artist      text not null,
    stem_type          text not null,
    start_ms           int  not null,
    end_ms             int  not null,
    rights_status      rights_status not null,
    created_at_ms      bigint not null,
    -- The time range must be a positive span — the DB-level mirror of the completeness predicate.
    constraint sample_attribution_positive_span check (end_ms > start_ms)
);

-- Enumerate a project's samples for the credits sheet.
create index sample_attribution_project_idx on sample_attribution (project_id);
