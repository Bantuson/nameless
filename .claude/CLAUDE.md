<!-- GSD:project-start source:PROJECT.md -->

## Project

**Nameless**

Nameless is a local-first, audio-native music composition system for a solo producer. You capture musical fragments straight into a project — a hum, a hook, a beat, a rhythm — and annotate each with intent ("chorus hook, sits over the second drop"). The system understands the audio natively (pitch, key, tempo, timbre), proposes an arrangement, and generates the missing parts (bass, drums, pads) conditioned on your actual recordings so they lock to your key and tempo. Every generated part is checked against your source by a hard eval gate before it is allowed in. You mix through one chain, master to a streaming loudness target, and export. It exists to translate the music you hear in your head into finished, audible work — for people who hear melodies but cannot name them.

This project builds the full Nameless system described in `nameless-prd.md`, with **three capabilities added during initialization**, the first of which is foundational:

1. **A tutorial-derived production-knowledge layer (M0 foundation).** Scripts ingest transcripts from 100+ YouTube production tutorials across the whole stack and target genres, then cross-reference and scrutinize them into a "logical production stack of skill" emitted as authored **Claude Skills** that teach the arranger/mixer agents real craft. This is the missing answer to "where does the SKILL.md knowledge come from" — and it is as foundational as the PRD's fragment-memory graph.
2. **A reference-track context layer.** Upload a finished song you love; the system extracts its vibe/atmosphere and measurable sonic targets as conditioning context for generation and mixing — **never to recreate or clone it**, only to better translate your intent.
3. **A sampling + persistent stem library.** Every uploaded track is stem-separated and retained indefinitely; any stem can be promoted to an attributed `sampled` fragment at any time, with provenance and an exported credits sheet — attribution-clean sampling rather than copy-and-claim-original.

**Core Value:** Translate the music in your head into genuinely *good* output. Two grounding forces make that real: **production knowledge** mined from how the craft is actually taught, and **your taste** expressed through reference tracks and samples. Quality in, quality out. The north-star sound is **Sonder / Brent Faiyaz vocal layering and atmosphere**, fused across **R&B × amapiano × deep house × alternative piano**.

### Constraints

- **Tech stack**: Rust + Python + TypeScript/React per PRD — let each language do what its ecosystem wins; clean boundary between them.
- **Token budget**: metered agent paths draw on a capped credit pool with overflow disabled. Skill + CLI + externalized queryable graph keep context near-empty by construction; audio/feature dumps run file-to-file and never enter context.
- **Compute**: M0 runs comfortably on CPU; generation and stem separation (M1) want a GPU — budget a rented/hosted worker.
- **Licensing**: research/non-commercial generator licenses (e.g. MusicGen) are fine for personal/portfolio; commercial output would require swapping to a clear-licensed generator.
- **Solo build**: scope must stay buildable and maintainable by one person, local-first.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version (2026) | Purpose | Why Recommended | Tag |
|------------|---------|---------|-----------------|-----|
| **Rust + axum** | axum **0.8.x** (0.8.4), tokio 1.x | Control-plane HTTP/WS API, fragment state machine, gate enforcement, `nameless` CLI | axum 0.8 is current and stable; the hard part here is schema integrity + DAG correctness + exhaustive state transitions, exactly Rust's strength. Confirmed actively maintained. | VALIDATED — PRD |
| **sqlx** | **0.8.x** (0.8.6) | Postgres access from Rust | Pick sqlx **over SeaORM** for this project: compile-time-checked SQL (`query!`/`query_as!`) is the artifact that matches the PRD's "schema integrity reads as senior" thesis, and SeaORM is itself built on top of sqlx. Use SeaORM only if you find yourself hand-writing dozens of near-identical CRUD queries. | VALIDATED — PRD (resolves "sqlx or SeaORM" → **sqlx**) |
| **Python 3.11/3.12** worker plane | — | Audio ML + DSP | Non-negotiable per PRD; the ecosystem lives here. Target 3.11/3.12 (broad wheel availability; some ML deps still lag on 3.13). | VALIDATED — PRD |
| **librosa** | **0.11.0** (Mar 2025) | Chroma, onset, beat/tempo, key, spectral/tonal features | Current, actively maintained, supports Python 3.8–3.13. The default DSP workhorse for feature extraction and reference-track analysis. | VALIDATED — PRD |
| **Postgres + pgvector** | Postgres 16/17, pgvector **0.8.x** | Fragment graph, notes, features, embeddings, evals, **+ provenance/sampling tables** | pgvector 0.8 added meaningful query-planner/iterative-scan improvements; one store for graph + vectors keeps the solo footprint minimal. Neon is a fine host if you want branch-per-eval isolation (PRD §5). | VALIDATED — PRD |
| **S3-compatible object storage (Cloudflare R2)** | — | Immutable raw + rendered audio + retained stems, by ID only | R2 has no egress fees — material when you retain every uploaded track's stems indefinitely (sampling library). Address by ID; never enters agent context. | VALIDATED — PRD |
| **TypeScript + React** | React 18/19, Vite | M0–M1 capture/notes/graph view; M2 adds Tone.js + Web Audio | Right place for the interactive surface; unchanged. | VALIDATED — PRD |

