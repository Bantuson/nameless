# Project Research Summary

**Project:** Nameless
**Domain:** Audio-native, local-first, solo AI music composition system + tutorial-distilled production-knowledge layer + reference-track context + attribution-tracked sampling
**Researched:** 2026-06-26
**Confidence:** HIGH on the locked stack/architecture and the new-capability integration shape; MEDIUM on generator models (research-grade, fast-moving) and the distillation-pipeline prompt design (no turnkey tool, it is a build).

## Executive Summary

Nameless extends an already senior-grade PRD (Rust control plane + Python audio-ML worker plane + TS/React frontend, Postgres+pgvector, S3/R2 by-ID, Skill+CLI capability layer with no MCP) with three init-time capabilities. The first, a **tutorial-derived production-knowledge layer** emitted as authored Claude Skills, is the M0 foundation, as load-bearing as the per-project fragment-memory graph and **must never be conflated with it**: the knowledge layer is a build-time offline pipeline producing read-only files on disk; the fragment graph is mutable per-project state in Postgres. They share no tables and no runtime read path. The signature architectural bet is authored Skills over RAG: a SKILL.md costs about its description until triggered, stays human-auditable and version-controlled, and keeps agent context near-empty.

The locked stack survives validation almost intact (axum 0.8 + sqlx 0.8 resolves the sqlx-vs-SeaORM decision toward sqlx; librosa/pyloudnorm/Demucs/CLAP confirmed), with a few actionable flags: defer the NATS/Redis message bus entirely and run a **Postgres-backed queue (sqlxmq) at solo scale**; treat torchaudio as I/O glue only; note Demucs is maintenance-only (BS-RoFormer via audio-separator is the swap path); and recognize the generator weights (MusicGen CC-BY-NC) are non-commercial. The distillation pipeline is the make-or-break build: extract atomic cited claims, then synthesize only over the claim set, then run a programmatic citation-verification gate, with layered output (opinionated default PLUS preserved consensus/conflict). Transcript ingestion must run **locally with snapshot-on-ingest** (YouTube blocks cloud IPs) with a faster-whisper ASR fallback.

The dominant risks are integrity risks, not infra risks. The highest-stakes pitfall is GIGO distillation (the LLM hallucinating craft, conflating genres, citation-drifting), exactly the quality-in-quality-out fear the project exists to answer; the mitigation is the extract-then-synthesize split plus a quote-and-cite verification gate and human spot-audit. The non-cloning boundary must be **typed/structural**, not conventional: reference tracks are physically barred from the melodic conditioning path (only human_recorded fragments feed melody), enforced with Rust exhaustive matching. The sampled provenance travels the human lifecycle (no eval gate) but is held by an **attribution-completeness invariant**. License realities bite even for a portfolio (sampling recordings infringes regardless of intent, so add a rights-status field). Eval/token economics need per-genre calibrated thresholds plus a max-attempts terminator so niche-genre regeneration loops do not silently burn the metered budget.

## Key Findings

### Recommended Stack

The locked stack is validated for 2026. The control plane is Rust + axum 0.8 with sqlx 0.8 (compile-time-checked SQL matches the schema-integrity-reads-as-senior thesis; SeaORM only if CRUD volume demands). The worker plane is Python 3.11/3.12 with librosa 0.11 as the DSP workhorse, pyloudnorm for LUFS, Demucs (htdemucs_ft / htdemucs_6s for piano isolation) for separation, torchcrepe/basic-pitch for pitch/MIDI, LAION-CLAP for the joint audio-text space, and pedalboard for the mix/master chain. Generation is MusicGen-Stem and/or MuseControlLite behind a worker interface. The knowledge pipeline adds yt-dlp + youtube-transcript-api + faster-whisper for ingestion and Claude (Agent SDK) + pydantic for typed claim extraction. See [STACK.md](STACK.md).

**Core technologies:**
- **Rust + axum 0.8 + sqlx 0.8** -- control plane, typed state machine, gate enforcement -- exactly schema integrity + DAG correctness + exhaustive transitions.
- **Python worker plane (librosa / pyloudnorm / Demucs / torchcrepe / basic-pitch / CLAP / pedalboard)** -- DSP + separation + generation + eval + mix/master -- shared DSP lib also imported by the offline knowledge pipeline.
- **Postgres 16/17 + pgvector 0.8** -- fragment graph, features, embeddings, evals, plus reference/stem/sample tables -- one store keeps the solo footprint minimal.
- **Postgres-backed queue (sqlxmq)** -- durable job queue -- **defer NATS/Redis entirely at solo scale**; swap behind an abstract worker-job interface only when throughput/autonomy demands.
- **yt-dlp + youtube-transcript-api + faster-whisper** -- transcript acquisition with ASR fallback -- run locally (cloud IPs are blocked).
- **Claude (Agent SDK) + pydantic** -- offline claim-mining/synthesis emitting SKILL.md -- the distillation pipeline is a build, not a library.
- **S3/R2 (no egress fees)** -- immutable raw + rendered audio + retained stems by ID.

