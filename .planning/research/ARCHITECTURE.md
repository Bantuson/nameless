# Architecture Research

**Domain:** Audio-native AI music composition — integrating 3 new capabilities into a locked PRD architecture
**Researched:** 2026-06-26
**Confidence:** HIGH (integration design grounded in the locked PRD; external tooling facts verified)

> **Scope discipline.** The PRD (`nameless-prd.md`) LOCKS the core: Rust control plane (axum, typed fragment state machine, render DAG + eval-gate enforcement, `nameless` CLI) · Python worker plane (DSP, Demucs, generation, evaluator, mix/master) · TS/React frontend · NATS JetStream seam · Postgres + pgvector · S3/R2 by-ID · capability layer = Skill + CLI, **no MCP**, audio/feature arrays never enter agent context. This document does **not** redesign any of that. It specifies how the three new capabilities **bolt onto** that spine cleanly, and the dependency-correct build order.

---

## Standard Architecture

### System Overview (PRD spine + new capabilities, integrated)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       TS / React frontend  (capture, notes, graph)         │
│              + NEW: reference upload · stem-library browser · credits view  │
└───────────────────────────────────┬────────────────────────────────────────┘
                                HTTP / WS
┌───────────────────────────────────▼────────────────────────────────────────┐
│                            RUST CONTROL PLANE (locked)                       │
│  axum API · fragment graph (source of truth) · typed state machine          │
│  render DAG + EVAL GATE enforcement · the `nameless` CLI                     │
│                                                                             │
│  + NEW (additive, not new subsystems):                                      │
│    · provenance enum gains `sampled`  · attribution-completeness invariant   │
│    · reference_tracks / stems / sample_attribution graph entities            │
│    · `nameless reference …`, `nameless stems …`, `nameless sample …`,        │
│      `nameless credits …` subcommands                                        │
└──────────────┬──────────────────────────────────────────▲──────────────────┘
        typed job envelopes  (NATS JetStream)        typed results
┌──────────────▼──────────────────────────────────────────┴──────────────────┐
│                          PYTHON WORKER PLANE (locked)                        │
│  feature extraction (librosa/torchaudio/torchcrepe) · Demucs · generation    │
│  · evaluator (+CLAP) · mix/master (pedalboard)                               │
│  + NEW worker jobs (reuse the same DSP libs):                                │
│    · reference-context extract (CLAP embed + sonic targets)                  │
│    · stem-library separation (Demucs on uploaded tracks, retained)           │
└──────────────┬───────────────────────────────────────┬─────────────────────┘
        Postgres + pgvector                        object storage (S3/R2)
   (graph, notes, features, evals,            (raw + rendered + UPLOADED tracks
    + reference_context, stems index,          + retained STEMS, immutable, by ID)
    + sample_attribution)
                                                                             
        CAPABILITY LAYER  — Skill + CLI (no MCP)                              
        SKILL.md teaches behavior/thresholds/conventions; CLI drives the plane.

