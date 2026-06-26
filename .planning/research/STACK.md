# Stack Research

**Domain:** Audio-native, local-first, solo AI music composition system (Rust control plane + Python audio-ML worker plane + TS/React frontend), plus a tutorial-derived knowledge-distillation pipeline and a reference-track + attribution-tracked sampling layer.
**Researched:** 2026-06-26
**Confidence:** HIGH on the locked Rust/Python/storage stack and on YouTube ingestion reality; MEDIUM on the generator models (research-grade, fast-moving) and the distillation-pipeline pattern (no turnkey tool — it is a build).

> **How to read this file.** Every recommendation is tagged **[VALIDATED — PRD]** (the PRD already locked it; this confirms it is still the right 2026 call and flags any caveat) or **[NEW — open area]** (the PRD does not specify it; this is a fresh prescriptive recommendation). The PRD's locked stack survives validation almost intact. The few flags worth acting on: Demucs is now maintenance-only (a swap path exists), `torchaudio` has entered maintenance/phase-down, `pedalboard` is GPL-3.0, the queue choice can likely be deferred entirely to Postgres at solo scale, and the generator model weights carry non-commercial licenses (fine for this scope).

---

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

---

## Open-Area Deep Dives

### 1. YouTube transcript ingestion at 100+ video scale (NEW)

**Honest ToS / blocking reality (HIGH confidence):**
- The **official YouTube Data API `captions.download` endpoint only returns captions for videos you own** — it is **not usable** for third-party tutorial channels. So the official path is a dead end for this use case.
- Both `youtube-transcript-api` and `yt-dlp` are **unofficial** and technically against YouTube ToS. At personal research scale (~100–300 videos, one-time/occasional ingestion, from a home IP) this is the de-facto standard and low-risk, but **state it as a known constraint**, not a sanctioned API.
- **Datacenter IP blocking is real and getting worse**: AWS/GCP/Azure IPs get `RequestBlocked` almost immediately. Because this project is **local-first**, run ingestion **from your local/home machine** — this sidesteps the single biggest failure mode. Do **not** plan to run ingestion from a cloud worker without budgeting for rotating **residential** proxies.

**Recommended ingestion flow:**
1. **Discovery** → resolve video IDs (genre×stage queries + artist/producer-anchored search per PROJECT.md).
2. **Captions fast path** → `youtube-transcript-api` (prefer **manual** captions over auto-generated; auto-captions lack punctuation/casing and mis-hear genre jargon like "log drum", "amapiano", "Serato").
3. **Robust path / fallback** → `yt-dlp --write-subs --write-auto-subs --sub-format vtt` (pinned version, smoke-tested).
4. **ASR fallback** → when no captions or auto-caption quality is poor, `yt-dlp` pulls the audio and **faster-whisper (`large-v3`)** transcribes with real punctuation + timestamps. This is **needed**, not optional — many producer tutorials have only auto-captions or none.
5. **Quality gate** → keep `caption_source ∈ {manual, auto, asr}` on every transcript so the distillation step can weight manual/ASR over noisy auto-captions.

### 2. Knowledge-distillation pipeline → authored SKILL.md (NEW)

There is **no turnkey tool**; this is the project's signature build. Recommended pattern (MEDIUM confidence, grounded in current claim-mining/citation literature):

1. **Per-video claim extraction (map).** One LLM pass per transcript → typed claims via a `pydantic` schema: `{claim, technique, stage(beats|vocals|instruments|plugins|mixing|mastering|atmosphere), genre, source_video_id, timestamp_range, verbatim_quote, confidence}`. **Rule: every claim must carry a source video + timestamp, or it is dropped** (prevents hallucinated craft).
2. **Normalize + cluster (reduce).** Embed claims (CLAP-text or a text encoder), cluster by technique/stage so the same idea from many videos lands together. This is where **consensus vs conflict** becomes visible.
3. **Cross-document synthesis (per cluster).** A second LLM pass over each cluster emits the PRD/PROJECT's **layered output**: an **opinionated default** PLUS preserved **consensus/conflict evidence**, each line ending in exactly one citation (split multi-source claims into multiple cited lines — the "citation-enforced synthesis" pattern).
4. **Emit authored Skills.** Render clusters into a **logical "production stack of skill"** → `SKILL.md` (opinionated default, thin) + **reference docs** (the cited evidence, loaded only when needed). Keeps agent runtime context near-empty — the whole point.
5. **Sparse-genre grounding (alt-piano).** Where tutorials are thin: (a) decompose into parent techniques (amapiano groove/log-drum + jazzy piano + deep-house space) and (b) run the **actual released tracks through the audio/CLAP feature pipeline** to extract real sonic signatures, then synthesize a grounded skill — never fabricate.

Run all of this as **offline scripts** (Agent SDK / `claude -p`), not at agent runtime. Output is files on disk; only the thin SKILL.md description ever sits in context. This is deliberately **not** RAG/pgvector (PROJECT.md out-of-scope decision).

### 3. Reference-track analysis — vibe + measurable targets (VALIDATED + augmented)

The PRD's CLAP / librosa / pyloudnorm choices are **validated**. Concretely:
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

**Opinionated recommendation: at solo scale, you very likely need neither yet.** The jobs are durable, long-running, retry-prone (generation = minutes) — but you **already run Postgres**, and a Postgres-backed queue (`sqlxmq` for Rust, or `SELECT … FOR UPDATE SKIP LOCKED`) gives at-least-once delivery, durability, retries, and backpressure with **zero new infrastructure**. Eliminate a moving part for M0/M1.

If/when you outgrow that:
- **NATS JetStream** — single binary, durable streams + durable consumers + at-least-once + replay, ~750k msg/s, sub-ms latency. The better default if you want one dedicated messaging system. Matches the PRD's stated lean.
- **Redis Streams** — fine and lighter **if you already run Redis** (e.g. for cache); consumer groups cover the work-queue case, but it is weaker for long-term retention/replay.

**Decision: Postgres-backed queue (`sqlxmq`) for M0–M1 → NATS JetStream when throughput/autonomy demands it.** Keep the worker job interface abstract so the swap is a config change.

---

## Installation (worker plane sketch)

```bash
# Python worker plane (use uv)
uv add librosa soundfile pyloudnorm torchcrepe basic-pitch laion-clap demucs pedalboard
uv add faster-whisper yt-dlp youtube-transcript-api essentia-tensorflow
# audio-separator (optional, for BS-RoFormer / active maintenance)
uv add "audio-separator[gpu]"   # or [cpu]
# system: ffmpeg required

# Rust control plane
cargo add axum tokio --features tokio/full
cargo add sqlx --features "runtime-tokio,postgres,macros,uuid,chrono"
cargo add sqlxmq   # postgres-backed job queue (defer NATS/Redis)
```

> Generators (MusicGen-Stem / MuseControlLite) install from their research repos / Hugging Face checkpoints, not a clean PyPI line — budget integration time and **pin commits + checkpoints**.

---

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

**If staying strictly local-first / personal (default):**
- Run YouTube ingestion from your home machine; Postgres-backed queue; non-commercial generators are fine. No proxies, no NATS, no commercial-license worries.

**If you later go headless/hosted (Agent SDK or API path):**
- Add residential proxies (or a managed transcript API) for ingestion from cloud IPs; graduate the queue to **NATS JetStream**; re-evaluate generator licenses before any public output. Treat all of this as real metered spend (PRD §15).

**If separation/generation quality on niche genres (alt-piano/amapiano) is weak:**
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

---
*Stack research for: audio-native local-first AI music composition + tutorial knowledge distillation + attribution-tracked sampling*
*Researched: 2026-06-26*
