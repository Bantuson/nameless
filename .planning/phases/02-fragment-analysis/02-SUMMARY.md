---
phase: 02-fragment-analysis
plan: all
subsystem: worker-plane
tags: [python, uv, ports-and-adapters, librosa, torchcrepe, pyloudnorm, laion-clap, pgvector, psycopg, krumhansl-schmuckler, clap, state-machine-mirror]

# Dependency graph
requires:
  - phase: 01-typed-capture-spine
    provides: "fragments/projects schema + provenance/fragment_state enums, JobEnvelope::FeatureExtract, content-hash object store, canonical Rust state machine (transition rules to mirror)"
provides:
  - "Python worker package workers/ (uv, pinned ML versions, NOT installed on the 4GB box)"
  - "Typed domain mirror: Provenance + FragmentState + Transition + pure transition() (faithful mirror of nameless-core, exhaustive 480-triple matrix test)"
  - "pydantic models: AudioFeatures, F0Contour, KeyEstimate, Embedding, FragmentRecord, SearchHit, AnalyzeOutcome; JobEnvelope discriminated union matching Rust serde JSON"
  - "Ports (Protocols): AudioLoader, FeatureExtractor, Embedder, FragmentRepo/FeatureStore, JobSource"
  - "Real adapters (lazy heavy imports): LibrosaFeatureExtractor (f0=torchcrepe, chroma/onset/beat/tempo=librosa, key=K-S pure, lufs=pyloudnorm), ClapEmbedder (laion_clap larger_clap_music), PgFragmentRepo (psycopg+pgvector cosine search + guarded advance), FilesystemAudioLoader/S3AudioLoader"
  - "Fake adapters: FakeFeatureExtractor (deterministic), FakeEmbedder (hash-seeded unit vecs), InMemoryFragmentRepo (numpy cosine), InMemoryAudioLoader, InMemoryJobSource"
  - "AnalyzeJobConsumer: pure orchestration (load→extract→embed→persist→advance), idempotent at-least-once"
  - "runner.run_once/run_forever over JobSource; nameless-workers CLI (fragments search --note/--similar-to, analyze, run)"
  - "Pure functions: Krumhansl-Schmuckler key-from-chroma; L2 normalize / cosine / rank_by_cosine"
  - "migrations/0002_fragment_features.sql: fragment_features table + audio/note vector(512) columns + HNSW cosine indexes"
  - "workers/LEARNING.md (deep DSP/ML teaching) + workers/README.md (env-gated run commands + seam)"
affects: [phase-07-reference-context, phase-08-stem-sampling, phase-09-web-ui, milestone-M1-generation-eval]

# Tech tracking
tech-stack:
  added: ["librosa 0.11.0", "torchcrepe", "pyloudnorm 0.1.1", "laion-clap 1.1.7", "soundfile", "torch (ml extra)", "psycopg 3 (pg extra)", "pgvector (pg extra)", "pydantic 2", "numpy", "uv/hatchling packaging"]
  patterns: [ports-and-adapters-python-protocols, lazy-heavy-imports-for-testability, pure-functions-for-core-logic, cross-language-state-machine-mirror-with-exhaustive-matrix-test, deterministic-fakes, compact-output-contract-at-type-level, joint-clap-embedding-one-index, hnsw-cosine-ann]

key-files:
  created: [
    "workers/pyproject.toml",
    "workers/src/nameless_workers/__init__.py",
    "workers/src/nameless_workers/domain/{__init__,models,provenance,state}.py",
    "workers/src/nameless_workers/pure/{__init__,key,vectors}.py",
    "workers/src/nameless_workers/ports.py",
    "workers/src/nameless_workers/consumer.py",
    "workers/src/nameless_workers/runner.py",
    "workers/src/nameless_workers/cli.py",
    "workers/src/nameless_workers/adapters/{__init__,audio_loader_fake,audio_loader_store,feature_fake,feature_librosa,embed_fake,embed_clap,repo_mem,repo_pg,job_source_mem}.py",
    "workers/tests/{__init__,conftest,test_models,test_state_mirror,test_key_from_chroma,test_vectors,test_consumer,test_repo_mem,test_runner}.py",
    "workers/LEARNING.md", "workers/README.md",
    "migrations/0002_fragment_features.sql"
  ]
  modified: []

