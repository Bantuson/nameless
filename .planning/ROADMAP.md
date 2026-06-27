# Roadmap: Nameless

## Overview

This roadmap delivers the **M0 foundation** of Nameless: the production-knowledge layer, fragment capture + feature/embedding graph, reference-track context, the persistent sampling/stem library, and a thin web UI. Generation, the eval gate, and mix/master are M1 and are deliberately out of this milestone. The journey runs as parallel tracks: a **core spine** (Phases 1-2) builds the typed fragment graph + shared DSP/CLAP feature worker that gates most other work; an **offline knowledge pipeline** (Phases 3-6) — the make-or-break, two-pass extract-then-synthesize build — runs largely concurrently since its only hard external dependency is YouTube tooling; the **reference + sampling** track (Phases 7-8) reuses the shared Demucs/CLAP capability and front-loads the integrity boundaries (typed non-cloning, attribution-completeness, rights-status); and the **thin web UI** (Phase 9) sits on top of the CLI/control-plane surfaces. Each phase is a vertical, end-to-end usable slice that delivers an observable producer-facing capability.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

**Parallelization:** Phase 3 (knowledge ingestion) is independent of the core spine and can start day one. Phases 4-6 chain off Phase 3; Phase 6 also needs the Phase 2 audio pipeline. Phases 7-8 chain off the core spine. Phase 9 sits on top of Phases 2/7/8.

- [x] **Phase 1: Typed Capture Spine** - Capture a fragment into the durable typed graph; storage, state machine, CLI, and job queue (completed 2026-06-27)
- [x] **Phase 2: Fragment Analysis** - A captured fragment reaches `analyzed` with features + embeddings, searchable by audio/note ✓ (58 tests pass; course-mode)
- [x] **Phase 3: Tutorial Ingestion + Snapshot Corpus** - Ingest 100+ north-star tutorials into a snapshotted, extractability-scored corpus ✓ (77 tests pass; course-mode)
- [x] **Phase 4: Cited Claim Mining + Cross-Reference** - Extract atomic, individually-cited claims and preserve consensus/conflict as first-class data ✓ (134 tests pass; course-mode)
- [ ] **Phase 5: Synthesize + Verify the First Authored Skills** - Synthesize only over the claim set into layered, citation-verified SKILL.md for the P1 cells
- [ ] **Phase 6: Sparse-Genre Grounding** - Author a confidence-labeled alt-piano skill from parent-technique decomposition + real released-track audio
- [ ] **Phase 7: Reference-Track Context** - Upload a finished song; get its vibe + non-melodic sonic targets, with cloning structurally impossible
- [ ] **Phase 8: Stem Library + Attributed Sampling** - Separate tracks into a retained stem library; promote a stem to an attributed sample with a credits sheet
- [ ] **Phase 9: Thin Web UI** - Do the core M0 loop — capture, reference upload, stem sampling, project review — in the browser

## Phase Details

### Phase 1: Typed Capture Spine

**Goal**: A producer can capture an audio fragment with intent into a durable, typed fragment graph whose state machine structurally refuses to place unanalyzed work.
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Requirements**: CAP-01, CAP-02, CAP-05, CAP-06, CAP-07
**Success Criteria** (what must be TRUE):

  1. User can capture an audio fragment (hum, hook, beat, rhythm) with an attached intent note into a project via the `nameless` CLI and see it listed by ID.
  2. Raw audio is stored immutably in object storage (S3/R2) addressed by ID and is never echoed into CLI output — compact-by-default means IDs and summaries only, never waveforms or feature arrays.
  3. The typed Rust state machine makes it impossible to place a fragment that has not reached `analyzed`; the block is enforced by the harness, not by convention.
  4. Feature-extraction and separation work is enqueued on a durable Postgres-backed job queue (sqlxmq) that survives restart, retries on failure, and applies backpressure — no NATS/Redis.

**Plans**: 5/4 plans complete

- [x] 01-01-PLAN.md — Walking Skeleton: cargo workspace + ports-and-adapters + `nameless --local` capture→store(content-hash)→list end-to-end, no Postgres [CAP-01, CAP-02, CAP-06]
- [x] 01-02-PLAN.md — Complete typed fragment lifecycle + exhaustive transition tests ("cannot place unanalyzed") [CAP-05]
- [x] 01-03-PLAN.md — Durable job-queue seam: JobQueue trait + JobEnvelope + in-memory retry/backpressure + enqueue-on-capture [CAP-07]
- [x] 01-04-PLAN.md — Production adapters behind a `postgres` feature: Postgres repo + sqlxmq + S3/R2 + migrations (env-gated) [CAP-02, CAP-07]

