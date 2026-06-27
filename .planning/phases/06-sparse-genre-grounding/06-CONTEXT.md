# Phase 6: Sparse-Genre Grounding - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

Author a grounded, confidence-labeled skill for under-tutorialized sounds (alternative piano; Ben Produces, Liyana Ricky, Lowbass Djy) WITHOUT fabricating craft — by (1) decomposing the target into parent techniques and composing from their already-authored claims, and (2) analyzing the artists' actual released tracks through the Phase-2 audio/CLAP pipeline to fold in objective sonic signatures, with thin evidence explicitly labeled LOW confidence. This is the user's flagged concern (the two strategies they chose: decompose-into-parents + analyze-real-tracks).

Out of scope: reference/sampling (7-8), UI (9), generation/M1, non-tutorial text mining (v2).
</domain>

<decisions>
## Implementation Decisions

### Architecture (extends knowledge-pipeline; reuses workers/ audio — testability law)
- `decompose(target_cell) -> [parent_cells]` (PURE): alternative-piano → {amapiano log-drum/groove, jazzy/soulful piano, deep-house space/groove}. Compose the alt-piano skill from the PARENTS' authored claims (Phase 5) — never invent.
- `TrackAnalyzer` port: a released track → `AudioDerivedClaim`s (tempo range, groove/swing, tonal balance, key tendency, CLAP tags), each cited to the track (artist/title @ region). Real adapter reuses Phase-2 `FeatureExtractor`/`Embedder` (lazy, env-gated); fake = deterministic from canned features. Audio claims are a DISTINCT evidence type, clearly labeled vs tutorial claims.
- `GroundingPipeline` = pure orchestration: decompose → gather parent claims → analyze tracks (audio claims) → synthesize (Phase-5 synthesizer over the combined claim set) → GATE → emit confidence-labeled skill.

### Confidence (KNOW-10 — pure, honest)
- `confidence(cell)` from: # direct tutorial sources (here ~0 for alt-piano), parent-decomposition distance, audio corroboration count. Thin → LOW, explicitly stamped in frontmatter + body ("grounded by decomposition + audio analysis, NOT direct tutorials"). Never present thin evidence as settled craft.

### Citation gate over mixed evidence
- Reuse Phase-5 `citation_gate` unchanged in spirit: audio-derived numbers must trace to a real `AudioAnalysisRecord` (the track is the citation); invented numbers still rejected. Tutorial claims trace to transcript quotes; audio claims to analysis records. Both first-class, both cited.

### Output
- `skills/production/<stage>/alternative-piano/SKILL.md` (and/or a composite alt-piano skill) — composed from parents + audio signatures, LOW-confidence labeled, PASSING the gate. The artist roster is the audio-source set (fixtures here; real tracks env-gated).

### Claude's Discretion
- Exact decomposition map weights, audio-claim phrasing, confidence formula constants, which parent cells feed which alt-piano sub-claim.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 5 `knowledge-pipeline/`: synthesizer (fake), `citation_gate`, layered emitter, `SkillStore`, P1 cells, authored skills + claim fixtures. EXTEND this package.
- Phase 2 `workers/`: `FeatureExtractor`/`Embedder` ports + fakes (CLAP, librosa) — REUSE for `TrackAnalyzer` (don't re-implement DSP).
- `.planning/research/PITFALLS.md` (sparse-genre: when decomposition misleads, CLAP over-claim; label low-confidence) + `FEATURES.md` (alt-piano parent decomposition; parent-technique table) + `PROJECT.md` decision (decompose + analyze real tracks; the two chosen strategies).

### Established Patterns
- Protocol ports + real+fake; pure core tested with fixtures; lazy heavy imports (torch/CLAP only in real `TrackAnalyzer`); tests RUN on the base env.

### Integration Points
- Input = Phase-5 authored parent skills/claims + (faked) released-track features. Output = a confidence-labeled alt-piano SKILL.md in `skills/production/`. This is the last knowledge-pipeline phase; Phases 7-8 are reference/sampling.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — write the real `TrackAnalyzer` (reusing workers' real feature/CLAP path); DO NOT run torch/CLAP or fetch real audio. Verify by review + tests-that-RUN against fakes/fixtures: decompose map, parent-claim composition, audio-claim construction (from canned features), confidence=LOW labeling, gate over mixed tutorial+audio claims, the emitted alt-piano skill. Real audio analysis env-gated.
- **Extend `LEARNING.md`** teaching: grounding a sound with no direct tutorials (decompose into parents + analyze real audio); WHY honest LOW-confidence labeling beats fabricated craft ("quality in, quality out"); the danger of audio over-claiming (CLAP genre coarseness — verified in research); the alt-piano = amapiano-groove + jazzy-piano + deep-house-space decomposition with the named pioneers.
</specifics>

<deferred>
## Deferred Ideas
- Non-tutorial source mining (interviews/breakdowns) for these artists — v2.
- Broad P2 genre×stage coverage — v2.
</deferred>
