# Nameless

> Working codename — rename before any code ships (PRD open decision #5).

## What This Is

Nameless is a local-first, audio-native music composition system for a solo producer. You capture musical fragments straight into a project — a hum, a hook, a beat, a rhythm — and annotate each with intent ("chorus hook, sits over the second drop"). The system understands the audio natively (pitch, key, tempo, timbre), proposes an arrangement, and generates the missing parts (bass, drums, pads) conditioned on your actual recordings so they lock to your key and tempo. Every generated part is checked against your source by a hard eval gate before it is allowed in. You mix through one chain, master to a streaming loudness target, and export. It exists to translate the music you hear in your head into finished, audible work — for people who hear melodies but cannot name them.

This project builds the full Nameless system described in `nameless-prd.md`, with **three capabilities added during initialization**, the first of which is foundational:

1. **A tutorial-derived production-knowledge layer (M0 foundation).** Scripts ingest transcripts from 100+ YouTube production tutorials across the whole stack and target genres, then cross-reference and scrutinize them into a "logical production stack of skill" emitted as authored **Claude Skills** that teach the arranger/mixer agents real craft. This is the missing answer to "where does the SKILL.md knowledge come from" — and it is as foundational as the PRD's fragment-memory graph.
2. **A reference-track context layer.** Upload a finished song you love; the system extracts its vibe/atmosphere and measurable sonic targets as conditioning context for generation and mixing — **never to recreate or clone it**, only to better translate your intent.
3. **A sampling + persistent stem library.** Every uploaded track is stem-separated and retained indefinitely; any stem can be promoted to an attributed `sampled` fragment at any time, with provenance and an exported credits sheet — attribution-clean sampling rather than copy-and-claim-original.

## Core Value

Translate the music in your head into genuinely *good* output. Two grounding forces make that real: **production knowledge** mined from how the craft is actually taught, and **your taste** expressed through reference tracks and samples. Quality in, quality out. The north-star sound is **Sonder / Brent Faiyaz vocal layering and atmosphere**, fused across **R&B × amapiano × deep house × alternative piano**.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Hypotheses until shipped and validated. -->

**Production-knowledge layer (M0 foundation)**

- [ ] System ingests transcripts from ≥100 YouTube production tutorials spanning the full stack (beats, vocals, instruments, plugins/presets, mixing, mastering, atmospheres) and target genres (R&B, amapiano, deep house, alternative piano)
- [ ] Videos are selected by system discovery across genre+stage queries, plus artist/producer-anchored search (Sonder/Brent Faiyaz; Ben Produces, Liyana Ricky, Lowbass Djy)
- [ ] System cross-references and scrutinizes claims across videos, producing layered output: an opinionated default per skill PLUS preserved consensus/conflict evidence, every claim traceable to source video + timestamp
- [ ] Distilled knowledge is organized into a logical "production stack of skill" and emitted as authored Claude Skills (SKILL.md + reference docs) the arranger/mixer agents load
- [ ] For under-tutorialized sounds (alternative piano, newer named artists), system grounds the skill by (a) decomposing into parent techniques — amapiano groove/log-drum + jazzy/soulful piano + deep-house space — and (b) analyzing the artists' actual released tracks through the audio/CLAP feature pipeline to extract real sonic signatures

**Reference-track context + sampling library**

- [ ] User can upload a reference song; system extracts vibe/atmosphere (CLAP embedding + LLM vibe description: mood, space, era, texture, energy) and measurable non-melodic sonic targets (genre, tempo range, LUFS, tonal balance, stereo width) as generation/mix context — never melody, chords, or structure
- [ ] Uploaded tracks persist in a personal library with cleanly separated stems (Demucs) retained and browsable indefinitely
- [ ] User can promote any stem to a `sampled` fragment in a project at any time (even weeks after upload); provenance records source track, artist, stem, and time-range
- [ ] Export auto-produces a credits sheet listing every sample used in the track

**Core Nameless loop (from PRD, woven into this build)**

- [ ] User can capture audio fragments with intent notes; system extracts features + embeddings and reaches `analyzed` state (M0)
- [ ] System proposes arrangements and generates missing parts conditioned on the user's audio, locked to key/tempo (M1)
- [ ] Every `ai_generated` fragment passes a hard eval gate (melody fidelity, key match, tempo lock, loudness delta, CLAP alignment) before placement — no bypass (M1)
- [ ] One mix chain per track + master to LUFS target + export (M1)

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Recreating / cloning a reference track** — reference audio is context only; melody, chords, and structure are never reproduced. The whole point is intent translation, not imitation.
- **Commercial distribution and licensing clearance** — deferred (PRD §15). Sampling is attribution-tracked for personal/portfolio use; clearance gating/flags are not built yet.
- **RAG / pgvector knowledge base for tutorial knowledge** — deliberately chose authored Claude Skills + scripts instead, on token-strategy grounds (Skill costs ~its description until triggered; a vector dump bloats context and reasons worse).
- **Mining non-tutorial videos (interviews, reactions, breakdowns) as a primary source** — not prioritized for v1; grounding leans on tutorial discovery + parent-technique decomposition + audio analysis. Revisit if coverage proves too thin.
- **Real-time collaboration / multi-user projects** — PRD non-goal.
- **Lyric generation and vocal synthesis** — PRD non-goal.
- **Mobile native app** — PRD non-goal; web-first.
- **Plugin marketplace** — PRD non-goal.
- **Full mixing console** — M1 ships one chain per track, not a console (console + metering is M3).

## Context

- **Existing design:** `nameless-prd.md` is a complete, senior-grade PRD (sections 1–17) covering the core loop, architecture, tech stack, milestones M0–M3, token strategy, licensing, risks, and open decisions. This initialization extends it; it does not replace it.
- **Architecture (from PRD):** Rust control plane (axum API, typed fragment state machine, render DAG + eval-gate enforcement, the `nameless` CLI) + Python worker plane (librosa/torchaudio, torchcrepe, basic-pitch, Demucs, MusicGen-Stem / MuseControlLite, LAION-CLAP, pedalboard) + TypeScript/React frontend (M0–M1 capture/notes/graph view; M2 Tone.js real-time surface). NATS JetStream seam; Postgres + pgvector; S3/R2 object storage addressed by ID. Capability layer = Skill + CLI, **no always-on MCP** — audio and feature arrays never enter agent context.
- **Two distinct knowledge layers — do not conflate:** (1) the PRD's **fragment-memory graph** is per-project memory of *your* fragments; (2) the new **production-knowledge layer** is *general craft* mined from tutorials. Both are M0 foundations; both feed the agents but serve different purposes.
- **Aesthetic anchors:** Sonder / Brent Faiyaz for vocal layering and atmospheric sound; alternative piano (a newer amapiano subgenre) via Ben Produces, Liyana Ricky, Lowbass Djy. The creative goal is a personal *fusion*, not a clone of any one lane.
- **Stem separation + provenance already exist in the PRD:** Demucs is in the worker plane; the fragment graph already tracks provenance (`human_recorded | ai_generated | derived`) and lineage. Sampling extends provenance with `sampled` + attribution metadata — a natural addition, not a new subsystem.
- **Solo, local-first, personal/portfolio grade.** Orchestration default = interactive Claude Code (flat-rate); Agent SDK / direct API paths are metered and treated as real spend.

## Constraints

- **Tech stack**: Rust + Python + TypeScript/React per PRD — let each language do what its ecosystem wins; clean boundary between them.
- **Token budget**: metered agent paths draw on a capped credit pool with overflow disabled. Skill + CLI + externalized queryable graph keep context near-empty by construction; audio/feature dumps run file-to-file and never enter context.
- **Compute**: M0 runs comfortably on CPU; generation and stem separation (M1) want a GPU — budget a rented/hosted worker.
- **Dev machine**: ~4GB RAM, no Docker — verification must be RAM-safe (SQLite / stubs / fixtures). A live Postgres server, the heavy ML stack, live YouTube ingestion, and cloud (S3/R2) storage are built here but verified in the user's real environment. See `.planning/ENVIRONMENT.md`.
- **Licensing**: research/non-commercial generator licenses (e.g. MusicGen) are fine for personal/portfolio; commercial output would require swapping to a clear-licensed generator.
- **Solo build**: scope must stay buildable and maintainable by one person, local-first.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Knowledge layer = authored Claude Skills + scripts (not RAG) | Matches PRD token strategy; opinionated, loadable craft beats a fuzzy vector dump | — Pending |
| Knowledge layer is an M0 foundation, woven into the full Nameless build | Agents can't produce good work without grounded craft — as foundational as fragment memory | — Pending |
| Scrutiny = layered: opinionated default + cited consensus/conflict evidence | Actionable for agents, auditable for trust — "quality in, quality out" | — Pending |
| Sourcing = system-discovered full-stack tutorials + artist/producer-anchored search | Breadth across the stack plus the specific target sound | — Pending |
| Sparse-genre grounding = decompose into parent techniques + analyze actual released tracks | Alt piano is under-tutorialized; reconstruct from real ingredients + real audio, never fabricate | — Pending |
| Reference track = vibe/atmosphere + measurable non-melodic sonic targets, strictly non-cloning | A finished song is better context than a description; intent translation, not imitation | — Pending |
| Uploaded tracks = persistent stem library; any stem promotable to an attributed sample anytime | Attribution-clean sampling is more honest than copy-and-claim-original | — Pending |
| Export produces a credits sheet for all samples used | Surfaces lineage and attribution honestly | — Pending |
| Build as a course/learning project: complete end-to-end code (incl. deep ML), NOT run on the dev machine | 4GB/no-Docker/no-Rust box can't run it; user wants to learn the craft and own a real codebase | — Pending |
| Testability-first as a persistent law: DI/ports-and-adapters, pure functions, separation of concerns, loose coupling | Makes the code teachable, reviewable, and genuinely testable even unrun; holds across phases/sessions/milestones | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-26 after initialization*