╔════════════════════════════════════════════════════════════════════════════╗
║   NEW · OFFLINE PRODUCTION-KNOWLEDGE PIPELINE  (build-time, NOT runtime)     ║
║   discover → fetch transcripts → claim-mine → cross-ref/scrutinize → emit    ║
║   Output = authored Claude Skills on disk  →  loaded by arranger/mixer       ║
║   (imports the worker-plane DSP lib for the sparse-genre audio-grounding leg)║
╚════════════════════════════════════════════════════════════════════════════╝
```

**The single most important boundary to get right:** the production-knowledge pipeline is an **offline authoring tool**, not a runtime plane. It runs on your machine when you want to (re)build the Skills, emits files to disk, and then **disappears from the runtime picture**. At runtime the agent sees only the emitted Skills (files) + the fragment graph (Postgres) + the CLI. The pipeline never sits in the request path and never holds runtime state.

### Two distinct knowledge layers (never conflate)

| | **Production-knowledge layer** (NEW) | **Fragment-memory graph** (PRD §6) |
|---|---|---|
| Holds | General craft mined from tutorials | *Your* fragments + derived signals |
| Scope | Cross-project, universal | Per-project, personal |
| Form | Authored Claude Skills = files on disk | Rows in Postgres + pgvector |
| Mutability | Read-only at runtime; rebuilt by pipeline | Mutable, lifecycle state machine |
| How agent reads | Skill progressive disclosure (frontmatter→body→refs) | CLI graph slices (notes + IDs) |
| Source of truth | Git-versioned `skills/` tree | `fragments`, `fragment_features`, … |
| Token cost | ~description until triggered | compact slices on demand |

They feed the same agents but answer different questions: *"how is a deep-house bassline mixed?"* (knowledge) vs *"which of my chorus hooks is unplaced?"* (graph). **They share no tables and no read path.** PROJECT.md explicitly rejects a RAG/pgvector knowledge base — knowledge stays as Skills/files on token-strategy grounds.

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| Knowledge pipeline (NEW, offline) | Turn ≥100 tutorials → layered authored Skills with cited consensus/conflict | Python CLI scripts; yt-dlp (discover) + youtube-transcript-api (fetch); LLM claim-mining/scrutiny; emits `SKILL.md` + refs |
| Sparse-genre grounding (NEW, offline) | For under-tutorialized sounds: decompose to parent techniques + analyze real released tracks | Imports worker-plane DSP/CLAP lib as a **module**, run synchronously (no NATS) |
| Skills tree (NEW, on disk) | The "production stack of skill" the agents load | `skills/production/**/SKILL.md` + reference docs, git-versioned |
| Knowledge registry (NEW, build-time only) | Claim→source(video+timestamp) provenance; drive incremental re-runs | Pipeline-local SQLite (NOT the runtime Postgres) |
| Reference-context extractor (NEW worker job) | Upload → CLAP embed + LLM vibe + measurable sonic targets (genre/tempo/LUFS/tonal balance/width) | New NATS job on existing worker plane; reuses CLAP + DSP |
| Stem-library separation (NEW worker job) | Demucs on uploaded tracks; stems retained indefinitely, browsable | Existing Demucs worker; new job type; stems → S3 by ID |
| Reference/stem/sample graph (NEW tables) | `reference_tracks`, `reference_context`, `stems`, `sample_attribution` | Postgres; control plane owns invariants |
| `sampled` provenance + attribution gate (NEW) | Promote a stem → attributed `sampled` fragment; block placement/render without complete attribution | Rust enum delta + state-machine invariant |
| Credits-sheet exporter (NEW) | At export, enumerate sampled fragments in the arrangement → credits sheet | Control plane query + render step; `nameless credits` |

---

## Recommended Project Structure

```
nameless/
├── control-plane/                # Rust (locked) — additive deltas only
│   └── src/
│       ├── graph/                # fragments, arrangements (PRD)
│       │   ├── provenance.rs     # ENUM DELTA: add `Sampled`
│       │   ├── reference.rs      # NEW: reference_tracks / reference_context
│       │   ├── stems.rs          # NEW: persistent stem library index
│       │   └── attribution.rs    # NEW: sample_attribution + completeness invariant
│       ├── state_machine.rs      # human/ai paths (PRD) + sampled path (human-like, no eval gate)
│       ├── gate.rs               # eval gate (PRD) + attribution gate (NEW invariant)
│       └── cli/                  # nameless subcommands
│           ├── reference.rs      # NEW
│           ├── stems.rs          # NEW
│           ├── sample.rs         # NEW
│           └── credits.rs        # NEW
│
├── workers/                      # Python worker plane (locked) — new job handlers
│   ├── features/                 # PRD feature extraction (shared lib)
│   ├── demucs/                   # PRD stem separation — also serves stem library
│   ├── reference_context.py      # NEW job: CLAP + sonic-target extraction
│   └── lib/                      # SHARED DSP/CLAP module (imported by pipeline too)
│
├── knowledge-pipeline/           # NEW · OFFLINE · not deployed at runtime
│   ├── discover.py               # genre×stage queries + artist/producer-anchored search (yt-dlp)
│   ├── fetch_transcripts.py      # youtube-transcript-api (+ backoff/rate-limit)
│   ├── claim_mine.py             # LLM: extract atomic claims per video w/ timestamps
│   ├── scrutinize.py             # cross-reference → consensus/conflict + citations
│   ├── ground_sparse.py          # parent-technique decomposition + audio analysis (imports workers/lib)
│   ├── emit_skill.py             # render layered SKILL.md + reference docs
│   ├── registry.sqlite           # build-time provenance + incremental-run state
│   └── README.md                 # how to (re)build the stack
│
├── skills/                       # AUTHORED OUTPUT — git-versioned, loaded at runtime
│   └── production/               # "the production stack of skill"
│       ├── arrangement/SKILL.md
│       ├── mixing/SKILL.md
│       ├── genres/
│       │   ├── amapiano/SKILL.md
│       │   ├── deep-house/SKILL.md
│       │   └── alt-piano/SKILL.md   # grounded via decomposition + audio analysis
│       └── _refs/                # reference docs loaded on demand (progressive disclosure)
│
└── frontend/                     # TS/React (locked) + reference upload / stem browser / credits view
```

### Structure Rationale

- **`knowledge-pipeline/` is a sibling of the runtime planes, not inside `workers/`.** It is build-time tooling. Keeping it separate prevents it from accidentally becoming a NATS consumer or leaking into runtime context. It *imports* `workers/lib` for the audio-grounding leg — a dependency on shared DSP code, not on the live worker plane.
- **`skills/` is a first-class, git-versioned directory, not a generated artifact buried in a build dir.** The Skills are the durable, reviewable craft asset; they should be diffable in PRs and editable by hand after generation. They are loaded by the agent via the standard Skill mechanism (frontmatter cheap at startup; body on trigger; `_refs/` on demand) — exactly the progressive-disclosure model that keeps runtime context thin.
- **Knowledge registry is SQLite local to the pipeline, deliberately NOT in the runtime Postgres.** Claim→source provenance is build-time audit data; the runtime agent never queries it. This enforces the two-layers separation at the storage level.
- **New control-plane code is additive files** (`reference.rs`, `stems.rs`, `attribution.rs`) rather than edits to the locked graph — keeps the PRD core intact and the new surface area reviewable.

---

## Architectural Patterns

### Pattern 1: Offline authoring pipeline → on-disk Skills (knowledge layer)

**What:** A staged batch pipeline (discover → fetch → claim-mine → scrutinize → emit) that produces authored Claude Skills as files. Runs on demand, not in the request path.

**When:** Whenever you (re)build or extend the production stack. Incremental: `registry.sqlite` tracks which videos/claims are already processed so re-runs only touch new sources.

**Trade-offs:** (+) Zero runtime cost beyond Skill description until triggered; cited, auditable, hand-editable; matches PRD token strategy. (+) Decoupled — model churn in claim-mining never touches the runtime. (−) Skills can go stale; rebuild is a manual step. (−) Quality depends on transcript availability and scrutiny prompt quality.

**The layered SKILL.md is the key output contract** — opinionated default on top, evidence underneath:

```markdown
---
name: deep-house-mixing
description: How deep house low-end, space, and groove are mixed. Load when
  arranging or mixing deep-house / amapiano-adjacent material.
