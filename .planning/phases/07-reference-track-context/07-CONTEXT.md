# Phase 7: Reference-Track Context - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

A producer uploads a finished song they love and gets its **vibe + measurable non-melodic sonic targets** as project conditioning context — with cloning made **structurally impossible**. Spans the Rust control plane (reference entity + schema + non-cloning typing + CLI) and the Python worker plane (non-melodic vibe/sonic-target extraction reusing Phase-2 CLAP/feature).

In scope: `reference_tracks`/`reference_context` schema + types (NO melody/chroma/structure field), the reference-analysis worker (CLAP style embedding, genre, tempo range, LUFS, tonal balance, stereo width, LLM vibe description), structural non-cloning enforcement, `reference upload/show/attach` CLI, project↔reference link. Out of scope: sampling (Phase 8), UI (Phase 9), generation/M1 consumption of the context (built here as an exposable bundle; consumed in M1).
</domain>

<decisions>
## Implementation Decisions

### Rust control plane (extends Phase 1) — REF-01, REF-03, REF-04
- New entity `ReferenceTrack` + `ReferenceContext`, SEPARATE from `Fragment` — references never enter the fragment lifecycle. Migration `0003_reference_tracks.sql`.
- **Non-cloning is structural (REF-03):** `ReferenceContext` has ONLY non-melodic columns — `clap_style_embedding`, `genre`, `tempo_range`, `lufs`, `tonal_balance`, `stereo_width`, `vibe_description`. There is NO melody/chroma/structure field → nothing to leak into. The melodic-conditioning path (the function that gathers conditioning for generation) accepts only `human_recorded` `Fragment`s by type — a `ReferenceTrack` is not a `Fragment`, so it is structurally barred (compile-time, not a runtime check). A type-level test proves a reference cannot reach the melodic path.
- `ReferenceStore` port (Postgres real + in-memory fake). Audio stored immutably by content-hash via the existing `ObjectStore` (REF-01).
- CLI: `nameless reference upload <path>`, `reference show <id>` (compact vibe/target summary), `reference attach <id> --project <p>` (REF-04) via a `project_reference_context` link.

### Python reference-analysis worker (extends `workers/`) — REF-02
- `ReferenceAnalyzer` port: bytes → `ReferenceContext` (non-melodic only). Real adapter REUSES Phase-2 `Embedder` (CLAP audio tower) but a **restricted feature path that NEVER computes f0/chroma** — a `NonMelodicFeatures` type that structurally lacks melody fields (non-cloning at extraction too). Fake = deterministic.
- Extracts: CLAP style embedding; genre (CLAP zero-shot tags / essentia, pluggable); tempo range; LUFS (pyloudnorm); tonal balance (multiband RMS — pure); stereo width (mid/side energy ratio — pure); + `VibeDescriber` port (real Claude → mood/space/era/texture/energy prose; fake deterministic). LLM call env-gated.

### Pure, testable core
- tonal-balance (band RMS ratios) + stereo-width (mid/side) math; the restricted-feature-set invariant (the type cannot carry melody); summary formatting (compact, never embeddings/arrays).

### Claude's Discretion
- exact band splits, genre-tagger choice, vibe-prompt wording, schema column types.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 1 `crates/nameless-core` + `nameless-adapters` (ObjectStore, ports+fakes, state machine, migrations) — EXTEND for the reference entity; mirror the ports+fake pattern.
- Phase 2 `workers/` (`Embedder`/CLAP, `FeatureExtractor`, pyloudnorm, pure vectors, lazy heavy imports, pytest) — REUSE the Embedder + build the RESTRICTED non-melodic extractor; do not recompute melody.
- `.planning/research/ARCHITECTURE.md` (reference_tracks/reference_context entity, non-cloning structural) + `PITFALLS.md` (clone-boundary leaks: one shared feature path = silent cloning → type the asymmetry).

### Established Patterns
- Rust: traits as ports + real+fake; pure domain + typed errors; heavy behind features. Python: Protocol ports + real+fake; pure core; lazy heavy imports; tests RUN on base env.

### Integration Points
- Rust control plane (audio by ID via ObjectStore; new reference schema). Python worker analyzes the uploaded reference. The `ReferenceContext` is the exposable conditioning bundle the M1 arranger/generator/eval will consume (built here, consumed later). Phase 8 (sampling) shares the upload/stem machinery.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — Rust is REVIEW-ONLY (no toolchain): write complete idiomatic code + tests, do NOT compile. Python: write complete code; tests RUN against fakes/fixtures (tonal-balance/stereo-width math, the restricted-feature invariant, summary, attach, the type-level non-cloning proof where expressible in Python). Real CLAP/LLM env-gated.
- **Ship a `LEARNING.md` section** teaching: WHY non-cloning must be STRUCTURAL not conventional (the clone-leak pitfall — one shared feature path silently clones; type the asymmetry so a reference physically cannot reach the melodic path); vibe/sonic-target conditioning vs melodic conditioning; what LUFS / tonal balance / stereo width / CLAP capture about "vibe"; the "a finished song is better context than a description, but never recreated" thesis.
</specifics>

<deferred>
## Deferred Ideas
- Stem separation + sampling from uploads → Phase 8 (shares upload machinery).
- M1 consumption of reference context in generation/eval (clone-leak negative check) → v2/M1.
</deferred>
