# Phase 3: Tutorial Ingestion + Snapshot Corpus - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

Build the offline **knowledge-pipeline** ingestion stage: discover north-star production tutorials, fetch their transcripts locally with throttling + snapshot-on-ingest (hash + retrieval date), fall back to ASR when captions are missing/poor, score each source's extractability, and register everything in a corpus the later stages cite. This is a build-time tool (research ARCHITECTURE: sibling `knowledge-pipeline/` dir with a local `registry.sqlite`), NOT a runtime plane and NOT in Postgres.

In scope: discovery query-grid + artist-anchored search → candidate queue; transcript fetch (youtube-transcript-api → yt-dlp subs → ASR) with throttle + snapshot; extractability scoring + modality flags; the corpus registry + `corpus` CLI. Out of scope: claim extraction (Phase 4), synthesis/skills (Phase 5), sparse-genre grounding (Phase 6).
</domain>

<decisions>
## Implementation Decisions

### Pipeline architecture (ports-and-adapters — testability law)
- `DiscoverySource` port: queries → candidate `VideoRef`s. Real (yt-dlp `ytsearch`) + fake (fixture list).
- `TranscriptFetcher` port: `VideoRef` → `RawTranscript | None`. Real (youtube-transcript-api primary, yt-dlp subs secondary) + fake.
- `Transcriber` port (ASR): audio → transcript. Real (faster-whisper `large-v3`) + fake (fixed text). Only invoked on the fallback path.
- `CorpusStore` port: snapshot + registry persistence. Real (filesystem snapshots + `registry.sqlite`) + in-memory fake.
- `RateLimiter` port (throttle) + a clock port (injected `now`/`sleep`) so throttling is testable without real time.
- `IngestPipeline` = pure orchestration over injected ports: discover → dedup → fetch (with fallback decision) → snapshot → score → register.

### Pure, highly-testable core
- `query_grid(stages, genres, artists)` → the discovery query set (R&B/amapiano/alt-piano/deep-house × stages + Sonder/Brent Faiyaz, Ben Produces, Liyana Ricky, Lowbass Djy anchors).
- `extractability_score(transcript)` → 0..1 + flags: caption-source weight (manual > auto > asr), word density, production-vocabulary presence, actionable-sentence ratio, visual-only penalty ("as you can see here" with no spoken values). **Pure function — the heart of "don't fake visual-only into a skill."**
- `fallback_decision(captions)` → use captions | fetch+ASR | reject (pure).
- `snapshot_record(raw)` → content hash (sha256) + retrieval_date(injected) + source metadata; segments keep per-line timestamps so Phase 4 can cite `video_id @ ts`.

### KNOW-04 (≥100, north-star)
- Build the discovery query set + pipeline that WOULD yield 100+ north-star videos, plus a fixture corpus for tests. The live 100-video ingest is env-gated (network/ToS/rate-limits; course mode does not fetch live). The registry schema + `corpus list/show --by-genre/--by-extractability` make the count + concentration inspectable.

### ToS honesty
- youtube-transcript-api / yt-dlp are unofficial; run LOCALLY (home IP), throttled. Document in README (per project CLAUDE.md "What NOT to use": no datacenter-IP ingest).

### Claude's Discretion
- registry.sqlite schema, snapshot file layout, exact scoring weights, throttle defaults — idiomatic, typed (pydantic).
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.planning/research/STACK.md` (yt-dlp pinned, youtube-transcript-api 1.x, faster-whisper large-v3) + `PITFALLS.md` (caption noise, visual-only knowledge, cloud-IP blocking, snapshot-on-ingest) + `ARCHITECTURE.md` (sibling `knowledge-pipeline/` + registry.sqlite, off-Postgres by design).
- Phase 2 `workers/` established the Python ports + fakes + lazy-heavy-import + LEARNING pattern to mirror.

### Established Patterns
- typing.Protocol ports with real+fake adapters; lazy heavy imports (yt-dlp/faster-whisper imported only inside real adapters); pure-function core tested with fixtures; pydantic typed boundaries.

### Integration Points
- New `knowledge-pipeline/` package (sibling of `workers/`). Output corpus (snapshots + registry) is the INPUT to Phase 4 claim mining — segment timestamps must support per-claim citation.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning project — write complete real Python; DO NOT install yt-dlp/faster-whisper or hit YouTube. Verify by review + tests-that-RUN against fakes/fixtures (the pure scorer, fallback logic, query grid, snapshot record, dedup, throttle-with-injected-clock). Live ingest + ASR are env-gated with exact commands.
- **Ship `knowledge-pipeline/LEARNING.md`** teaching: how YouTube captions work (manual vs auto-ASR vs none), why datacenter IPs get blocked (and why local-first sidesteps it), what extractability scoring measures and why visual-only tutorials are dangerous to distill, snapshot-on-ingest for citation durability under takedowns, and faster-whisper/CTranslate2 basics. Educational, with the "quality in, quality out" thesis made concrete.
</specifics>

<deferred>
## Deferred Ideas
- Claim extraction / cross-reference (Phase 4); synthesis + citation gate + skills (Phase 5); sparse-genre grounding (Phase 6).
- Non-tutorial source mining (interviews/breakdowns) — v2 per REQUIREMENTS.
</deferred>