### Expected Features

Research focused on the new/fuzzy areas: knowledge ingestion, reference context, attributed sampling, and the production-knowledge taxonomy. The signature differentiator is tutorials distilled into authored Skills (not RAG) with layered, cited output. See [FEATURES.md](FEATURES.md).

**Must have (table stakes):**
- Transcript fetch + per-claim source binding (video ID + timestamp) -- traceability is the baseline trust contract.
- Claim extraction into a typed stage x genre schema -- raw transcript is unusable as grounding.
- Cross-reference + contradiction handling that preserves both sides -- the default is a decision on top of preserved conflict, never a deletion.
- Taxonomy organization into authored Skills for the **P1 cells** -- the navigable production stack of skill is the value.
- Key/tempo/grid-locked generation + objective eval gate + per-part provenance -- the PRD-specified composition promise.
- Reference upload to vibe + measurable **non-melodic** sonic targets; stem separation + provenance + credits sheet.

**Should have (competitive):**
- Layered output: opinionated default PLUS preserved consensus/conflict with citations -- actionable AND auditable.
- Parent-technique decomposition + released-track audio analysis for under-tutorialized sounds (alt-piano) -- never fabrication.
- Persistent personal stem library -- any stem promotable to an attributed sample weeks later.
- Attribution-clean-by-construction (provenance mandatory, not optional metadata).

**The production stack of skill (taxonomy):** production-stage (00 Foundations through 13 Mastering) x genre (R&B / amapiano / alt-piano / deep house / fusion). The **P1 cells cluster around the north-star fusion**: R&B vocal layering/adlibs/lush chords/atmosphere + amapiano and alt-piano log-drum groove + jazzy piano + deep-house space/groove. Author those first; decompose the rest. This is a roadmap-load-bearing prioritization signal.

**Defer (v2+):** P2 taxonomy cells (broad genre x stage coverage); non-tutorial source mining (interviews/breakdowns); per-genre mastering presets / full mixing console (PRD M3); sample clearance/licensing flags (deferred with commercialization).

**Anti-features (NOT building):** cloning/cover mode of a reference; RAG/pgvector for tutorial knowledge; lyric generation / vocal synthesis; one-shot generate-the-whole-track; a bare confidence number with no evidence.

### Architecture Approach

The three new capabilities **bolt onto the locked PRD spine additively**, no redesign. The single most important boundary: the production-knowledge pipeline is an **offline authoring tool, not a runtime plane**. It runs on demand on your machine, emits files to skills/, and disappears from the runtime picture (it may import workers/lib for the sparse-genre audio-grounding leg, but never runs as a queue consumer). Build-time claim provenance lives in pipeline-local registry.sqlite, deliberately NOT in runtime Postgres. See [ARCHITECTURE.md](ARCHITECTURE.md).

**Major components:**
1. **Offline knowledge pipeline** (knowledge-pipeline/, sibling of runtime planes) -- discover, fetch, claim-mine, scrutinize, emit to skills/production/. Build-time only; output is git-versioned files.
2. **Rust control plane (additive deltas)** -- provenance enum gains Sampled; new reference.rs/stems.rs/attribution.rs; attribution-completeness invariant in the state machine; new nameless reference|stems|sample|credits subcommands.
3. **Python worker plane (new job types)** -- reference-context extract (CLAP + non-melodic sonic targets) and stem-library separation (Demucs on uploaded tracks, retained), reusing existing DSP libs.
4. **New schema** -- reference_tracks, reference_context (no melody/chroma/structure column; non-cloning is structural), stems, sample_attribution (completeness enforced as a state-machine invariant).
5. **Frontend additions** -- reference upload, stem-library browser, credits view.

**Build-order signal:** M0 has **multiple concurrent tracks** -- Track A control plane (F1, S1, S3), Track B worker plane (F2, S2), Track C the **offline knowledge pipeline (K1 to K3, startable day one in parallel** since its only hard external dep is YouTube tooling), Track D frontend. The critical path to a good M1 is F1, F2, then authored craft AND sampling/reference, then M1 generation+gate.

### Critical Pitfalls

