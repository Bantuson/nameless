# Phase 2: Fragment Analysis - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous; grey areas auto-resolved). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

Deliver the Python worker-plane "fragment analysis" capability: a captured fragment becomes `analyzed`, carrying audio features (f0, chroma, onsets/beat-grid/tempo, key, LUFS) and embeddings (CLAP audio + note text), persisted and retrievable by audio similarity or note text (pgvector).

In scope: the feature-extraction worker, the embedder, persistence of features + embeddings, the Captured→Analyzing→Analyzed transition driven from the worker, and similarity retrieval surfaced through the CLI. The cross-language seam to Phase 1's Rust control plane (consume `FeatureExtract` jobs from the Postgres queue; persist to `fragment_features` + embedding columns; advance state).

Out of scope: generation/eval (M1), reference-track analysis (Phase 7 — different entity), stem separation (Phase 8), the knowledge pipeline (Phases 3-6), the web UI (Phase 9).
</domain>

<decisions>
## Implementation Decisions

### Worker architecture (ports-and-adapters — testability law)
- `AudioLoader` port: load raw bytes by content-hash ID from the ObjectStore. Real (filesystem/S3) + in-memory fake.
- `FeatureExtractor` port: bytes → typed `AudioFeatures`. Real impl (librosa + torchcrepe + pyloudnorm) + **deterministic fake** (returns fixed features) for tests.
- `Embedder` port: (audio bytes → vector) and (text → vector). Real impl (LAION-CLAP `larger_clap_music`: audio tower for audio, text tower for the note, so both live in ONE joint space) + fake (hash-seeded deterministic vectors).
- `FragmentRepo` / `FeatureStore` port: persist features + embeddings, read/write fragment state, similarity search. Real impl (Postgres + pgvector) + in-memory fake (numpy cosine for search).
- `AnalyzeJobConsumer`: the orchestration — consume `FeatureExtract{fragment_id}` → load → extract → embed → persist → transition. **Pure orchestration over injected ports**, fully testable with fakes (no real ML/DB needed to test the control flow).

### Features (CAP-03)
- f0 contour → torchcrepe; chroma → librosa.feature.chroma_cqt; onsets → librosa.onset; beat-grid + tempo → librosa.beat.beat_track; key → chroma-template (Krumhansl-Schmuckler) correlation; loudness → pyloudnorm (ITU-R BS.1770). Large arrays persist in `fragment_features`; NEVER printed by the CLI (compact contract holds).

### Embeddings + retrieval (CAP-04)
- CLAP audio embedding + CLAP text embedding of the note → both indexed in pgvector (one joint space, per PRD §6) so retrieval-by-note and retrieval-by-audio-similarity use the same index.
- CLI: `fragments search --note "<text>"` and `fragments search --similar-to <id>` → ranked matches (compact: id + key/tempo + score, never vectors).

### Cross-language state seam
- Phase 1's Rust state machine is the CANONICAL authority on transition legality. The worker only ever drives the legal `Captured → Analyzing → Analyzed` path, via `FragmentRepo.advance(fragment_id, Analyze/MarkAnalyzed)` whose impl applies the same guard (documented as a deliberate, minimal mirror of the Rust rules; Rust remains canonical). Surface this design tension explicitly in SUMMARY/LEARNING.
- Job + DB contracts (FeatureExtract envelope, `fragment_features` columns, embedding columns) match the Phase 1 schema/migrations.

### Env / packaging
- `uv` + `pyproject.toml`; deps: librosa, torchcrepe, pyloudnorm, laion-clap, numpy, soundfile, pydantic, psycopg + pgvector. Pin versions; DO NOT install (heavy ML, 4GB box).

### Claude's Discretion
- Module layout, exact pydantic models, key-detection template constants, pgvector index params (ivfflat/hnsw) — idiomatic Python, typed boundaries.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 1 Rust control plane: `crates/nameless-core` (provenance/state enums, `transition` rules to mirror), `migrations/0001_init.sql` (fragments + provenance/fragment_state enums + pgvector). The Python `fragment_features` + embedding columns extend this schema.
- `.planning/research/STACK.md` (librosa 0.11, torchcrepe, pyloudnorm 0.1, LAION-CLAP 1.1.7 + `larger_clap_music`) and `ARCHITECTURE.md` (worker plane shape, shared DSP lib).

### Established Patterns
- Ports-and-adapters with real+fake adapters (Phase 1 precedent in Rust; mirror in Python with `typing.Protocol`).

### Integration Points
- Reads jobs from the Postgres queue (Phase 1 `JobQueue`/`JobEnvelope`); writes `fragment_features` + embeddings to Postgres; advances `fragments.state`. New Python package, e.g. `workers/` (PRD "Python worker plane").
</code_context>

<specifics>
## Specific Ideas

- **Build mode (authoritative): `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning project — write complete, real Python; DO NOT run/install heavy ML on this 4GB box. Verify by review + tests-that-exist (run against the FAKES so the control flow is genuinely testable). The real librosa/CLAP/Postgres paths are env-gated with exact commands.
- **Go DEEP on the ML — ship `workers/LEARNING.md`** teaching: f0/CREPE pitch tracking, the chromagram, onset detection + beat tracking + tempo, Krumhansl-Schmuckler key estimation, LUFS/BS.1770 loudness, CLAP joint audio-text embeddings, and pgvector ANN similarity — with the math/intuition and why each matters for translating a hummed idea into a locked arrangement.
</specifics>

<deferred>
## Deferred Ideas

- Reference-track vibe/sonic-target extraction (Phase 7) reuses the CLAP/feature machinery but is a separate non-cloning entity — do not build it here.
- Real cross-process worker run + GPU acceleration → env-gated.
</deferred>
