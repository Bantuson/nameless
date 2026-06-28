-- Nameless control plane — Phase 7 schema delta (Reference-Track Context).
--
-- Applied with: DATABASE_URL=postgres://... cargo sqlx migrate run
-- (or psql -f) AFTER 0001_init.sql + 0002_fragment_features.sql. Additive only.
--
-- A producer uploads a finished song they love; the system extracts its VIBE + measurable
-- NON-MELODIC sonic targets as project conditioning context — with cloning made STRUCTURALLY
-- impossible (REF-03). The whole non-cloning guarantee is enforced HERE at the schema level + in the
-- Rust types (crates/nameless-core/src/reference.rs, conditioning.rs):
--
--   * A reference track is a SEPARATE entity from `fragments`. It has no provenance, no
--     fragment_state, no kind — it can never enter the fragment lifecycle, so it is never placed,
--     mixed, or rendered into an arrangement (ARCHITECTURE.md Pattern 2 / Anti-Pattern 3).
--   * `reference_context` has ONLY non-melodic columns. There is DELIBERATELY no melody / chroma /
--     f0 / chord / structure / key column on it — there is nothing for generation to clone from.
--     What you cannot store, you cannot leak (PITFALLS.md Pitfall 6). Adding such a column would be
--     an explicit, reviewable migration — the asymmetry is typed, not conventional.
--
-- Writers (mirrors Phase 2's fragments-vs-fragment_features split):
--   * Rust control plane writes `reference_tracks` (on `reference upload`) and
--     `project_reference_context` (on `reference attach`).
--   * Python `RestrictedReferenceAnalyzer` writes `reference_context` (CLAP style embedding + genre
--     + tempo range + LUFS + tonal balance + stereo width + LLM vibe). The control plane only READS
--     it back as a compact summary for `reference show` — projecting `vector_dims(...)`, never the
--     embedding vector (the compact-output contract).

-- ---------------------------------------------------------------------------------------------
-- Role a reference plays for a project. Typed enum (not free text) so the link is exhaustively
-- matchable, mirroring the `provenance` / `fragment_state` enums. Both roles expose ONLY
-- non-melodic context; the role tunes emphasis (atmosphere vs. measurable targets), never content.
-- Must stay in lockstep with nameless_core::reference::ReferenceRole (as_str/from_db_str).
-- ---------------------------------------------------------------------------------------------
create type reference_role as enum (
    'vibe',
    'sonic_target'
);

-- ---------------------------------------------------------------------------------------------
-- 1. reference_tracks — uploaded finished songs. NOT fragments.
--    Audio is referenced by content-hash uri (immutable, by ID), retained in object storage (the
--    Phase-8 stem library shares this upload). No provenance / state / kind columns by design.
-- ---------------------------------------------------------------------------------------------
create table reference_tracks (
    id             uuid primary key,
    audio_uri      text   not null,           -- SHA-256 content-hash object key (immutable)
    title          text,                      -- optional label (credits/UI; never a target)
    artist         text,
    duration_ms    int,
    sample_rate    int,
    uploaded_at_ms bigint not null
);

-- ---------------------------------------------------------------------------------------------
-- 2. reference_context — extracted VIBE + measurable NON-MELODIC targets (one row per analyzed
--    reference). Written by the Python analyzer. NOTE the columns present, and — critically — the
--    columns ABSENT: there is no f0 / chroma / melody / chord / structure / key column. That
--    absence IS the non-cloning guarantee.
-- ---------------------------------------------------------------------------------------------
create table reference_context (
    reference_track_id  uuid primary key references reference_tracks (id) on delete cascade,

    -- CLAP audio-tower STYLE embedding — a global timbral/vibe fingerprint for advisory
    -- conditioning + retrieval. 512-d = LAION-CLAP `larger_clap_music` joint space (same width as
    -- the fragment embeddings in 0002). It is a vibe vector, NOT a note sequence; the analyzer
    -- computes it over the whole track and never derives chroma/f0 from it. The control plane reads
    -- back only vector_dims(...), never this vector (the compact-output / by-ID rule).
    clap_style_embedding vector(512),

    -- measurable, NON-melodic targets. These are ALWAYS produced by the analyzer for any row that
    -- exists in this table (a `reference_context` row is only written after a full analysis), so they
    -- are NOT NULL — that makes the Rust read path (`get_context_summary`) infer concrete `f32`/`text`
    -- under `cargo sqlx` instead of `Option<…>`, matching the non-`Option` `ReferenceContextSummary`
    -- fields. (`genre` stays nullable: zero-shot tagging can legitimately abstain.)
    genre            text,
    tempo_bpm_min    real   not null,            -- a tempo RANGE (target band), not a beat grid
    tempo_bpm_max    real   not null,
    lufs             real   not null,            -- integrated loudness (ITU-R BS.1770-4)
    -- 5-band energy ratios — persisted as the named-key OBJECT shape produced by
    -- `NonMelodicFeatures.tonal_balance.model_dump()`: {"low","low_mid","mid","high_mid","high"}.
    -- This is the pinned cross-language contract the Rust `TonalBalance` struct deserializes (WR-01);
    -- it is DELIBERATELY never the bands ARRAY form used only for compact CLI/log output. Coarse
    -- spectral shape; never notes.
    tonal_balance    jsonb  not null,
    stereo_width     real   not null,            -- mid/side energy ratio in [0,1]

    -- human-facing interpretation (NOT a machine conditioning target — kept at a different trust
    -- level than the measured fields above; PITFALLS.md Pitfall 5). NOT NULL: the analyzer must
    -- produce a non-empty description or fail loudly (see ClaudeVibeDescriber refusal handling, WR-03)
    -- rather than persist an empty string.
    vibe_description text   not null,            -- LLM prose: mood / space / era / texture / energy

    analyzer_version text not null,              -- bumped when the extractor/checkpoint changes
    -- The analyzer's output type (`ReferenceContext`) carries no timestamp, so the writer would have
    -- to source this out-of-band on every insert. Default it to wall-clock epoch-ms so the writer
    -- cannot forget it and violate NOT NULL; an explicit value (if ever supplied) still wins.
    created_at_ms    bigint not null default (extract(epoch from now()) * 1000)::bigint
);

-- ---------------------------------------------------------------------------------------------
-- 3. project_reference_context — attach a reference to a project as conditioning (REF-04).
--    Many-to-many, roled. Composite primary key makes `reference attach` an idempotent upsert.
-- ---------------------------------------------------------------------------------------------
create table project_reference_context (
    project_id          uuid not null references projects (id) on delete cascade,
    reference_track_id  uuid not null references reference_tracks (id) on delete cascade,
    role                reference_role not null,
    -- Default to wall-clock epoch-ms so the attach time is actually recorded: the Rust `attach`
    -- insert omits this column (ProjectReference carries no timestamp), so a literal `0` default
    -- left every row dead. The DB default now fills a real timestamp without a Rust-side change.
    attached_at_ms      bigint not null default (extract(epoch from now()) * 1000)::bigint,
    primary key (project_id, reference_track_id)
);

create index project_reference_context_project_idx
    on project_reference_context (project_id);

-- Read-path index for `reference show` order / listing.
create index reference_tracks_uploaded_idx on reference_tracks (uploaded_at_ms desc);