1. **GIGO distillation (the central, make-or-break risk)** -- LLM fabricates specificity, conflates genres, over-generalizes, citation-drifts. Avoid with **two separate passes (extract atomic cited claims, then synthesize only over the claim set)**, a programmatic quote-and-cite verification gate, never letting the LLM invent numbers, preserving contradiction as first-class data, and a 10-20% human spot-audit before any skill ships. Flag for deep, dedicated planning.
2. **Transcript ingestion degrades / gets IP-blocked** -- auto-captions mangle producer jargon and code-switched SA speech; much craft is visual-only; YouTube blocks cloud IPs and rate-limits. Avoid with an **extractability score as a gating feature**, run ingestion **locally with throttling + snapshot-on-ingest (hash + retrieval date)** so citations survive takedowns, faster-whisper ASR fallback, and modality flags so visual-only lessons are not faked into SKILL.md.
3. **Cloning boundary leaks** -- melody-conditioned generators are designed to follow melody; one shared feature path + one forgotten branch = silent cloning. Avoid by **typing the asymmetry into the schema/state machine** (only human_recorded feeds melodic conditioning; references expose only non-melodic targets), plus a negative melodic-similarity check (generated-vs-reference) in the eval gate.
4. **Sampling copyright reality understated** -- sampling recordings infringes regardless of intent; a portfolio is published, not private; MusicGen output is NC-encumbered. Avoid by adding a **rights-status field** (copyrighted-uncleared / royalty-free / own-work / unknown) from day one, stating in-system that attribution is not permission, and preferring clear-licensed/own material for public output.
5. **Eval-gate thresholds mis-tuned + token-thin discipline violated** -- too-strict gates trigger endless regeneration (GPU + token burn); CLI output bloat and an over-large always-loaded SKILL.md blow the metered budget. Avoid with **per-genre calibrated thresholds anchored on liked/real-artist tracks, a hard max-attempts terminator + ask-human fallback, full score logging**, compact-by-default CLI (arrays by ID only), on-trigger reference docs, and exercising the metered path early.

## Implications for Roadmap

Research implies an **M0 with parallel tracks** (one of which, the knowledge pipeline, starts immediately) followed by an M1 that consumes those foundations.

### Phase 1 (M0): Core spine -- schema, state machine, control-plane + CLI skeleton, capture, feature/embedding worker
**Rationale:** Everything depends on F1/F2; the typed graph + by-ID storage + DSP/CLAP lib are the shared backbone for composition, reference, sampling, and sparse-genre grounding.
**Delivers:** Fragment capture to analyzed; Postgres+pgvector graph; object storage by ID; nameless CLI skeleton with **compact-by-default** output; Postgres-backed job queue (sqlxmq).
**Addresses:** Core-loop capture (table stakes); shared audio feature pipeline.
**Avoids:** Pitfall 10 (token discipline -- compact CLI, ignore file from day one); sets up Pitfall 6 (provenance typing).

### Phase 2 (M0, parallel -- start day one): Offline knowledge pipeline + first authored Skills
**Rationale:** As foundational as the fragment graph; agents cannot produce good work without grounded craft. Only hard dep is YouTube tooling, so it runs concurrently with Phase 1. The make-or-break build; should be deep-planned.
**Delivers:** Local throttled ingestion with snapshot-on-ingest + extractability scoring + ASR fallback; two-pass extract-then-synthesize with citation-verification gate; layered SKILL.md output; **the P1 north-star cells authored first**; sparse-genre grounding (decompose + audio analysis) for alt-piano.
**Addresses:** KNOW table stakes + the layered-output differentiator; the production-stack-of-skill P1 cluster.
**Avoids:** Pitfalls 1, 2, 3, 4, 5.

### Phase 3 (M0, parallel): Reference-track context + persistent stem library + sampling provenance
**Rationale:** Reuses Phase 1 DSP/CLAP + Demucs; additive schema + state-machine invariant. Stem separation is shared by REF and SAMPLE -- build once.
**Delivers:** reference_tracks/reference_context/stems/sample_attribution schema; reference upload to non-melodic targets + vibe; Demucs stem library retained indefinitely; promote-stem to sampled fragment behind the **attribution-completeness gate**; **rights-status field**; frontend upload/browser/credits view.
**Uses:** Demucs, CLAP, pyloudnorm, R2.
**Implements:** Reference-as-context (not fragment) and sampled-on-the-human-path patterns.
**Avoids:** Pitfalls 6 (typed non-cloning), 7 (rights status).

### Phase 4 (M1): Melody-conditioned generation + eval gate + mix/master + credits export
**Rationale:** Consumes M0 foundations (authored Skills drive the arranger; reference_context conditions generation; sampling feeds credits export). The long pole is whichever of authored-craft vs generation+gate is sequenced last.
**Delivers:** Generation behind a worker interface; eval gate with per-genre calibrated thresholds + max-attempts terminator + the clone-leak negative check; one mix chain + master to LUFS; export with credits sheet.
**Uses:** MusicGen-Stem / MuseControlLite, pedalboard.
**Avoids:** Pitfalls 6, 8 (generator license + GPU metering, CPU smoke path), 9 (threshold calibration + loop bounding), 10.

### Phase Ordering Rationale