### Phase 2: Fragment Analysis

**Goal**: A captured fragment becomes `analyzed` — carrying key/tempo/features and embeddings — and is retrievable by audio similarity or by note text.
**Mode**: mvp
**Depends on**: Phase 1
**Requirements**: CAP-03, CAP-04
**Success Criteria** (what must be TRUE):

  1. After capture, the shared feature worker extracts f0 contour, chroma, onsets/beat-grid/tempo, key, and loudness (LUFS), and the fragment advances to `analyzed`.
  2. User can see a fragment's key and tempo in the CLI graph/summary output (never raw arrays).
  3. A CLAP audio embedding and a note-text embedding are computed and indexed in pgvector.
  4. User can retrieve fragments by note text or by audio similarity and get ranked matches.

**Plans**: TBD

### Phase 3: Tutorial Ingestion + Snapshot Corpus

**Goal**: Build a snapshotted, extractability-scored corpus of 100+ north-star production tutorials whose citations survive channel takedowns.
**Mode**: mvp
**Depends on**: Nothing (parallel track — only hard external dependency is YouTube tooling)
**Requirements**: KNOW-01, KNOW-02, KNOW-03, KNOW-04
**Success Criteria** (what must be TRUE):

  1. User can run discovery across the production-stage × north-star-genre grid plus artist/producer-anchored searches (Sonder / Brent Faiyaz; Ben Produces, Liyana Ricky, Lowbass Djy) and get a queue of candidate tutorials.
  2. Transcripts are fetched locally (yt-dlp + youtube-transcript-api) with throttling and snapshot-on-ingest (content hash + retrieval date), so a later channel takedown does not break citations.
  3. When captions are missing or low quality, the system falls back to faster-whisper ASR and records an extractability score, flagging visual-only / low-signal sources instead of faking them into a skill.
  4. At least 100 tutorial videos, concentrated on the north-star fusion genres, are ingested and visible in the corpus registry.

**Plans**: TBD

### Phase 4: Cited Claim Mining + Cross-Reference

**Goal**: Turn the transcript corpus into a registry of atomic, individually-cited claims grouped into preserved consensus and conflict — an extraction pass only, with no synthesis.
**Mode**: mvp
**Depends on**: Phase 3
**Requirements**: KNOW-05, KNOW-06
**Success Criteria** (what must be TRUE):

  1. The extraction pass produces atomic claims, each bound to a source video ID + timestamp, in a typed production-stage × genre schema — with no synthesis introduced at this stage.
  2. User can inspect any claim and trace it back to the exact source quote and timestamp.
  3. Cross-referencing groups claims by topic and preserves both consensus and contradictions as first-class data — a conflict is recorded, never silently deleted.

**Plans**: TBD

### Phase 5: Synthesize + Verify the First Authored Skills

**Goal**: Synthesize only over the extracted claim set into layered, citation-verified SKILL.md files for the P1 north-star cells, spot-audited before they ship.
**Mode**: mvp
**Depends on**: Phase 4
**Requirements**: KNOW-07, KNOW-08, KNOW-09, KNOW-11
**Success Criteria** (what must be TRUE):

  1. Synthesis runs only over the extracted claim set and emits layered output per skill — an opinionated default PLUS the preserved consensus/conflict evidence, every claim carrying its citation.
  2. The programmatic citation-verification gate rejects any synthesized claim not traceable to a real source quote/timestamp; no invented numbers reach a Skill.
  3. The first authored Claude Skills (SKILL.md + reference docs) for the P1 north-star cells are committed to `skills/production/` as the "production stack of skill," authoring those cells first.
  4. User can review a sampled set of authored skills in a human spot-audit step before they are promoted/shipped.

**Plans**: TBD

### Phase 6: Sparse-Genre Grounding

