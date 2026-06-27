-- Nameless control plane — initial schema (Phase 1: Typed Capture Spine).
--
-- Applied with: DATABASE_URL=postgres://... cargo sqlx migrate run
--
-- The two enum types MUST stay in lockstep with the Rust enums in nameless-core:
--   * provenance      ↔ nameless_core::provenance::Provenance      (4 variants)
--   * fragment_state  ↔ nameless_core::state_machine::FragmentState (12 variants)
-- The repo adapter maps Rust → these enum labels by their snake_case `as_str()`/`from_db_str()`.

-- pgvector is enabled now so Phase 2 (features/embeddings) can add vector columns without a new
-- extension migration. Phase 1 adds NO embedding columns — deferred work is not pre-built.
create extension if not exists vector;

-- Where a fragment's audio came from (drives which lifecycle path it travels).
create type provenance as enum (
    'human_recorded',
    'ai_generated',
    'derived',
    'sampled'
);

-- The complete fragment lifecycle (PRD §7). Both the human/sampled path and the ai eval-gate path.
create type fragment_state as enum (
    'captured',
    'analyzing',
    'analyzed',
    'placed',
    'mixed',
    'rendered',
    'requested',
    'generating',
    'generated',
    'evaluating',
    'promoted',
    'rejected'
);

-- Projects — the container a fragment graph belongs to. Phase 1 keeps only the capture-relevant
-- columns; PRD target_key/tempo/genre/lufs land when arrangement work (M1) needs them.
create table projects (
    id            uuid primary key,
    title         text   not null,
    created_at_ms bigint not null
);

-- Fragments — the atomic unit of the graph. Audio is referenced by content-hash uri, never inline.
create table fragments (
    id                 uuid primary key,
    project_id         uuid not null references projects (id),
    kind               text not null,                 -- FragmentKind label (melody|hook|beat|...)
    provenance         provenance not null,
    audio_uri          text not null,                 -- SHA-256 content-hash object key (immutable)
    duration_ms        int,
    sample_rate        int,
    note_text          text not null,                 -- the intent channel + compact node summary
    state              fragment_state not null,
    parent_fragment_id uuid references fragments (id), -- lineage edge (null for a raw capture)
    created_at_ms      bigint not null
);

-- Read-path indexes for the Phase-1 list/show queries.
create index fragments_project_id_idx on fragments (project_id);
create index fragments_state_idx on fragments (state);
