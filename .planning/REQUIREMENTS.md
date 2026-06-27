# Requirements: Nameless

**Defined:** 2026-06-26
**Core Value:** Translate the music in your head into genuinely good output — by grounding the agents in real production craft (knowledge layer) and your taste (reference tracks + samples). Quality in, quality out.

**v1 milestone (M0):** Foundations — the production-knowledge layer, fragment capture + feature graph, reference-track context, the sampling/stem library, and a thin web UI. Generation, the eval gate, and mix/master (M1) are deferred to the next milestone. Knowledge breadth is focused on the north-star fusion (R&B × amapiano/alternative piano × deep house), not broad genre coverage.

## v1 Requirements

### Knowledge Pipeline (KNOW) — the M0 foundation

- [ ] **KNOW-01**: System discovers candidate tutorials across the production-stage × north-star-genre grid, plus artist/producer-anchored searches (Sonder / Brent Faiyaz; Ben Produces, Liyana Ricky, Lowbass Djy)
- [ ] **KNOW-02**: System fetches transcripts locally (yt-dlp + youtube-transcript-api) with throttling and snapshot-on-ingest (content hash + retrieval date) so citations survive channel takedowns
- [ ] **KNOW-03**: System falls back to faster-whisper ASR when captions are missing or low quality, and scores each source's extractability — flagging visual-only / low-signal content rather than faking it into a skill
- [ ] **KNOW-04**: System ingests at least 100 tutorial videos, concentrated on the north-star fusion genres
- [ ] **KNOW-05**: System extracts atomic, individually-cited claims (source video ID + timestamp) into a typed production-stage × genre schema — extraction pass only, no synthesis
- [ ] **KNOW-06**: System cross-references claims across sources, preserving both consensus and contradictions as first-class data (a default is a decision on top of preserved conflict, never a deletion)
- [ ] **KNOW-07**: System synthesizes *only over the extracted claim set* into layered output — an opinionated default per skill PLUS the preserved consensus/conflict evidence with citations
- [ ] **KNOW-08**: A programmatic citation-verification gate rejects any synthesized claim not traceable to a real source quote/timestamp; the LLM never invents numbers
- [ ] **KNOW-09**: System emits distilled knowledge as authored Claude Skills (SKILL.md + reference docs) organized as the "production stack of skill," authoring the P1 north-star cells first
- [ ] **KNOW-10**: For under-tutorialized sounds (alternative piano, newer named artists), system grounds the skill by decomposing into parent techniques AND analyzing the artists' actual released tracks via the audio/CLAP pipeline, labeling low-confidence where evidence is thin
- [ ] **KNOW-11**: A human spot-audit step lets the user review a sample of authored skills before they are promoted/shipped

### Core Spine & Capture (CAP)

- [x] **CAP-01**: User can capture an audio fragment (hum, hook, beat, rhythm) into a project with an attached intent note
- [x] **CAP-02**: System stores raw audio immutably in object storage (S3/R2), addressed by ID — audio never enters the agent's context
- [x] **CAP-03**: Feature worker extracts f0 contour, chroma, onsets/beat-grid/tempo, key, and loudness (LUFS) for each fragment
- [x] **CAP-04**: System computes a CLAP audio embedding and a note-text embedding, indexed in pgvector for retrieval by note or by audio similarity
- [x] **CAP-05**: Fragment advances through the typed Rust state machine to `analyzed`; the state machine makes it impossible to place an unanalyzed fragment
- [x] **CAP-06**: The `nameless` CLI exposes capture / analyze / fragments / graph subcommands with compact-by-default output (IDs and summaries, never waveforms or feature arrays)
- [x] **CAP-07**: A durable Postgres-backed job queue (sqlxmq) carries feature-extraction and separation jobs with retry and backpressure (no NATS/Redis at solo scale)

### Reference-Track Context (REF)

- [ ] **REF-01**: User can upload a reference song into a persistent personal library
- [ ] **REF-02**: System extracts non-melodic vibe + sonic targets from a reference — CLAP style embedding, genre, tempo range, LUFS, tonal balance, stereo width — plus an LLM "vibe description" (mood, space, era, texture, energy)
- [ ] **REF-03**: Reference data is structurally barred from the melodic-conditioning path — no melody/chroma/structure is extracted or stored for references; non-cloning is enforced in schema + state machine, not by convention
- [ ] **REF-04**: User can attach one or more reference contexts to a project as conditioning context for later generation/mixing

### Sampling & Stem Library (SAMP)

