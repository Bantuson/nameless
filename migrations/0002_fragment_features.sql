-- Nameless control plane — Phase 2 schema delta (Fragment Analysis).
--
-- Applied with: DATABASE_URL=postgres://... cargo sqlx migrate run
-- (or psql -f) AFTER 0001_init.sql. This migration is additive only: it does NOT touch the
-- fragments/projects shape from Phase 1, it extends them.
--
-- What Phase 2 adds (CAP-03 features + CAP-04 embeddings & retrieval):
--   1. Two pgvector embedding columns on `fragments` — the JOINT CLAP space (PRD §6):
--        * audio_embedding — CLAP audio-tower vector of the raw audio
--        * note_embedding  — CLAP text-tower vector of the intent note
--      Both live in ONE 512-d joint space (LAION-CLAP `larger_clap_music`), so a text query and an
--      audio query land in the same index — retrieval-by-note and retrieval-by-audio-similarity use
--      the same operator. These are the ONLY large objects the CLI is allowed to read back as a
--      *score*, never as raw components (the compact-output contract — PRD §12).
--   2. `fragment_features` — the big DSP arrays (f0 contour, chroma, onsets, beat grid) + the scalar
--      summaries (tempo, key, LUFS). PRD §6/§8: "large arrays; stored, never sent to the model."
--      They are addressed by fragment_id and never enter agent context.
--   3. ANN indexes (HNSW, cosine) over both embedding columns for fast top-k retrieval.
--
-- The Python worker plane (workers/) is the writer: it consumes a FeatureExtract job, computes
-- these, persists here, and drives Captured → Analyzing → Analyzed through the SAME transition rules
-- the Rust state machine owns (nameless_core::state_machine — canonical). See workers/LEARNING.md.

-- ---------------------------------------------------------------------------------------------
-- 1. Joint CLAP embedding columns on the fragment row.
-- ---------------------------------------------------------------------------------------------
-- Dimension 512 = LAION-CLAP joint projection width (`larger_clap_music` / HTSAT-base music CLAP).
-- pgvector fixes the dimension at the column level; if the checkpoint ever changes width, that is a
-- new migration (a deliberate, visible event — matching "pin the version + checkpoint", STACK.md).
alter table fragments
    add column if not exists audio_embedding vector(512),  -- CLAP audio tower
    add column if not exists note_embedding  vector(512),  -- CLAP text tower (note_text)
    -- Records WHICH model/checkpoint produced the two vectors above, so a re-embed under a new
    -- checkpoint is auditable and the retrieval path can refuse to mix incompatible spaces.
    add column if not exists embedding_model text;

-- ---------------------------------------------------------------------------------------------
-- 2. fragment_features — the derived DSP signals (one row per analyzed fragment).
-- ---------------------------------------------------------------------------------------------
-- Large arrays are stored as jsonb (f0 contour, chroma matrix, onset/beat times); the cheap scalar
-- summaries the agent is allowed to see (tempo, key, LUFS) are real/text columns so the retrieval
-- query can project them without deserializing a single big array.
create table if not exists fragment_features (
    fragment_id     uuid primary key references fragments (id) on delete cascade,

    -- ---- melody / harmony as continuous signals (never reduced to notes) ----
    -- f0_contour: {"times_s":[…], "f0_hz":[…], "confidence":[…]} from torchcrepe (PRD §8).
    f0_contour      jsonb,
    -- chroma: 12 × T CQT chromagram, row-major [[pc0_t0, pc0_t1, …], …] (librosa.chroma_cqt).
    chroma          jsonb,
    -- chroma_mean: the 12-d time-averaged chroma the Krumhansl-Schmuckler key estimate runs on.
    chroma_mean     jsonb,
    -- onset times (seconds) and the beat grid (seconds) — rhythm as event times, not audio.
    onsets_s        jsonb,
    beat_grid_s     jsonb,

    -- ---- cheap scalar summaries (the only feature fields the CLI surfaces) ----
    tempo_bpm       real,          -- librosa.beat.beat_track global tempo estimate
    key             text,          -- e.g. 'C:maj' / 'A:min' — Krumhansl-Schmuckler (pure fn)
    key_confidence  real,          -- the winning K-S correlation (−1..1); low ⇒ ambiguous tonality
    loudness_lufs   real,          -- pyloudnorm integrated loudness (ITU-R BS.1770-4)

    -- ---- reconstruction / provenance metadata ----
    sample_rate     int,           -- the sr the analysis ran at
    duration_s      real,
    hop_length      int,           -- frame hop used for chroma/onset/beat (for time reconstruction)
    analyzer_version text not null, -- bumped when the extractor changes ⇒ re-analysis is detectable
    created_at_ms   bigint not null
);

-- ---------------------------------------------------------------------------------------------
-- 3. ANN indexes for retrieval (CAP-04). HNSW + cosine.
-- ---------------------------------------------------------------------------------------------
-- HNSW (pgvector ≥0.8) over vector_cosine_ops: high recall, no training step, robust as the graph
-- grows incrementally (one capture at a time) — a better default than ivfflat for a solo, append-as-
-- you-go library where you never have the whole set up front to train ivfflat lists on. Rows with a
-- NULL embedding (not-yet-analyzed fragments) are simply absent from the index.
--
-- Cosine is the right metric because CLAP vectors are direction-meaningful, not magnitude-meaningful;
-- the worker L2-normalizes before insert, so cosine and inner-product agree and `1 - (a <=> b)` is a
-- clean [0,1]-ish similarity score.
--
-- ivfflat alternative (uncomment, and ANALYZE after bulk load, if you ever batch-import a large set):
--   create index fragments_audio_embedding_ivf on fragments
--       using ivfflat (audio_embedding vector_cosine_ops) with (lists = 100);
create index if not exists fragments_audio_embedding_hnsw
    on fragments using hnsw (audio_embedding vector_cosine_ops);

create index if not exists fragments_note_embedding_hnsw
    on fragments using hnsw (note_embedding vector_cosine_ops);
