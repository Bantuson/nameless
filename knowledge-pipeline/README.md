# `knowledge-pipeline/` — Nameless offline knowledge pipeline (ingestion + claim mining)

The build-time authoring tool that grounds Nameless's craft (PRD M0 foundation, research
`ARCHITECTURE.md`). It runs in two stages, both build-time, both writing into one local
`registry.sqlite`:

- **Phase 3 — ingestion stage** (`corpus` CLI): discover north-star production tutorials, fetch their
  transcripts **locally** with throttling + snapshot-on-ingest, fall back to ASR when captions are
  missing/poor, score each source's **extractability** (flagging visual-only / low-signal rather than
  faking it), and register everything in a local **corpus**.
- **Phase 4 — cited claim mining + cross-reference** (`claims` CLI): mine the snapshot corpus into a
  registry of **atomic, individually-cited claims** (Claude tool-use), verify each citation against the
  snapshot, and cross-reference them into **preserved consensus and conflict** — **extraction only, ZERO
  synthesis** (the opinionated default + SKILL.md are Phase 5). This is the EXTRACT half of the make-or-break
  two-pass design that defeats GIGO.

This is a **sibling of `workers/`, NOT a runtime plane.** It runs on your machine when you want to
(re)build the corpus/claims, writes files + a local `registry.sqlite`, and then disappears from the
runtime picture. It shares **no tables and no read path** with the runtime Postgres fragment graph — the
two knowledge layers are deliberately separate.

- Requirements covered: **KNOW-01..04** (Phase 3 — discovery, fetch+snapshot, ASR+extractability, ≥100
  north-star target); **KNOW-05** (atomic cited claims, typed production-stage × genre schema, no
  synthesis), **KNOW-06** (cross-reference consensus + conflict preserved as first-class data).
- The ideas (captions, IP-blocking, extractability, snapshots, faster-whisper **and** structured tool-use
  extraction, the extract-then-synthesize split, citation discipline, consensus/conflict, semantic-dedup
  trade-offs) are taught in depth in **[`LEARNING.md`](./LEARNING.md)**.

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
| `ClaimExtractor` (P4) | `AnthropicClaimExtractor` (Claude tool-use, `claude-opus-4-8`) | `FakeClaimExtractor` (scripted + rule-based) |
| `ClaimStore` (P4) | `SqliteClaimStore` (extends `registry.sqlite`) | `InMemoryClaimStore` |
| `SimilarityIndex` (P4) | `EmbeddingSimilarityIndex` (sentence-transformers) | `KeywordSimilarityIndex` (Jaccard) |

The **pure core** is the testable heart: `query_grid`, `extractability_score`, `fallback_decision`,
`snapshot_record`, `dedup`, a VTT parser (Phase 3) — **plus `verify_citation`, `cross_reference`,
`dedup_claims`, and the `emit_claims` extraction schema + normalization (Phase 4)** — all deterministic,
no I/O, no `anthropic`.

```
src/knowledge_pipeline/
  domain/      models.py (VideoRef, RawTranscript+segments, SnapshotRecord, ExtractabilityResult, CorpusEntry, …)
               claims.py  (Claim, ClaimCluster, ClaimStats — the typed KNOW-05/06 boundary)   [P4]
               keys.py    (pure normalize_text/normalize_key/topic_key/compute_claim_id)       [P4]
               genres.py  (the north-star genre x stage grid + artist anchors)
  pure/        P3: query_grid · extractability · fallback · snapshot · dedup · captions · vocab
               P4: citation.py (verify_citation) · cross_reference.py · claim_dedup.py · extraction_schema.py
  prompts.py   versioned claim-extraction system prompt (KNOW-05; "extract only, never invent numbers")  [P4]
  ports.py     P3: DiscoverySource · TranscriptFetcher · Transcriber · CorpusStore · Clock · RateLimiter
               P4: ClaimExtractor · SimilarityIndex · ClaimStore
  adapters/    fakes + stdlib (eager): *_fake.py · corpus_mem.py · clock_fake.py · rate_limiter.py ·
               claim_extractor_fake.py · claim_store_mem.py · claim_store_sqlite.py · similarity_keyword.py
               real, heavy-imports LAZY: discovery_ytdlp · fetch_youtube · transcribe_whisper · corpus_fs ·
               claim_extractor_anthropic (anthropic) · similarity_embeddings (sentence-transformers)
  registry_sql.py  DDL for registry.sqlite (sources · snapshots · extractability)
  claims_sql.py    additive DDL extending registry.sqlite (claims · clusters · cluster_members)   [P4]
  pipeline.py        IngestPipeline  — discover → dedup → fetch+fallback → snapshot → score → register
  mining_pipeline.py MiningPipeline  — extract → verify citation → dedup → cross-reference → persist   [P4]
  cli.py           `corpus discover | ingest | list | show | stats`
  claims_cli.py    `claims mine | list | show | stats`                                            [P4]
  fixtures.py · claim_fixtures.py   load fixtures/{transcripts,claims}/*.json into the fake-adapter inputs
fixtures/transcripts/  6 fixture videos (incl. visual-only + sparse/low-signal)
fixtures/claims/       5 fixtures: a 3-source consensus set + the amapiano FLEX-vs-layered conflict
tests/        fakes-only pytest suite — P3 (ingestion) + P4 (claim schema, citation, cross-reference,
              dedup, extraction schema, claim store [mem + real sqlite], mining e2e, claims CLI,
              no-synthesis boundary). 134 tests, run on the base env.
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
uv run pytest -q             # 134 tests (77 Phase 3 + 57 Phase 4):
                             # P3 — query grid, extractability gate, fallback ladder, snapshot hash/date,
                             #      dedup, throttle-on-fake-clock, corpus store (mem + real sqlite), e2e, CLI
                             # P4 — claim schema + keys, citation verify (positive/drift/not-found),
                             #      cross-reference consensus AND conflict-preservation, claim dedup,
                             #      extraction schema + rule-based fake, claim store (mem + real sqlite),
                             #      mining e2e, claims CLI, the no-synthesis boundary invariant
```