---
## Default (do this)
Side-chain the bass to the kick; high-pass pads ~200Hz; keep the sub mono < 120Hz...

## Consensus  (n sources agree)
- Mono sub-bass below ~100–120 Hz — [Ben Produces @12:30], [LowbassDjy @04:10]

## Conflict  (sources disagree — judgment call)
- Reverb on the kick: [A @08:00] says never; [B @15:20] uses short room. Default: dry.

## Provenance
Every claim ↑ traces to video_id + timestamp (see knowledge-pipeline/registry.sqlite).
```

### Pattern 2: Reference track as *conditioning context*, not a fragment

**What:** An uploaded reference track is a distinct entity (`reference_tracks`) whose *extracted context* (`reference_context`: CLAP embedding + LLM vibe description + measurable non-melodic targets) is attached to a project and fed as **conditioning input** to arranger/mixer/generator/eval-gate. It is **never** turned into a placeable fragment and **never** contributes melody/chords/structure.

**When:** User uploads a finished song they love to steer vibe + sonic targets. The non-cloning guarantee is structural: reference context exposes only `genre, tempo_range, lufs, tonal_balance, stereo_width, vibe_text, clap_embedding` — there is no melody/chroma/structure field on it to leak.

**Trade-offs:** (+) Clean separation keeps "imitate the vibe" from ever becoming "reproduce the song." (+) Reuses CLAP + DSP already in the worker plane. (−) Requires the generator/eval-gate to accept an optional conditioning bundle (additive to their job envelopes).

```
arranger/generator job envelope (additive, optional):
  { fragment_ids:[…], target_key, target_tempo,
    reference_context: { clap_embedding, lufs, tonal_balance, stereo_width,
                         genre, tempo_range }  // vibe + sonic targets ONLY
  }
