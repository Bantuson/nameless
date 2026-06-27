# `knowledge-pipeline/` — Nameless offline knowledge pipeline (ingestion stage)

The build-time authoring tool that grounds Nameless's craft (PRD M0 foundation, research
`ARCHITECTURE.md`). **Phase 3** delivers the *ingestion stage*: discover north-star production tutorials,
fetch their transcripts **locally** with throttling + snapshot-on-ingest, fall back to ASR when captions
are missing/poor, score each source's **extractability** (flagging visual-only / low-signal rather than
faking it into a skill), and register everything in a local **corpus** the later stages cite.

This is a **sibling of `workers/`, NOT a runtime plane.** It runs on your machine when you want to
(re)build the corpus, writes files + a local `registry.sqlite`, and then disappears from the runtime
picture. It shares **no tables and no read path** with the runtime Postgres fragment graph — the two
knowledge layers are deliberately separate.

- Requirements covered: **KNOW-01** (discovery grid + artist anchors), **KNOW-02** (local fetch +
  throttle + snapshot-on-ingest), **KNOW-03** (ASR fallback + extractability + visual-only flag),
  **KNOW-04** (≥100 north-star target; registry inspectable by genre/extractability).
- The ideas (captions, IP-blocking, extractability, snapshots, faster-whisper) are taught in depth in
  **[`LEARNING.md`](./LEARNING.md)**.

## Design: ports & adapters (why the tests need no network, ASR, or real time)

Every network/heavy/time dependency sits behind a `typing.Protocol` **port** with a REAL adapter (heavy
imports lazy) and a deterministic **FAKE**. The orchestration (`IngestPipeline`) is **pure** over those
ports — it contains no yt-dlp, no youtube-transcript-api, no faster-whisper, no sqlite, no wall clock.

| Port (`ports.py`) | Real adapter (env-gated) | Fake / stdlib adapter (tests) |
|---|---|---|
| `DiscoverySource` | `YtDlpDiscoverySource` (yt-dlp `ytsearch`) | `FixtureDiscoverySource` |
| `TranscriptFetcher` | `YoutubeTranscriptFetcher` (youtube-transcript-api → yt-dlp subs) | `FixtureTranscriptFetcher` |
| `Transcriber` (ASR) | `FasterWhisperTranscriber` (faster-whisper + yt-dlp audio) | `FixedTextTranscriber` |
| `CorpusStore` | `FilesystemCorpusStore` (snapshots + `registry.sqlite`) | `InMemoryCorpusStore` |
| `Clock` | `SystemClock` | `FakeClock` (virtual time) |
| `RateLimiter` | `IntervalRateLimiter` (interval + jitter) | `NoOpRateLimiter` |

The **pure core** is the testable heart: `query_grid`, `extractability_score`, `fallback_decision`,
`snapshot_record`, `dedup`, and a VTT parser — all deterministic, no I/O.

```
src/knowledge_pipeline/
  domain/      models.py (VideoRef, RawTranscript+segments, SnapshotRecord, ExtractabilityResult, CorpusEntry, …)
               genres.py  (the north-star genre x stage grid + artist anchors)
  pure/        query_grid.py · extractability.py · fallback.py · snapshot.py · dedup.py · captions.py · vocab.py
  ports.py     DiscoverySource · TranscriptFetcher · Transcriber · CorpusStore · Clock · RateLimiter
  adapters/    *_fake.py / corpus_mem.py / clock_fake.py / rate_limiter.py  (fakes + stdlib, eager) +
               discovery_ytdlp.py · fetch_youtube.py · transcribe_whisper.py · corpus_fs.py (real, heavy-imports lazy)
  registry_sql.py  DDL for registry.sqlite (sources · snapshots · extractability)
  pipeline.py  IngestPipeline — discover → dedup → fetch+fallback → snapshot → score → register
  cli.py       `corpus discover | ingest | list | show | stats`
  fixtures.py  loads fixtures/transcripts/*.json into the fake-adapter inputs
fixtures/transcripts/  6 fixture videos (incl. a visual-only and a sparse/low-signal one)
tests/        fakes-only pytest suite (pure core, fallback, snapshot, dedup, throttle-with-fake-clock,
              corpus store [mem + real sqlite], pipeline e2e, CLI)
```

## Build mode (course/learning project) — code-complete, NOT run live on the build box

This machine cannot install `faster-whisper` and must not hit YouTube (4GB / no-Docker; ingestion must
run from a home IP). The code is complete and real; the network/ASR paths are **env-gated** below.
**Nothing here was installed or fetched from YouTube on the build box.**

## Verification