(If not using uv: `pip install pydantic pytest` then `PYTHONPATH=src pytest -q`.)

You can also drive **both stages offline against the bundled fixtures** (no network, no API) — the real
sqlite stores materialize a real `registry.sqlite`:

```bash
# Phase 3 — ingestion
PYTHONPATH=src python -m knowledge_pipeline.cli ingest --fixtures --corpus-root ./demo-corpus
PYTHONPATH=src python -m knowledge_pipeline.cli list   --corpus-root ./demo-corpus --by-genre
PYTHONPATH=src python -m knowledge_pipeline.cli show altpiano_visual_only --corpus-root ./demo-corpus --segments 3

# Phase 4 — cited claim mining (FakeClaimExtractor over the claim fixtures + real SqliteClaimStore)
PYTHONPATH=src python -m knowledge_pipeline.claims_cli mine  --fixtures --corpus-root ./demo-claims
PYTHONPATH=src python -m knowledge_pipeline.claims_cli list  --corpus-root ./demo-claims --conflicts   # both sides preserved
PYTHONPATH=src python -m knowledge_pipeline.claims_cli list  --corpus-root ./demo-claims --by-genre
PYTHONPATH=src python -m knowledge_pipeline.claims_cli show  <CLAIM_ID> --corpus-root ./demo-claims     # trace to source quote + ts + video
PYTHONPATH=src python -m knowledge_pipeline.claims_cli stats --corpus-root ./demo-claims
```

The fixtures carry a real **consensus set** (the sub-bass high-pass corroborated across deep-house, R&B
and amapiano = 3 distinct sources) and the **amapiano log-drum FLEX-vs-layered conflict** (both stances
preserved, never collapsed) — so the offline run demonstrates KNOW-06 directly.

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

### Env-gated (LIVE claim mining — Phase 4 — NOT run here)

Live mining calls Claude (`claude-opus-4-8`) with forced `emit_claims` tool-use, once per `keep`/
`low_signal` corpus video. **This is metered spend** and is never run on the build box.

```bash
# 1. Install the extractor extra (PIN the exact anthropic version first):
uv sync --extra extract

# 2. Set your key, then mine the snapshot corpus into cited claims (idempotent — re-mining upserts):
export ANTHROPIC_API_KEY=sk-ant-...
uv run claims mine --corpus-root ./.nameless-knowledge/corpus                 # all keep/low_signal videos
uv run claims mine --corpus-root ./.nameless-knowledge/corpus --video <VIDEO_ID>   # a single video
uv run claims mine --corpus-root ./.nameless-knowledge/corpus --require-citation   # drop claims whose citation fails

# 3. Inspect (these read the registry — no API, runnable anywhere):
uv run claims list  --corpus-root ./.nameless-knowledge/corpus --by-stage
uv run claims list  --corpus-root ./.nameless-knowledge/corpus --conflicts       # contested topics, both sides
uv run claims show  <CLAIM_ID> --corpus-root ./.nameless-knowledge/corpus        # trace to source quote + ts
uv run claims stats --corpus-root ./.nameless-knowledge/corpus
```

**Token-cost note (estimate, not a benchmark).** `claude-opus-4-8` is ~**$5.00 / 1M input** and
~**$25.00 / 1M output** tokens. One tutorial transcript is typically **<2k input tokens**, and a claims
array is small output, so a single extraction is well under **~$0.05** — call it a **few cents per video**.
The budget risk is therefore *volume × re-runs*, which the content-addressed, idempotent upsert controls
(re-mining an unchanged corpus does not re-extract identical claims into duplicates, but it **does** re-call
the API per targeted video — scope `--video` or re-mine deliberately). Optional `--extra embed`
(sentence-transformers) for semantic dedup is local compute, not metered.

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

- **Phase 3 → Phase 4.** The corpus (immutable snapshot files + `registry.sqlite`) is the input to claim
  mining. The per-segment timestamps are the substrate Phase 4 cites as `video_id @ ts`; the snapshot hash +
  retrieval date keep those citations auditable even after a channel takedown.
- **Phase 4 → Phase 5.** The `claims` + `clusters` tables (atomic cited claims, grouped into preserved
  consensus/conflict) are the input to **synthesis + the hard citation gate**. Phase 5 may decide an
  opinionated default and author `SKILL.md`, but **only over this extracted claim set** — it can cite
  nothing Phase 4 didn't extract, and `verify_citation` (the pure function Phase 4 already runs) becomes its
  non-negotiable reject gate. The extract-then-synthesize boundary is what makes the eventual skills
  trustworthy.

## Licensing note

This stage bundles no models. The env-gated tools carry their own terms (yt-dlp / youtube-transcript-api
unofficial; faster-whisper/CTranslate2 permissive). See the repo `CLAUDE.md` "License Constraints" and
`.planning/research/STACK.md` before any commercial use.