### Supporting Libraries — Audio ML / DSP (Python worker plane)

| Library | Version (2026) | Purpose | When to Use / Status | Tag |
|---------|---------|---------|-------------|-----|
| **torchaudio** | 2.x | I/O, resampling, some transforms | ⚠️ **Maintenance/phase-down** — Meta scaled back active development (2024+); some features deprecated. Still works, but **prefer librosa + soundfile for new feature code** and treat torchaudio as I/O glue, not a strategic dependency. | VALIDATED — PRD (with caveat) |
| **torchcrepe** | ~0.0.23 | f0 / pitch-contour tracking | Stable, thin PyTorch CREPE wrapper. Good default. Note newer monophonic pitch trackers exist (e.g. **SwiftF0**, 2025) if CREPE proves slow on CPU — keep behind the worker interface. | VALIDATED — PRD |
| **basic-pitch** (Spotify) | **0.4.x** | Audio→MIDI for the symbolic/precision fallback path | Apache-2.0, permissive, actively maintained, ONNX/TF/CoreML runtimes. Fits the "surgical control" render path (PRD §9). | VALIDATED — PRD |
| **Demucs** (`adefossez/demucs`) | **v4 / 4.0.1**, `htdemucs` | Stem separation (sampling layer + reference-track stems) | ⚠️ **Maintenance-only** — creator left Meta, "no new features." Still the pragmatic default and high quality. Use **`htdemucs_ft`** for best quality, or **`htdemucs_6s`** to get **piano + guitar** stems (directly relevant — alt-piano/amapiano piano isolation). MIT-licensed code + models. | VALIDATED — PRD (with status flag) |
| **audio-separator** (`nomadkaraoke/python-audio-separator`) | **0.4x** | Actively-maintained separation wrapper; access to **BS-RoFormer** (SOTA), MDX, MDXC, Demucs | **[NEW]** Recommended as the swap/upgrade path the PRD's "keep generator/separator behind the worker interface" risk note anticipates. BS-RoFormer is current MUSDB18-HQ SOTA (esp. bass). Auto-downloads checkpoints. Use when Demucs quality is insufficient on a stem; verify per-checkpoint licenses before relying on output. | NEW — open area (Demucs alternative) |
| **pyloudnorm** | **0.1.x** (0.1.1) | LUFS / integrated loudness (ITU-R BS.1770-4) | The standard Python LUFS meter; validates the PRD's loudness-target + loudness-delta eval metric and the reference-track LUFS target. Stable, low-churn. | VALIDATED — PRD |
| **LAION-CLAP** (`laion_clap`) | **1.1.7** | Joint audio-text embedding (fragment retrieval, vibe embedding, eval CLAP-alignment) | Current PyPI release; self-described "work in progress" but the de-facto open joint space. Use `larger_clap_music` / `clap-htsat` checkpoints for music. **Pin the version and checkpoint** — API and weights have drifted historically. | VALIDATED — PRD |
| **pedalboard** (Spotify) | **0.9.x** | EQ, compression, reverb, limiting, VST3/AU/CLAP hosting | ⚠️ **GPL-3.0 licensed.** Fine for a personal/portfolio build; flag it if you ever distribute a binary (copyleft). Excellent for the M1 mix/master chain and the M3 plugin host. | VALIDATED — PRD (license flag) |
| **MusicGen-Stem** | research (ICASSP 2025, Meta) | Multi-stem (bass/drums/other) generation conditioned on chromagram | **[Confirm checkpoint availability]** — strong fit (stem-by-stem, melody/chroma conditioning) but a research release; weights distribution is less turnkey than base MusicGen. Code under AudioCraft (MIT); **weights CC-BY-NC 4.0 (non-commercial)** — fine for this scope. | VALIDATED — PRD (availability caveat) |
| **MuseControlLite** | **ICML 2025**, code + checkpoints public | Melody + dynamics + rhythm + audio (inpaint/outpaint) conditioning at low param count | Confirmed released with public code and checkpoints (`fundwotsai2001/MuseControlLite`). Built on a diffusion-transformer (Stable-Audio-Open-class) backbone — **inherits a Stability AI Community / non-commercial-style license** on the backbone weights; verify before any commercial use. Best when you want explicit attribute control (PRD §9). | VALIDATED — PRD |
| **essentia / essentia-tensorflow** | 2.1-beta | Genre + mood + BPM/key tagging for reference tracks | **[NEW]** Ships pretrained genre/mood classifiers (MusiCNN / EffNet-Discogs) that directly produce the reference-track **genre** target the PRD/PROJECT want, which librosa alone does not. Use alongside librosa for the reference-analysis worker. Permissive-ish (AGPL — flag for distribution). | NEW — reference analysis |
| **MuQ-MuLan** | research (2025) | Optional music-centric audio-text embedding | **[NEW, optional]** Reported to beat LAION-CLAP on music tagging/retrieval (zero-shot MagnaTagATune). Consider as a CLAP alternative for the vibe/tagging path **only if** CLAP retrieval quality disappoints; keep behind the embedding interface. | NEW — optional upgrade |