key-decisions:
  - "Mirror the Rust state machine in Python (domain/state.py) rather than IPC to Rust per edge; pin the two with an exhaustive 480-triple matrix test. Rust stays canonical; drift surfaces in test_state_mirror.py."
  - "FragmentRepo.advance() is the guarded mutation chokepoint: it reads (provenance,state), applies the shared pure transition(), and persists — so the worker cannot drive an illegal edge (e.g. analyze an ai_generated fragment, or place an unanalyzed one)."
  - "Heavy libs (librosa/torch/torchcrepe/laion_clap/psycopg/pgvector) imported LAZILY inside methods so the package + full test suite run on a pydantic+numpy base — the decision that makes the fakes a faithful, runnable double on the 4GB box."
  - "Krumhansl-Schmuckler key estimation written as a PURE function over chroma_mean (no audio), so it is exhaustively unit-tested; confidence = winning Pearson r (flat chroma ⇒ ~0 ⇒ honestly 'no key')."
  - "ONE joint CLAP space: audio tower + note text tower → two vector(512) columns; a text query ranks cross-modally against audio_embedding. HNSW+cosine index (no training, robust to incremental inserts) over ivfflat for a solo append-as-you-go library."
  - "Compact-output contract enforced at the TYPE level: SearchHit has only {fragment_id,key,tempo_bpm,score} — structurally cannot carry a vector/array."
  - "Consumer is idempotent for at-least-once delivery: skip if already analyzed, resume if mid-flight; on failure leave the fragment in 'analyzing' (the Rust FSM has no 'analysis failed' state) and let the queue RetryPolicy retry/dead-letter."
  - "tiered deps: base (pydantic+numpy) for fakes/tests, [ml] + [pg] extras for the real leaf — maps exactly to the RAM-safe vs env-gated verification split."

patterns-established:
  - "Python ports-and-adapters with typing.Protocol; real adapter + deterministic fake per port."
  - "Cross-language domain mirror validated by reproducing the Rust exhaustive matrix test."
  - "Lazy heavy imports keep core/test paths light; real adapters are env-gated leaves."

requirements-completed: [CAP-03, CAP-04]

# Metrics
completed: 2026-06-27
status: complete
tests: "58 passed (fakes-only, run here — RAM-safe)"
---

# Phase 2: Fragment Analysis Summary

**A Python worker-plane (`workers/`) that takes a captured fragment to `analyzed` — extracting f0
(torchcrepe), chroma/onsets/beat-grid/tempo (librosa), key (a pure Krumhansl-Schmuckler function),
loudness (pyloudnorm/BS.1770) and a joint CLAP audio+note embedding (LAION-CLAP), persisting them to
`fragment_features` + two `vector(512)` columns, advancing `Captured→Analyzing→Analyzed` through a
faithful, exhaustively-tested mirror of the canonical Rust state machine, and serving retrieval by note
text or audio similarity over a pgvector HNSW cosine index — all behind ports with deterministic fakes,
so the entire control flow is tested with no ML or database (58 tests pass on a pydantic+numpy base).**

## Requirement coverage

| Requirement | How |
|---|---|
| **CAP-03** (features) | `LibrosaFeatureExtractor`: f0=`torchcrepe.predict` (16 kHz, 10 ms hops, periodicity confidence); chroma=`librosa.feature.chroma_cqt`; onsets=`librosa.onset.onset_detect`; beat grid+tempo=`librosa.beat.beat_track`; key=pure `estimate_key` (Krumhansl-Schmuckler); LUFS=`pyloudnorm.Meter.integrated_loudness`. Persisted to `fragment_features` (jsonb arrays + scalar key/tempo/lufs). Fake mirrors the shape deterministically. |
| **CAP-04** (embeddings + retrieval) | `ClapEmbedder` audio tower + text tower → ONE 512-d joint space; persisted to `fragments.audio_embedding` / `note_embedding`. `PgFragmentRepo.search` ranks with pgvector cosine `<=>`; HNSW indexes in `0002`. CLI `fragments search --note <text>` (cross-modal) and `--similar-to <id>`; compact `id key tempo score` only. |

## File / module map
See `key-files` frontmatter. Centerpieces: `domain/state.py` (Rust mirror), `pure/key.py` (K-S),
`adapters/feature_librosa.py` + `adapters/embed_clap.py` (real ML leaf), `adapters/repo_pg.py`
(psycopg+pgvector), `consumer.py` (orchestration), `migrations/0002_fragment_features.sql`.

## Cross-language state-seam design note
The Rust control plane owns the **canonical** transition rules (`crates/nameless-core/src/state_machine.rs`).
The Phase-2 worker is a separate Python process that, after computing features, must advance
`Captured → Analyzing → Analyzed` itself. Rather than make an IPC round-trip to Rust per edge (coupling a
trivial pure function to control-plane availability), `domain/state.py` **mirrors** the rules and
`FragmentRepo.advance()` applies them as a guarded read-modify-write — so the worker is structurally
unable to drive an illegal edge (it cannot analyze an `ai_generated` fragment, nor place an unanalyzed
one). The mirror's only risk is **drift**; `tests/test_state_mirror.py` reproduces the Rust **480-triple
exhaustive matrix** (4×12×10) against an independently hand-written allow-list, so any divergence fails a
test. Rust remains the source of truth; Python is a tested shadow. The job envelope likewise mirrors the
Rust serde JSON exactly (`{"job":"feature_extract","fragment_id":…}`), verified in `test_models.py`.