- **Dependency-correct:** F1 (schema/state machine) and F2 (storage + DSP lib) gate everything; the knowledge pipeline is independent except for the sparse-genre leg (needs F2 workers/lib), so it parallelizes from day one.
- **Architecture-grouped:** the offline pipeline is isolated as a sibling track (hard wall from runtime); control-plane schema deltas, worker job types, and frontend each form a clean concurrent track.
- **Pitfall-aware:** the highest-stakes integrity work (distillation, non-cloning typing, rights status) is pushed early -- cheap to build in, expensive to retrofit. Generation/eval economics land in M1 where GPU and metered tokens first bite.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Knowledge pipeline):** central make-or-break build with no turnkey tool -- claim-mining/scrutiny prompt design, citation-verification gate, and consensus/conflict separation are MEDIUM-confidence. Flag for dedicated deep planning. Sparse-genre grounding needs its own treatment.
- **Phase 4 (Generation + eval gate):** generator checkpoints (MusicGen-Stem availability, MuseControlLite backbone license) are research-grade and fast-moving; per-genre threshold calibration has no labeled ground truth yet.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Core spine):** axum/sqlx/Postgres patterns are well-documented and the PRD already specifies the design.
- **Phase 3 (Reference + sampling):** Demucs/CLAP/pyloudnorm are established; the integration shape is HIGH-confidence and derives from the PRD grammar.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Locked Rust/Python/storage stack validated for 2026; queue-deferral and license flags well-sourced. MEDIUM only on generator-weight availability. |
| Features | HIGH | Genre/production craft and sampling/attribution norms verified against producer sources. MEDIUM on the novel tutorials-to-authored-Skills feature shape (few precedents). |
| Architecture | HIGH | Integration design derives directly from the locked PRD grammar (provenance/lineage, eval-gate-as-invariant, Skill+CLI, by-ID storage). |
| Pitfalls | HIGH | Most verified against tooling docs and 2025-26 reports; sparse-genre and eval-threshold items MEDIUM (judgment-based). |

**Overall confidence:** HIGH

### Gaps to Address

- **Distillation prompt design and consensus/conflict separation (MEDIUM):** no turnkey tool -- prototype the two-pass extract-then-synthesize + verification gate early; human spot-audit before promotion. Handle in Phase 2 deep planning.
- **Generator checkpoint availability + licenses (MEDIUM):** confirm MusicGen-Stem weights and MuseControlLite backbone terms; keep generator strictly behind the worker interface so a swap is a config change. Handle in Phase 4 research.
- **Eval-gate thresholds per genre (MEDIUM):** no labeled ground truth -- anchor on the user liked tracks + real-artist tracks from the sparse-genre pipeline; ship per-genre configurable, log all scores, recalibrate.
- **Transcript coverage for newest alt-piano artists (MEDIUM):** mitigated by the audio-grounding leg; accept partial coverage + LOW-confidence labels.
- **Minor open items:** exact reference-CLAP advisory threshold; whether a thin nameless-skills-list surface is ever needed (default: no); store trimmed stem slice as the fragment audio_uri while retaining the full stem in the library.

## Sources

### Primary (HIGH confidence)
- nameless-prd.md sections 4-7, 10, 12, 13, 15, 16 -- locked architecture, state machine, eval gate, capability layer, token strategy, licensing, risks.
- .planning/PROJECT.md -- two-knowledge-layer separation, non-cloning + attribution decisions, no-RAG decision.
- Official repos/docs -- Demucs (maintenance status, model list), librosa 0.11, faster-whisper (CUDA 12/cuDNN 9), audio-separator/BS-RoFormer, axum 0.8 + sqlx 0.8, NATS vs Redis Streams, Claude Skill authoring best practices.
- License facts -- MusicGen CC-BY-NC 4.0 weights, pedalboard GPL-3.0, basic-pitch Apache-2.0, Demucs MIT; youtube-transcript-api cloud-IP blocking (GitHub #511).
- Producer/educator sources -- InspiredByBeatz, RouteNote, Splice, Roland, LANDR, MusicRadar, DeepHouseNetwork, Tracklib.

### Secondary (MEDIUM confidence)
- LLM claim-extraction / citation-enforced synthesis patterns (arXiv 2511.16198 SemanticCite; production pipeline blogs).
- MusicGen-Stem (ICASSP 2025) / MuseControlLite (ICML 2025) -- design HIGH, weight availability/backbone license MEDIUM.
- CLAP coarseness for fine-grained genre (arXiv 2206.04769, 2409.09213); MuQ-MuLan comparison.
- YouTube PoToken / 2025-26 cloud-range blocking (SkipTheWatch, DEV).

### Tertiary (LOW confidence)
- torchaudio maintenance/phase-down (ecosystem announcements -- flag for re-verify).
- US sound-recording sampling precedent (Bridgeport -- general legal knowledge, not legal advice).

---
*Research completed: 2026-06-26*
*Ready for roadmap: yes*