eval gate gains an optional CLAP-alignment-to-reference score (advisory, not a hard fidelity gate).
```

### Pattern 3: `sampled` fragments travel the human path + an attribution gate

**What:** A stem from the persistent library is promoted to a fragment with `provenance = sampled`. Because a sample is **real source audio** (not a generation needing fidelity-vs-source scoring), it travels the **human** lifecycle, **not** the AI path — it does **not** go through the eval gate:

```
human:   captured  -> analyzing -> analyzed -> placed -> mixed -> rendered
sampled: imported  -> analyzing -> analyzed -> placed -> mixed -> rendered   (same shape, no eval gate)
ai:      requested -> generating -> generated -> evaluating -> {promoted|rejected}   (eval gate HERE)
```

But sampled fragments add a **new invariant the state machine enforces**: the control plane refuses the `analyzed → placed` (and any render) transition unless **attribution is complete** (source track, artist, stem, time-range present). This mirrors the eval gate's role — *the agent explores; the harness gates* — applied to attribution instead of fidelity.

**When:** Any stem, any time (even weeks post-upload). Promotion = create fragment + `sample_attribution` row; analysis reuses the same feature worker as human fragments.

**Trade-offs:** (+) Honest, attribution-clean sampling falls out of the existing provenance/lineage design — "a natural addition, not a new subsystem." (+) Symmetric gating story (fidelity gate for AI, attribution gate for samples). (−) Adds one enforced precondition to the placement transition.

```rust
// state_machine.rs — additive invariant (illustrative)
match (fragment.provenance, transition) {
    (Provenance::Sampled, Transition::Place) if !attribution.is_complete() =>
        return Err(GateError::IncompleteAttribution),   // hard block, no bypass
    (Provenance::AiGenerated, Transition::Place) if !eval.passed =>
        return Err(GateError::EvalNotPassed),           // existing PRD gate
    // human + complete-attribution sampled proceed identically
    _ => apply(transition),
}
```

---

## Data Flow

### Flow A: tutorial → Skill (offline, build-time)

```
discover (yt-dlp: genre×stage queries + artist/producer anchors)
   ↓  video_ids
fetch transcripts (youtube-transcript-api, backoff)        → registry.sqlite (sources)
   ↓  transcript text + timestamps
claim-mine (LLM: atomic claims, each w/ video_id+timestamp) → registry.sqlite (claims)
   ↓  claims
cross-ref / scrutinize (group by topic → consensus/conflict + citations)
   ↓  layered findings
   ├─ sparse genre? → ground_sparse: decompose to parent techniques
   │                   + analyze artists' released tracks via workers/lib (CLAP/features)
   ↓
emit_skill → skills/production/**/SKILL.md (default + consensus + conflict + provenance) + _refs/
   ↓
git commit  →  loaded at runtime by arranger/mixer via Skill progressive disclosure
```

### Flow B: upload → reference-context AND/OR sample (runtime)

```
user uploads finished track (frontend → axum)
   ↓  raw audio → S3 (by ID)  ;  reference_tracks row created
   ↓  NATS job: stem-library separation (Demucs)
   ├─ stems retained → S3 + stems index rows   (browsable indefinitely)
   └─ NATS job: reference-context extract (CLAP embed + LLM vibe + sonic targets)
         ↓  reference_context row
         ↓  (user attaches to a project)  → conditioning input to arranger/mixer/generator/eval-gate

  ── later, any time ──
   user promotes a stem → `nameless sample promote <stem_id> --project … --artist … --range …`
   ↓  fragment row (provenance=sampled) + sample_attribution row
   ↓  feature worker analyzes (human path)  →  analyzed
   ↓  ATTRIBUTION GATE: place blocked unless attribution complete
   ↓  placed → mixed → rendered
   ── at export ──
   credits exporter enumerates sampled fragments in arrangement → credits sheet