## Deviations from plan
- **No formal PLAN.md existed for Phase 2** (only `02-CONTEXT.md`); built directly from the CONTEXT
  decisions + execution-context deliverables. Every CONTEXT decision (ports list, feature stack,
  one-joint-space embeddings, advance-via-mirror seam, uv packaging) is implemented as specified.
- **Added a `JobSource` port + `runner.py`** beyond the named ports, to make queue consumption testable
  and to surface the seam binding honestly (it was implied by "AnalyzeJobConsumer consumes a FeatureExtract
  job"). No scope creep — it is the consume-side mirror of the Phase-1 `JobQueue` trait.
- **CLAP real adapter uses the `laion_clap` package** (pinned 1.1.7, music checkpoint) per the stack pin;
  the HuggingFace `laion/larger_clap_music` route is documented as a drop-in behind the same port.

## Verification

### Reviewed-complete AND run here (RAM-safe — fakes only, pydantic+numpy+pytest present on this box)
- **`uv run pytest -q` → 58 passed (~1.4s).** Genuinely executed on this machine (the light base was
  available), so the following are not just "written" but green:
  - state-machine mirror: the full 480-triple matrix + all headline invariants (cannot place unanalyzed,
    ai cannot be analyzed, sampled travels human path, rejected terminal, illegal pair names itself).
  - Krumhansl-Schmuckler: major/minor templates resolve to their tonic, all 12 transpositions, C-major
    triad → `C:maj`, flat chroma → confidence 0, length validation.
  - vectors: normalize/cosine identities, stable descending ranking, limit/empty handling.
  - orchestration: Captured→Analyzed, features+embeddings persisted & searchable, idempotent re-delivery,
    resume-from-analyzing, not-found, ai-provenance refusal, loader-failure→retryable & left analyzing,
    embedding-dim-mismatch rejected.
  - repo: cosine ranking + key/tempo join, exclude-self, project filter, note-field ranking,
    unanalyzed-absent-from-index, guarded advance + illegal-edge refusal.
  - runner: ack-on-success, retry-on-failure, dead-letter ceiling, non-feature job acked-not-processed.
  - models: job-envelope JSON matches the Rust shape; SearchHit type cannot carry a vector.
- **Static checks run here:** `python -m py_compile` over all 24 files (clean); importing every REAL
  adapter module (`feature_librosa`, `embed_clap`, `repo_pg`, `audio_loader_store`) WITHOUT torch/
  librosa/psycopg installed succeeds and leaks none of them (proves the lazy-import testability design);
  CLI parses and fails cleanly with a `DATABASE_URL` message before importing psycopg.

### Env-gated (NOT run here — needs the heavy ML leaf and/or a live Postgres)
Install heavy deps + a migrated Postgres first (the 4 GB box cannot):
- `cd workers && uv sync --extra ml --extra pg` — installs librosa/torch/torchcrepe/pyloudnorm/laion-clap
  + psycopg/pgvector (may OOM on 4 GB; use a real machine/GPU box).
- `psql "$DATABASE_URL" -f migrations/0002_fragment_features.sql` (or `cargo sqlx migrate run`) — applies
  the `fragment_features` table + vector columns + HNSW indexes.
- `DATABASE_URL=… NAMELESS_OBJECT_ROOT=… uv run nameless-workers analyze --fragment <id>` — real
  end-to-end analysis of one captured fragment (decode → librosa/torchcrepe/pyloudnorm → CLAP → persist →
  advance). This is the single-shot entrypoint the Rust sqlxmq runner invokes per job.
- `uv run nameless-workers fragments search --note "the chorus-like ideas"` /
  `--similar-to <id>` — real pgvector cosine retrieval.
- (Optional) wire `S3AudioLoader` (`uv add boto3`) for R2 instead of the filesystem object store.
- **First-time supply chain:** verify the pinned PyPI packages and pin the CLAP checkpoint before any
  real `uv sync` (README "Supply chain").

## Next-phase readiness
- **M1 generation/eval** consumes exactly these signals: chroma/key/tempo/beat-grid condition the
  generator (MusicGen-Stem chromagram conditioning); the CLAP embedding + LUFS feed the eval gate
  (CLAP-alignment, loudness-delta). The `FeatureExtractor`/`Embedder` ports are the reuse seam.
- **Phase 7 (reference context)** reuses `LibrosaFeatureExtractor` (tempo/LUFS/tonal balance) + `ClapEmbedder`
  (vibe embedding) — but as a separate non-cloning entity; do not extend `fragment_features` for it.
- **Phase 9 (web UI)** can call `fragments search` for the graph/retrieval views.
- **Blocker for the user:** the real worker run is env-gated — install the `ml`+`pg` extras on a capable
  machine and apply `0002` before driving live analysis.