### Supporting Libraries — Knowledge-distillation pipeline (NEW — open area)

| Library / Tool | Version | Purpose | Why | Tag |
|---------|---------|---------|-----|-----|
| **yt-dlp** | latest, **pinned** | Primary transcript + audio acquisition (`--write-auto-subs`, `--write-subs`, `--sub-format vtt`) | Most robust, actively maintained (releases ~every 2 weeks), gets **both** captions and the audio stream for ASR fallback in one tool. **Pin the version + keep a smoke test** — YouTube changes break it periodically. Prefer VTT/SRT output (json3/ttml have known bugs). | NEW |
| **youtube-transcript-api** | 1.x | Convenience transcript fetch (manual + auto captions, language selection) | Cleaner Python API for captions specifically. Works fine **from a home/residential IP** (local-first fits), but is blocked from datacenter IPs without residential proxies. Use as the fast path; fall back to yt-dlp when it 403s. | NEW |
| **faster-whisper** (CTranslate2) | latest, `large-v3` / `large-v3-turbo` | ASR fallback when captions are missing or auto-caption quality is poor | 4× faster than openai/whisper, less memory, 8-bit quant on CPU/GPU; `large-v3-turbo` for speed. The honest fallback for niche producers/tutorials lacking clean captions. CUDA 12 + cuDNN 9 for GPU. | NEW |
| **Claude (Agent SDK / `claude -p`)** for extraction | — | Claim-mining + cross-document synthesis **as scripts** that emit SKILL.md | The distillation pipeline is a **build, not a library**. Pattern (below) is offline scripts → SKILL.md, keeping agent runtime context thin. | NEW |
| **pydantic** (+ JSON-mode/tool-use) | 2.x | Typed claim schema for extraction output | Forces structured `{claim, technique, stage, source_video_id, timestamp, confidence}` records; "reliable LLM output comes from structure, not clever prompts." | NEW |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Python env/dependency management for the worker plane | Fast, lockfile-based; far less pain than pip/conda for the heavy torch/audio stack. |
| **ffmpeg** | Audio decode/transcode (yt-dlp, librosa, Demucs all lean on it) | System dependency; pin and document. |
| **sqlxmq** or **apalis** (Rust) | Postgres-backed job queue (see queue decision below) | `sqlxmq` reuses the sqlx pool you already have; `apalis` supports Postgres + Redis backends. |
| **Understand-Anything code knowledge-graph** | Dev-time grounding over the Rust+Python repo | Per PRD §13 dev-time note — saves tokens while building (independent of runtime). |