- [ ] **SAMP-01**: System separates an uploaded track into clean stems (Demucs) and retains them in the persistent library indefinitely
- [ ] **SAMP-02**: User can browse an uploaded track's stems and promote any stem to a `sampled` fragment in a project at any time — even weeks after upload
- [ ] **SAMP-03**: A `sampled` fragment travels the human lifecycle (analyzed → placed), not the eval gate; the state machine blocks placement until attribution is complete (source track, artist, stem, time-range)
- [ ] **SAMP-04**: Each sample carries a `rights-status` field (copyrighted-uncleared / royalty-free / own-work / unknown); the system states in-context that attribution is not permission
- [ ] **SAMP-05**: System generates a credits sheet for a project from its sample-attribution rows, listing every sample used (source / artist / stem / time-range)

### Thin Web UI (UI)

- [ ] **UI-01**: User can record/capture a fragment and attach an intent note via a minimal web interface
- [ ] **UI-02**: User can upload a reference track and view its extracted vibe + sonic-target summary
- [ ] **UI-03**: User can browse the persistent stem library and trigger "add as sample" on any stem
- [ ] **UI-04**: User can view a project's fragment graph (nodes, notes, key/tempo) and its sample credits

## v2 Requirements

Deferred to future milestones. Tracked but not in the current roadmap.

### Generation & Composition (M1)

- **GEN-01**: Arranger proposes song structure and generates missing parts conditioned on the user's audio, locked to key/tempo
- **GEN-02**: Hard eval gate (melody fidelity, key match, tempo lock, loudness delta, CLAP alignment) with per-genre calibrated thresholds + a max-attempts terminator; no bypass
- **GEN-03**: Reference-context CLAP advisory + a clone-leak negative check (generated-vs-reference melodic similarity) in the gate
- **GEN-04**: One mix chain per track + master to LUFS target + full export (with the credits sheet attached)

### Knowledge Breadth (v2)

- **KNOW-V2-01**: Broaden the production stack of skill to the P2 cells — jazz, hip-hop, afrobeats, afro house, afro tech, and full stage × genre coverage
- **KNOW-V2-02**: Mine non-tutorial sources (interviews, beat breakdowns, reactions) where formal how-tos are thin

### Later Milestones (M2 / M3)

- **RT-01**: Real-time Tone.js pad + multitrack timeline; live arrangement and mix edits (M2)
- **MIX-01**: Full mixing console with metering, mastering presets by genre, plugin host, symbolic editing surface (M3)
- **SAMP-V2-01**: Sample clearance / licensing workflow (revisited only if commercialization arrives)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Recreating / cloning a reference track | Reference audio is context only; melody, chords, and structure are never reproduced. The point is intent translation, not imitation. |
| Commercial distribution & licensing clearance | Deferred (PRD §15). Sampling is attribution + rights-status tracked for personal/portfolio use; clearance gating is not built. |
| RAG / pgvector knowledge base for tutorial knowledge | Chose authored Claude Skills + scripts instead, on token-strategy grounds. |
| Real-time collaboration / multi-user projects | PRD non-goal. |
| Lyric generation & vocal synthesis | PRD non-goal. |
| Mobile native app | PRD non-goal; web-first. |
| Plugin marketplace | PRD non-goal. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CAP-01 | Phase 1 | Complete |
| CAP-02 | Phase 1 | Complete |
| CAP-05 | Phase 1 | Complete |
| CAP-06 | Phase 1 | Complete |
| CAP-07 | Phase 1 | Complete |
| CAP-03 | Phase 2 | Complete |
| CAP-04 | Phase 2 | Complete |
| KNOW-01 | Phase 3 | Pending |
| KNOW-02 | Phase 3 | Pending |
| KNOW-03 | Phase 3 | Pending |
| KNOW-04 | Phase 3 | Pending |
| KNOW-05 | Phase 4 | Pending |
| KNOW-06 | Phase 4 | Pending |
| KNOW-07 | Phase 5 | Pending |
| KNOW-08 | Phase 5 | Pending |
| KNOW-09 | Phase 5 | Pending |
| KNOW-11 | Phase 5 | Pending |
| KNOW-10 | Phase 6 | Pending |
| REF-01 | Phase 7 | Pending |
| REF-02 | Phase 7 | Pending |
| REF-03 | Phase 7 | Pending |
| REF-04 | Phase 7 | Pending |
| SAMP-01 | Phase 8 | Pending |
| SAMP-02 | Phase 8 | Pending |
| SAMP-03 | Phase 8 | Pending |
| SAMP-04 | Phase 8 | Pending |
| SAMP-05 | Phase 8 | Pending |
| UI-01 | Phase 9 | Pending |
| UI-02 | Phase 9 | Pending |
| UI-03 | Phase 9 | Pending |
| UI-04 | Phase 9 | Pending |

**Coverage:**

- v1 requirements: 31 total (KNOW ×11, CAP ×7, REF ×4, SAMP ×5, UI ×4 — the prior "30" header undercounted KNOW by one)
- Mapped to phases: 31 (100%) ✓
- Unmapped: 0

---
*Requirements defined: 2026-06-26*
*Last updated: 2026-06-26 after roadmap creation (traceability mapped to 9 M0 phases)*