```

### What never crosses which boundary (the token/cleanliness invariants)

1. **Audio + feature arrays never enter agent context** (PRD) — unchanged; reference embeddings/stems are addressed by ID too.
2. **Knowledge registry (claims/sources) never enters the runtime read path** — agents read emitted Skills, not the SQLite.
3. **Reference context exposes no melody/chords/structure** — non-cloning enforced by schema, not policy.
4. **Sampled fragments never skip attribution** — enforced by the state machine, not by the agent.

---

## Build Order (dependency-correct)

The knowledge layer is the **M0 foundation** alongside the fragment graph: agents cannot produce good work without grounded craft. Crucially, the knowledge pipeline is **largely parallelizable** — it depends on the runtime only for the sparse-genre audio-grounding leg (which needs `workers/lib`).

### Foundational (everything else depends on these)

| # | Component | Depends on | Track |
|---|-----------|-----------|-------|
| F1 | Core schema + Rust state machine + control plane + `nameless` CLI skeleton (PRD M0) | — | Control plane |
| F2 | Object storage + capture + feature extraction worker + embeddings/pgvector (PRD M0) | F1 | Worker plane |

### M0 — buildable in parallel once F1/F2 exist (or alongside)

| # | Component | Depends on | Parallel with |
|---|-----------|-----------|---------------|
| K1 | Knowledge pipeline core: discover → fetch → claim-mine → scrutinize → emit | youtube tooling only | **Fully parallel with F1/F2** (independent track) |
| K2 | Sparse-genre grounding leg (decompose + audio analysis) | K1 + `workers/lib` (F2) | After F2's DSP lib exists |
| K3 | First authored Skills committed to `skills/production/` | K1 (+K2 for alt-piano) | — |
| S1 | provenance enum delta (`sampled`) + schema: `reference_tracks`, `reference_context`, `stems`, `sample_attribution` | F1 | Parallel with worker work |
| S2 | Reference upload + stem-library separation (Demucs) + reference-context extract jobs | F2 (Demucs+CLAP) + S1 | Parallel with K-track |
| S3 | Sampling: promote stem → `sampled` fragment + attribution gate in state machine | S1 + S2 | — |
| U1 | Frontend: reference upload, stem browser, credits view | F1 API + S2/S3 | Parallel with backend |

### M1 — consumes M0 foundations

| # | Component | Depends on |
|---|-----------|-----------|
| M1a | Skill that drives arranger/mixer behavior | **K3 (authored Skills)** — this is *why* the pipeline is foundational |
| M1b | Melody-conditioned generation + reference-context conditioning | F2, S2 (reference_context), arranger |
| M1c | Eval gate (fidelity) + optional reference-CLAP advisory score | M1b |
| M1d | Mix chain + master + export + **credits-sheet export** | M1c + S3 |

### Parallelization summary

- **Track A — Control plane:** F1 → S1 → S3 (sequential; the schema/state-machine spine).
- **Track B — Worker plane:** F2 → S2 → (Demucs/CLAP feed M1b). Independent DSP code; only storage wiring waits on F1.
- **Track C — Knowledge pipeline:** K1 → K3, with K2 joining after F2's DSP lib. **Start day one, in parallel with everything** — its only hard external dep is YouTube tooling.
- **Track D — Frontend:** U1 after F1's API surface.
- **Critical path to a *good* M1:** F1 → F2 → (K1→K3 craft) AND (S1→S3 sampling) → M1a..d. The knowledge pipeline and the sampling/reference work proceed concurrently; the long pole is whichever of "authored craft" vs "generation+gate" you sequence last.

---

## Data Model Deltas (concrete)

```sql
-- 1. Extend provenance enum (PRD: human_recorded | ai_generated | derived)
ALTER TYPE provenance ADD VALUE 'sampled';