## Open-Area Deep Dives

### 1. YouTube transcript ingestion at 100+ video scale (NEW)

- The **official YouTube Data API `captions.download` endpoint only returns captions for videos you own** — it is **not usable** for third-party tutorial channels. So the official path is a dead end for this use case.
- Both `youtube-transcript-api` and `yt-dlp` are **unofficial** and technically against YouTube ToS. At personal research scale (~100–300 videos, one-time/occasional ingestion, from a home IP) this is the de-facto standard and low-risk, but **state it as a known constraint**, not a sanctioned API.
- **Datacenter IP blocking is real and getting worse**: AWS/GCP/Azure IPs get `RequestBlocked` almost immediately. Because this project is **local-first**, run ingestion **from your local/home machine** — this sidesteps the single biggest failure mode. Do **not** plan to run ingestion from a cloud worker without budgeting for rotating **residential** proxies.

### 2. Knowledge-distillation pipeline → authored SKILL.md (NEW)

### 3. Reference-track analysis — vibe + measurable targets (VALIDATED + augmented)

- **Tempo / key / chroma / onset** → librosa (validated).
- **LUFS / integrated loudness** → pyloudnorm (BS.1770-4) (validated).
- **Tonal balance** → librosa multiband spectral analysis (compute RMS per band; compare to a genre reference curve).
- **Stereo width** → compute mid/side energy ratio + L/R correlation with `numpy`/`soundfile` (no dedicated lib needed).
- **Genre / mood** → **[NEW] add essentia-tensorflow** pretrained classifiers — librosa does not give you a genre label, and "genre" is an explicit reference target.
- **Vibe embedding + LLM vibe description** → CLAP embedding for retrieval/zero-shot tags, then an LLM turns features+tags into the mood/space/era/texture/energy prose. **Strictly non-melodic targets only** (never melody/chords/structure) — enforced at the schema level.

### 4. Attribution-tracked sampling on Demucs (VALIDATED + status flag)

- **Default separator:** Demucs `htdemucs_ft` (best quality) — but it is **maintenance-only**. For piano-forward material, **`htdemucs_6s`** isolates piano + guitar, directly useful for alt-piano sampling.
- **Upgrade/swap path:** `audio-separator` wrapping **BS-RoFormer** (current SOTA) when Demucs under-separates a stem — exactly the "keep the separator behind the worker interface" hedge the PRD's risk section calls for.
- **Provenance approach:** extend the existing `provenance` enum with `sampled`; store `{source_track_id, artist, stem_type, time_range_ms, separator_model+version, separated_at}`. Retain all stems in R2 by ID (no-egress host matters here). **Generate the credits sheet from these rows on export**, and additionally write attribution into exported audio file tags (ID3/Vorbis/BWF) so lineage survives outside the system.

### 5. The seam — NATS JetStream vs Redis Streams (VALIDATED — resolves PRD open decision #1)

- **NATS JetStream** — single binary, durable streams + durable consumers + at-least-once + replay, ~750k msg/s, sub-ms latency. The better default if you want one dedicated messaging system. Matches the PRD's stated lean.
- **Redis Streams** — fine and lighter **if you already run Redis** (e.g. for cache); consumer groups cover the work-queue case, but it is weaker for long-term retention/replay.

## Installation (worker plane sketch)

# Python worker plane (use uv)

# audio-separator (optional, for BS-RoFormer / active maintenance)

# system: ffmpeg required

