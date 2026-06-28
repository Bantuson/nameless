# Phase 8: Stem Library + Attributed Sampling - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

A producer separates any uploaded track into a retained stem library, promotes a stem to an attribution-complete `sampled` fragment at any time, and exports a credits sheet. Spans the Rust control plane (stems + sample_attribution schema, the attribution-completeness INVARIANT, rights-status, CLI, credits) and the Python worker plane (Demucs stem separation).

In scope: Demucs separation + retained stem library, promote-stem→`sampled` fragment, the attribution-completeness state-machine invariant (no placement without complete attribution), the `rights-status` field + "attribution ≠ permission" messaging, the credits-sheet generator. Out of scope: UI (Phase 9), generation/M1, sample clearance workflow (v2).
</domain>

<decisions>
## Implementation Decisions

### Rust control plane (extends Phases 1 + 7) — SAMP-02/03/04/05
- `sampled` provenance already exists (Phase 1) and travels the human lifecycle (Captured→Analyzing→Analyzed→Placed), never the eval gate (already typed + tested).
- **Attribution-completeness invariant (SAMP-03 — the integrity boundary):** a `sampled` fragment CANNOT be placed (Analyzed→Placed) until attribution is complete (source_track, artist, stem, time_range). Make incomplete states unrepresentable: a typed `CompleteAttribution` (vs `PartialAttribution`) where only `CompleteAttribution` can be attached, and the sampled-Place path requires it — a hard, no-bypass block returning a typed error otherwise. This mirrors the eval gate ("harness gates, agent explores") for sampling.
- Schema (migration `0004_sampling.sql`): `stems` (retained per source track, by content-hash, browsable), `sample_attribution` (source_track_id, artist, stem_type, time_range_ms, separator_model+version, separated_at, rights_status), link to the sampled fragment.
- `rights_status` enum: `copyrighted_uncleared | royalty_free | own_work | unknown`; system states in-context that **attribution is not permission** (SAMP-04).
- CLI: `stems list <track>`, `sample add <stem> --project <p> --artist … --time-range … --rights …` (promote → sampled fragment with attribution), `credits <project>` → credits sheet (SAMP-05).
- Pure: `credits_sheet(attribution_rows)` → text/markdown; the attribution-completeness predicate.
- `StemStore` + `AttributionStore` ports + Postgres-feature real + in-memory fakes.

### Python worker (extends `workers/`) — SAMP-01
- `StemSeparator` port: track bytes → named stems (vocals/drums/bass/other; htdemucs_ft, or htdemucs_6s for piano isolation — relevant to alt-piano). Real adapter (Demucs, lazy) + deterministic fake. Stems retained in object storage by content-hash, recorded with `separator_model+version` for provenance.

### Claude's Discretion
- stem-model default (htdemucs_ft vs _6s), schema column types, credits-sheet format, exact typed-attribution API.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 1 `crates/nameless-core` (provenance incl. `sampled`, state machine `transition`, ports+fakes, migrations) + Phase 7 `ReferenceTrack`/upload/ObjectStore machinery (SHARED — sampling separates the SAME uploaded tracks). EXTEND.
- Phase 2 `workers/` (worker plane, ports+fakes, lazy heavy imports, pytest) — add the Demucs `StemSeparator` alongside the feature/reference workers.
- `.planning/research/ARCHITECTURE.md` (`stems`/`sample_attribution` schema, sampled-on-human-path + attribution invariant) + `PITFALLS.md` (sampling copyright reality: infringes regardless of intent; rights-status from day one; attribution ≠ permission; Demucs artifacts) + `STACK.md` (Demucs htdemucs_ft/_6s, maintenance-only; BS-RoFormer swap path behind the port).

### Established Patterns
- Rust: traits+real+fake; pure domain; make-illegal-states-unrepresentable; heavy behind features. Python: Protocol ports+real+fake; pure core; lazy heavy imports; tests RUN.

### Integration Points
- Shares the Phase-7 upload/ObjectStore path (an uploaded track is both a reference AND a sample source — the user's "choose dynamically, even weeks later" model). Sampled fragments enter the Phase-1 fragment lifecycle. Credits sheet reads `sample_attribution`.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — Rust REVIEW-ONLY (write complete code + tests, don't compile); Python tests RUN against fakes/fixtures (separator orchestration, attribution completeness, credits sheet, rights-status). Real Demucs separation env-gated.
- **Ship a `LEARNING.md` section** teaching: how Demucs source separation works (hybrid waveform/spectrogram U-Net + transformer, mask estimation; htdemucs_ft vs _6s piano), attribution-clean sampling vs copy-and-claim-original, the honest legal reality (sampling recordings infringes regardless of personal intent; attribution ≠ permission; rights-status from day one), and the attribution-completeness invariant as a structural gate.
</specifics>

<deferred>
## Deferred Ideas
- Sample clearance / licensing workflow → v2 (PRD §15).
- BS-RoFormer separator swap → behind the StemSeparator port when Demucs under-separates.
- M1 mix/master/export attaching the credits sheet to the final track → M1.
</deferred>