-- 2. Reference tracks (uploaded finished songs — NOT fragments)
CREATE TABLE reference_tracks (
  id            uuid PRIMARY KEY,
  audio_uri     text NOT NULL,          -- S3 by ID, immutable
  title         text, artist text,
  duration_ms   int, sample_rate int,
  uploaded_at   timestamptz DEFAULT now()
);

-- 3. Extracted reference CONTEXT — vibe + measurable NON-melodic targets only.
--    Deliberately NO melody/chroma/structure column → non-cloning is structural.
CREATE TABLE reference_context (
  reference_track_id uuid PRIMARY KEY REFERENCES reference_tracks(id),
  clap_embedding     vector,            -- joint audio-text space (advisory conditioning)
  vibe_text          text,              -- LLM: mood, space, era, texture, energy
  genre              text,
  tempo_bpm_min      real, tempo_bpm_max real,
  lufs               real,
  tonal_balance      jsonb,             -- coarse band energy, not notes
  stereo_width       real
);

-- 4. Attach reference context to a project as conditioning (many-to-many, roled)
CREATE TABLE project_reference_context (
  project_id uuid, reference_track_id uuid, role text,  -- e.g. 'vibe' | 'sonic-target'
  PRIMARY KEY (project_id, reference_track_id)
);

-- 5. Persistent stem library — Demucs stems of uploaded tracks, retained forever
CREATE TABLE stems (
  id                 uuid PRIMARY KEY,
  reference_track_id uuid REFERENCES reference_tracks(id),
  stem_type          text,             -- vocals | drums | bass | other (Demucs)
  audio_uri          text NOT NULL,     -- S3 by ID
  duration_ms        int,
  created_at         timestamptz DEFAULT now()
);