### RAM-safe (runs anywhere with the light base — this is what was actually run)

```bash
cd knowledge-pipeline
uv sync --extra dev          # installs only pydantic + pytest
uv run pytest -q             # 77 tests: query grid, extractability gate (incl. visual-only),
                             # fallback ladder, snapshot hash/date, dedup, throttle-on-fake-clock,
                             # corpus store (in-memory AND real sqlite), pipeline e2e, CLI
```

(If not using uv: `pip install pydantic pytest` then `PYTHONPATH=src pytest -q`.)

You can also drive the whole pipeline **offline against the bundled fixtures** (no network) — the real
`FilesystemCorpusStore` (sqlite is stdlib) materializes a real `registry.sqlite`:

```bash
PYTHONPATH=src python -m knowledge_pipeline.cli ingest --fixtures --corpus-root ./demo-corpus
PYTHONPATH=src python -m knowledge_pipeline.cli list   --corpus-root ./demo-corpus --by-genre
PYTHONPATH=src python -m knowledge_pipeline.cli list   --corpus-root ./demo-corpus --by-extractability
PYTHONPATH=src python -m knowledge_pipeline.cli show altpiano_visual_only --corpus-root ./demo-corpus --segments 3
PYTHONPATH=src python -m knowledge_pipeline.cli stats  --corpus-root ./demo-corpus
```

### Env-gated (the LIVE ingest — NOT run here; run from your home machine)

```bash
# 1. Install the network + ASR extras (yt-dlp ships ~biweekly — PIN THE EXACT version first):
uv sync --extra ingest --extra asr

# 2. Inspect the discovery PLAN (grid + anchors → candidate videos) without ingesting:
uv run corpus discover --limit 5

# 3. Run the real ingest from your HOME IP, throttled (this fetches transcripts + ASR-transcribes):
uv run corpus ingest --limit 5 --corpus-root ./.nameless-knowledge/corpus --min-interval 2.5 --jitter 0.5
#    add --no-asr to skip the GPU-cost faster-whisper fallback (uncaptioned videos then record as reject)

# 4. Inspect the resulting corpus (these read the registry — no network, runnable anywhere):
uv run corpus list  --corpus-root ./.nameless-knowledge/corpus --by-genre
uv run corpus list  --corpus-root ./.nameless-knowledge/corpus --by-extractability --verdict keep
uv run corpus stats --corpus-root ./.nameless-knowledge/corpus           # is it ≥100 and north-star-concentrated?
uv run corpus show <VIDEO_ID> --corpus-root ./.nameless-knowledge/corpus --segments 5
```

KNOW-04's "≥100 videos" is reached by the live ingest: the default grid is `|genres| x |stages|` = 4 × 11
= 44 grid queries + artist anchors, each fanned to `--limit` results, deduped — comfortably >100 unique
candidate videos concentrated on the north-star fusion. The bundled fixture corpus (6 videos) is for
tests + the offline demo, not the count.

## ToS / local-first (read before the live ingest)

- `youtube-transcript-api` and `yt-dlp` are **unofficial** and technically against YouTube's ToS. At
  personal research scale (~100–300 videos, occasional, from a home IP) this is the de-facto standard and
  low-risk — but it is **a known constraint, not a sanctioned API**. The official YouTube Data API
  `captions.download` only returns captions for videos *you own*, so it is useless for tutorial channels.
- **Run ingestion from your local/home (residential) IP.** Datacenter/cloud IPs (AWS/GCP/Azure) get
  `RequestBlocked` almost instantly. This project is local-first, so this is free insurance — the GPU
  worker plane is for already-fetched audio, not for ingestion. Do **not** run `corpus ingest` from a
  cloud worker without budgeting rotating *residential* proxies (ToS-adjacent; not a clean portfolio story).
- The throttle (`--min-interval` / `--jitter`) is there to be polite and dodge 429s. Treat ingest as a
  slow background batch; it is **idempotent** (content-hashed snapshots) so a block mid-run loses no work.

## Cross-stage seam

The corpus this stage produces — immutable snapshot files (full timestamped segments) + `registry.sqlite`
— is the **input to Phase 4** (cited claim mining). The per-segment timestamps are the substrate Phase 4
cites as `video_id @ ts`; the snapshot hash + retrieval date keep those citations auditable even after a
channel takedown.

## Licensing note

This stage bundles no models. The env-gated tools carry their own terms (yt-dlp / youtube-transcript-api
unofficial; faster-whisper/CTranslate2 permissive). See the repo `CLAUDE.md` "License Constraints" and
`.planning/research/STACK.md` before any commercial use.