**Goal**: Author a grounded, confidence-labeled skill for under-tutorialized sounds (alternative piano, newer named artists) by decomposing parent techniques and analyzing real released tracks through the audio/CLAP pipeline.
**Mode**: mvp
**Depends on**: Phase 5, Phase 2
**Requirements**: KNOW-10
**Success Criteria** (what must be TRUE):

  1. For an under-tutorialized sound, the system decomposes it into parent techniques (amapiano/log-drum groove + jazzy/soulful piano + deep-house space) and authors the skill from those ingredients rather than fabricating craft.
  2. The system analyzes the named artists' actual released tracks via the audio/CLAP feature pipeline and folds the extracted sonic signatures into the skill.
  3. Claims grounded on thin evidence are explicitly labeled low-confidence rather than presented as settled craft.

**Plans**: TBD

### Phase 7: Reference-Track Context

**Goal**: A producer can upload a finished song they love and get its vibe + measurable non-melodic sonic targets as project conditioning context — with cloning made structurally impossible.
**Mode**: mvp
**Depends on**: Phase 2
**Requirements**: REF-01, REF-02, REF-03, REF-04
**Success Criteria** (what must be TRUE):

  1. User can upload a reference song into a persistent personal library, stored immutably by ID.
  2. The system extracts a CLAP style embedding, genre, tempo range, LUFS, tonal balance, and stereo width, plus an LLM vibe description (mood, space, era, texture, energy), and presents it as a summary.
  3. No melody, chroma, or structure is ever extracted or stored for a reference — non-cloning is enforced in the schema and state machine (there is no field for it to leak into), not by convention.
  4. User can attach one or more reference contexts to a project as conditioning context for later generation/mixing.

**Plans**: TBD

### Phase 8: Stem Library + Attributed Sampling

**Goal**: A producer can separate any uploaded track into a retained stem library, promote a stem to an attribution-complete `sampled` fragment at any time, and export a credits sheet.
**Mode**: mvp
**Depends on**: Phase 7 (and the Phase 2 worker plane)
**Requirements**: SAMP-01, SAMP-02, SAMP-03, SAMP-04, SAMP-05
**Success Criteria** (what must be TRUE):

  1. An uploaded track is separated into clean stems (Demucs) that are retained in the persistent library indefinitely and remain browsable.
  2. User can promote any stem to a `sampled` fragment in a project at any time — even weeks after upload — and it travels the human lifecycle (analyzed → placed), never the eval gate.
  3. The state machine blocks placing a sampled fragment until attribution is complete (source track, artist, stem, time-range); incomplete attribution is a hard block, no bypass.
  4. Each sample carries a `rights-status` field (copyrighted-uncleared / royalty-free / own-work / unknown), and the system states in-context that attribution is not permission.
  5. User can export a project credits sheet that lists every sample used (source / artist / stem / time-range).

**Plans**: TBD

### Phase 9: Thin Web UI

**Goal**: A producer can do the core M0 loop — capture, reference upload, stem sampling, and project review — through a minimal web interface instead of the CLI.
**Mode**: mvp
**Depends on**: Phase 2, Phase 7, Phase 8
**Requirements**: UI-01, UI-02, UI-03, UI-04
**Success Criteria** (what must be TRUE):

  1. User can record/capture a fragment and attach an intent note via a minimal web interface.
  2. User can upload a reference track and view its extracted vibe + sonic-target summary in the browser.
  3. User can browse the persistent stem library and trigger "add as sample" on any stem.
  4. User can view a project's fragment graph (nodes, notes, key/tempo) and its sample credits.

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. Tracks may overlap where dependencies allow (Phase 3 is independent of the core spine; Phases 7-8 depend only on the spine).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Typed Capture Spine | 5/4 | Complete   | 2026-06-27 |
| 2. Fragment Analysis | 1/1 | ✓ Complete (58 tests) | 2026-06-27 |
| 3. Tutorial Ingestion + Snapshot Corpus | 1/1 | ✓ Complete (77 tests) | 2026-06-28 |
| 4. Cited Claim Mining + Cross-Reference | 1/1 | ✓ Complete (134 tests) | 2026-06-28 |
| 5. Synthesize + Verify the First Authored Skills | 0/TBD | Not started | - |
| 6. Sparse-Genre Grounding | 0/TBD | Not started | - |
| 7. Reference-Track Context | 0/TBD | Not started | - |
| 8. Stem Library + Attributed Sampling | 0/TBD | Not started | - |
| 9. Thin Web UI | 0/TBD | Not started | - |