-- 6. Sample attribution — present iff a fragment has provenance='sampled'.
--    Completeness of these fields is enforced as a state-machine invariant.
CREATE TABLE sample_attribution (
  fragment_id        uuid PRIMARY KEY REFERENCES fragments(id),
  reference_track_id uuid REFERENCES reference_tracks(id),
  stem_id            uuid REFERENCES stems(id),
  source_title       text NOT NULL,
  source_artist      text NOT NULL,
  stem_type          text NOT NULL,
  start_ms           int  NOT NULL,
  end_ms             int  NOT NULL
);
-- fragments.audio_uri for a sampled fragment points at the (possibly trimmed) stem slice.
```

**Knowledge layer storage (NOT in runtime Postgres):** the authored Skills live as files in `skills/` (git). Build-time provenance lives in pipeline-local `registry.sqlite`:

```
sources(video_id, url, title, channel, query_origin, fetched_at)
claims (id, video_id, timestamp_s, topic, claim_text, stance)
findings(topic, default_text, consensus_json, conflict_json, citations_json)
```

This keeps the **production-knowledge layer entirely off the fragment graph** — the runtime read path is files only, exactly as PROJECT.md's "no RAG/pgvector knowledge base" decision requires.

---

## Anti-Patterns

### Anti-Pattern 1: Making the knowledge pipeline a runtime worker / NATS consumer
**What people do:** Put `knowledge-pipeline/` under `workers/` and trigger distillation via job envelopes.
**Why it's wrong:** It is build-time authoring, not per-request work; wiring it into NATS invites it into runtime context and couples Skill quality to live infra/model churn.
**Do this instead:** Keep it an offline CLI that emits files and commits them. It may *import* `workers/lib` for audio grounding, but it never runs as a consumer.

### Anti-Pattern 2: Storing tutorial knowledge in pgvector and retrieving it at runtime (RAG)
**What people do:** Embed every claim, retrieve top-k into the agent's context per turn.
**Why it's wrong:** Bloats context, reasons worse, contradicts the locked token strategy; PROJECT.md explicitly rejects it.
**Do this instead:** Distill into opinionated authored Skills; the agent loads ~a description until a Skill triggers, then the focused body, then `_refs/` on demand.

### Anti-Pattern 3: Modeling a reference track as a placeable fragment
**What people do:** Ingest the upload into `fragments` and let the arranger reuse its melody/structure.
**Why it's wrong:** Opens the door to cloning — the explicit out-of-scope line.
**Do this instead:** Keep reference tracks a separate entity whose only runtime surface is `reference_context` (vibe + non-melodic targets). No melody/chroma/structure field exists to leak.

### Anti-Pattern 4: Running sampled fragments through the eval gate
**What people do:** Reuse the AI fidelity gate on samples.
**Why it's wrong:** The gate scores generated-vs-source fidelity; a sample *is* source — there's nothing to compare. It would reject valid material.
**Do this instead:** Sampled fragments travel the human lifecycle (no eval gate) but must clear the **attribution-completeness** invariant before placement/render.

### Anti-Pattern 5: Generating attribution lazily at export
**What people do:** Let samples be placed with blank attribution, hoping to fill it in before export.
**Why it's wrong:** Loses provenance; the credits sheet becomes unreliable.
**Do this instead:** Enforce attribution at the `analyzed → placed` transition; the credits exporter then just reads complete rows.

---

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Knowledge pipeline ↔ runtime | **None at runtime** — only emits files to `skills/` | Hard wall; preserves two-layer separation |
| Knowledge pipeline ↔ `workers/lib` | Python module import (offline, synchronous) | Only the sparse-genre grounding leg |
| Agent ↔ Skills tree | Skill mechanism (frontmatter→body→`_refs/`) | Progressive disclosure; thin runtime context |
| Control plane ↔ new worker jobs | NATS typed envelopes (reference-context, stem-separation) | Additive job types; same seam |
| State machine ↔ attribution | In-process invariant in `attribution.rs`/`gate.rs` | No-bypass, mirrors eval gate |
| Generator/eval-gate ↔ reference_context | Optional conditioning bundle in job envelope | Sonic targets only; advisory CLAP-to-reference score |

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| YouTube (discovery) | `yt-dlp` metadata extraction (genre×stage + artist anchors) | No download of media; IDs/titles only |
| YouTube (transcripts) | `youtube-transcript-api` | Free, no key; rate-limit ~100–500/hr → backoff + incremental registry |
| LLM (claim-mine/scrutinize) | Build-time API calls | Off the runtime token budget; metered as build spend |
| S3/R2 | Existing; now also uploaded tracks + retained stems | By-ID, immutable, unchanged pattern |

---

## Confidence & Gaps

- **HIGH:** the integration shape — offline pipeline → on-disk Skills; reference-as-context (not fragment); `sampled` on the human path + attribution gate; schema deltas; build order. All derive directly from the locked PRD's own grammar (provenance/lineage, eval-gate-as-invariant, Skill+CLI, by-ID storage).
- **MEDIUM:** claim-mining/scrutiny prompt design and how cleanly consensus/conflict separates in practice; transcript coverage for the newest alt-piano artists (mitigated by the audio-grounding leg).
- **Open for roadmap:** exact thresholds for the optional reference-CLAP advisory score; whether the knowledge registry ever needs a thin read-only `nameless skills list` surface (default: no — filesystem suffices); trimming a stem slice vs referencing the whole stem with a time-range (recommend store the slice as the fragment's `audio_uri`, keep the full stem in the library).

## Sources

- [Skill authoring best practices — Claude Docs](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices) — SKILL.md frontmatter + body + bundled refs; <500-line body; progressive disclosure
- [Agent Skills overview — Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — metadata loaded at startup, body/assets on demand
- [youtube-transcript-api — PyPI](https://pypi.org/project/youtube-transcript-api/) — keyless transcript fetch/list
- [yt-dlp-transcripts — PyPI](https://pypi.org/project/yt-dlp-transcripts/) — channel/playlist batch processing, rate-limit guidance
- `nameless-prd.md` §4–7, §12 — locked architecture, provenance/lineage, lifecycle, capability layer
- `.planning/PROJECT.md` — two-distinct-knowledge-layers note, non-cloning + attribution decisions, no-RAG decision

---
*Architecture research for: audio-native AI music composition — new-capability integration*
*Researched: 2026-06-26*