# Rust control plane

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **sqlx** | SeaORM 1.1 | Many models/tables with heavy CRUD; want struct-based ORM ergonomics over raw SQL. (SeaORM is built on sqlx anyway.) |
| **Demucs htdemucs_ft** | BS-RoFormer via `audio-separator` | Need SOTA separation (esp. bass) and latency is not a concern; or you want an actively-maintained pipeline. |
| **LAION-CLAP** | MuQ-MuLan | Music-specific tagging/retrieval quality matters and CLAP under-performs on genre. |
| **Postgres-backed queue (sqlxmq)** | NATS JetStream / Redis Streams | Throughput, multi-worker fan-out, or true headless autonomy outgrows Postgres polling. |
| **youtube-transcript-api (home IP)** | Managed transcript API (Supadata/TranscriptAPI) | You must run ingestion from cloud infra at scale and don't want to manage residential proxies. (Costs money; unnecessary for local-first personal scale.) |
| **MusicGen-Stem** | MuseControlLite | You want explicit time-varying attribute control (melody+dynamics+rhythm) over raw stem generation. Run both behind the worker interface (PRD open decision #2). |
| **torchcrepe** | SwiftF0 | CREPE is too slow on CPU for the f0 path. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Official YouTube Data API `captions.download` for third-party videos** | Only returns captions for videos **you own** — useless for tutorial channels. | yt-dlp / youtube-transcript-api (home IP) + faster-whisper fallback. |
| **Running transcript ingestion from a cloud/datacenter IP (unproxied)** | Instant `RequestBlocked`/bot-detection from YouTube. | Run locally (local-first fits) or pay for rotating **residential** proxies. |
| **RAG / pgvector knowledge base for tutorial knowledge** | Bloats agent context, reasons worse, contradicts the token strategy. (Explicit PROJECT.md out-of-scope.) | Authored Claude Skills emitted by offline distillation scripts. |
| **Spleeter** | Outdated, weaker separation than htdemucs/BS-RoFormer; aging TF1 stack. | Demucs `htdemucs_ft` or BS-RoFormer. |
| **openai/whisper (reference impl) for batch ASR** | ~4× slower, more memory than faster-whisper. | faster-whisper (CTranslate2). |
| **Treating torchaudio as a strategic DSP dependency** | In maintenance/phase-down; features deprecating. | librosa + soundfile for features; torchaudio for I/O only. |
| **Adding NATS/Redis on day one** | Extra moving part you don't need at solo scale. | Postgres-backed queue until throughput demands otherwise. |
| **Assuming MusicGen output is commercially usable** | Weights are **CC-BY-NC 4.0 / non-commercial** (and MuseControlLite's backbone has a restrictive community license). | Fine for portfolio/personal; for commerce, swap to a clear-licensed/self-trained generator (PRD §15). |

## License Constraints (personal/portfolio scope — HIGH confidence on the flags)

| Component | License | Implication for this build |
|-----------|---------|----------------------------|
| MusicGen / MusicGen-Stem (AudioCraft) | Code MIT; **weights CC-BY-NC 4.0** | ✅ personal/portfolio fine; ❌ commercial output. |
| MuseControlLite | Code permissive; **backbone (Stable-Audio-Open-class) = Stability Community / non-commercial-ish** | ✅ personal fine; verify backbone terms before any commercial use. |
| Demucs (code + htdemucs models) | **MIT** | ✅ permissive, no problem. |
| BS-RoFormer / UVR checkpoints | Varies per checkpoint (often research/MIT) | Verify the specific `.ckpt` license before relying on its output. |
| **pedalboard** | **GPL-3.0** | ✅ personal/portfolio fine; ⚠️ copyleft if you ever distribute a binary. |
| basic-pitch | Apache-2.0 | ✅ permissive. |
| LAION-CLAP | Permissive code; check checkpoint training-data terms | ✅ fine for personal. |
| essentia | **AGPL-3.0** (TF models vary) | ✅ personal fine; ⚠️ AGPL is strong copyleft if ever served/distributed. |
| **Sampled reference audio** | Third-party copyright | Out-of-scope for clearance (PROJECT.md); attribution-tracked for personal use only. **Do not distribute** sample-containing output without clearance. |

## Stack Patterns by Variant

- Run YouTube ingestion from your home machine; Postgres-backed queue; non-commercial generators are fine. No proxies, no NATS, no commercial-license worries.
- Add residential proxies (or a managed transcript API) for ingestion from cloud IPs; graduate the queue to **NATS JetStream**; re-evaluate generator licenses before any public output. Treat all of this as real metered spend (PRD §15).
- Swap Demucs → BS-RoFormer (audio-separator); run MuseControlLite for attribute control; lean harder on the sparse-genre grounding path (parent-technique decomposition + real-track audio analysis). The eval gate turns weak generation into a visible reject (PRD §16) — that is the design, not a bug.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| axum 0.8.x | sqlx 0.8.x, tokio 1.x | Confirmed working pairing in 2026. |
| sqlx 0.8.x | SeaORM 1.1.x | SeaORM 1.1 builds on sqlx 0.8 — they coexist if you adopt SeaORM later. |
| faster-whisper (GPU) | CTranslate2 (CUDA 12 + cuDNN 9) | Latest CTranslate2 dropped CUDA 11; match your GPU/driver stack. |
| Demucs / librosa / torch | torch 2.x, ffmpeg | Pin torch + torchaudio together; heavy CUDA stack — isolate the env (uv/venv). |
| pgvector 0.8.x | Postgres 16/17 | Iterative-scan + planner improvements vs 0.7. |
| pedalboard (VST3/CLAP hosting) | OS-native plugin SDKs | M3 plugin host — verify per-OS hosting support then. |

## Sources

- youtube-transcript-api IP-blocking (cloud vs residential), 2026 — GitHub issues #511/#593, transcriptapi.com, HuggingFace forums — **MEDIUM** (community/blog, cross-checked)
- yt-dlp subtitle reliability + format bugs, 2026 — yt-dlp GitHub issues, skipthewatch, transcriptapi comparison — **MEDIUM**
- faster-whisper status + large-v3-turbo + CUDA 12/cuDNN 9 — SYSTRAN/faster-whisper GitHub + PyPI — **HIGH**
- Demucs maintenance-only status + model list (htdemucs_ft/_6s) — github.com/adefossez/demucs (official) — **HIGH**
- BS-RoFormer SOTA + audio-separator wrapper, active maintenance, v0.4x — aistemsplitter benchmark, nomadkaraoke/python-audio-separator GitHub+PyPI — **HIGH**
- MusicGen-Stem (ICASSP 2025, chroma conditioning, 3-stem) — arXiv 2501.01757, HAL — **HIGH** on design / **MEDIUM** on weight availability
- MuseControlLite (ICML 2025, public code+checkpoints, melody/dynamics/rhythm) — arXiv 2506.18729, fundwotsai2001/MuseControlLite GitHub — **HIGH**
- LAION-CLAP 1.1.7 + MuQ-MuLan comparison — LAION-AI/CLAP GitHub, PyPI, emergentmind — **HIGH** (version) / **MEDIUM** (MuQ-MuLan claim)
- librosa 0.11.0 (Mar 2025, py3.8–3.13) — pypi.org/project/librosa — **HIGH**
- axum 0.8 + sqlx 0.8 vs SeaORM 1.1 — Shuttle ORM guide 2025, sea-ql.org, dev.to tutorials — **HIGH**
- NATS JetStream vs Redis Streams (single-node, throughput, durability) — index.dev, dev.to, docs.nats.io — **HIGH**
- LLM claim-extraction / citation-enforced synthesis patterns — arXiv 2605.30966, 2602.21045; Alan/Databricks production pipeline blogs — **MEDIUM**
- License facts (MusicGen CC-BY-NC, pedalboard GPL-3.0, basic-pitch Apache-2.0, Demucs MIT) — respective project repos — **HIGH**
- torchaudio maintenance/phase-down — PyTorch ecosystem announcements (training knowledge, flag for re-verify) — **MEDIUM**

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

**Canonical: `.planning/ENGINEERING-PRINCIPLES.md` (read it before planning or writing code).**

- **Course/learning build, code-complete but NOT run here.** The dev machine (~4GB RAM, no Docker, no Rust/C++ toolchain) won't compile/run this. Deliver complete, real, end-to-end code for every phase (Rust, Python/ML, TS/React) anyway. Never gate progress on compiling/running/installing. "Verify" = review + completeness + traceability + **tests that exist** (written, not executed here); flag anything needing real hardware/credentials as env-gated with the exact command.
- **Testability is law (every phase, forever):** dependency injection / ports-and-adapters (every DB, ML model, network, queue, clock, RNG behind a trait/interface with a real adapter + a test fake); pure functions for core logic; separation of concerns; loose coupling.
- **Go deep on ML as a teaching subject** — ML/DSP phases ship a `LEARNING.md` explaining the technique, the math, why, trade-offs, and references.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
