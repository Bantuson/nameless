# Phase 3 — Tutorial Ingestion + Snapshot Corpus — SUMMARY

**Status:** Code-complete. RAM-safe tests RUN here (77 passed). Live ingest env-gated (not run — network/ToS/ASR).
**Delivered:** a new `knowledge-pipeline/` Python package (sibling of `workers/`), the offline ingestion
stage of the production-knowledge pipeline. Mirrors the Phase-2 testability pattern exactly: `typing.Protocol`
ports + real (heavy-imports-lazy) and fake adapters + a pure-function core + pure orchestration + pytest +
LEARNING.md.

Build mode per `.planning/ENGINEERING-PRINCIPLES.md`: complete, real Python (full yt-dlp /
youtube-transcript-api / faster-whisper adapters), **nothing installed, nothing fetched from YouTube**.

---

## File map

### Package manifest + docs
- `knowledge-pipeline/pyproject.toml` — uv, pinned versions, tiered extras: base (`pydantic`) /
  `[ingest]` (yt-dlp, youtube-transcript-api) / `[asr]` (faster-whisper) / `[dev]` (pytest). `corpus` script.
- `knowledge-pipeline/README.md` — RAM-safe vs env-gated commands, ToS/local-first note, KNOW mapping.
- `knowledge-pipeline/LEARNING.md` — captions (manual/auto/none), datacenter-IP blocking, extractability +
  why visual-only is dangerous, snapshot-on-ingest, faster-whisper/CTranslate2 — course-quality.

### Domain (typed boundaries)
- `src/knowledge_pipeline/domain/models.py` — `VideoRef`, `TranscriptSegment`, `RawTranscript`,
  `CaptionAvailability`/`CaptionFetch`, `FallbackDecision`, `SnapshotRecord`, `ExtractabilityResult`,
  `CorpusEntry`, `CorpusStats`, `IngestOutcome`/`IngestReport` + enums (`CaptionSource`, `Verdict`,
  `FallbackAction`, `IngestStatus`).
- `src/knowledge_pipeline/domain/genres.py` — the north-star (genre × stage) grid + artist anchors
  (Sonder, Brent Faiyaz, Ben Produces, Liyana Ricky, Lowbass Djy).

### Pure core (the testable heart — no I/O)
- `pure/query_grid.py` — `query_grid(stages, genres, artists)` + `grid_coverage` **[KNOW-01]**
- `pure/extractability.py` — `extractability_score(transcript) → score+flags+verdict`, `ScoringConfig`
  (caption-source weight, word density, vocab presence, actionable ratio, multiplicative visual-only
  penalty) **[KNOW-03]**
- `pure/fallback.py` — `fallback_decision(captions) → use|asr|reject` **[KNOW-03]**
- `pure/snapshot.py` — `snapshot_record(raw, now)` (sha256 + injected retrieval date), `content_hash` **[KNOW-02]**
- `pure/dedup.py` — `dedup_video_refs` (merge provenance) + `dedup_already_ingested` (idempotency)
- `pure/captions.py` — `parse_vtt` (VTT/SRT → timestamped segments; yt-dlp subs path)
- `pure/vocab.py` — producer-jargon lexicon, actionable verbs, visual-only phrases, numeric-param regex

### Ports + adapters
- `ports.py` — `DiscoverySource`, `TranscriptFetcher`, `Transcriber`, `CorpusStore`, `Clock`, `RateLimiter`
- Fakes / stdlib (eager): `discovery_fake.py`, `fetch_fake.py`, `transcribe_fake.py`, `corpus_mem.py`,
  `clock_fake.py` (virtual time), `clock_real.py`, `rate_limiter.py`, `corpus_fs.py` (real sqlite — stdlib)
- Real (heavy imports lazy, env-gated): `discovery_ytdlp.py` (yt-dlp ytsearch),
  `fetch_youtube.py` (youtube-transcript-api primary + yt-dlp subs secondary),
  `transcribe_whisper.py` (faster-whisper large-v3 + yt-dlp audio)

### Orchestration + persistence + CLI
- `pipeline.py` — `IngestPipeline` (discover → dedup → fetch+fallback → ASR → snapshot → score → register),
  `PipelineConfig`. Pure over ports.
- `registry_sql.py` — `registry.sqlite` DDL (sources · snapshots · extractability) + snapshot file layout.
- `fixtures.py` — loads `fixtures/transcripts/*.json` into fake-adapter inputs.
- `cli.py` — `corpus discover | ingest | list (--by-genre/--by-extractability) | show (--segments) | stats`;
  compact output; offline `--fixtures` mode + env-gated live mode.

### Fixtures + tests
- `fixtures/transcripts/` — 6 videos: rich-manual (KEEP), good-auto (KEEP), no-captions→ASR (KEEP),
  noisy-auto→ASR (KEEP), **visual-only (REJECT)**, sparse vlog (LOW_SIGNAL).
- `tests/` — `test_query_grid`, `test_extractability`, `test_fallback`, `test_snapshot`, `test_dedup`,
  `test_captions`, `test_rate_limiter` (fake clock), `test_corpus_store` (mem **and** real sqlite),
  `test_pipeline` (e2e), `test_cli`.

---

## Requirement coverage

| Req | What | Where |
|---|---|---|
| **KNOW-01** | Discovery across production-stage × north-star-genre grid + artist/producer anchors | `pure/query_grid.py` + `domain/genres.py`; `DiscoverySource` (yt-dlp + fixture); `pipeline.discover` (throttle + dedup) |
| **KNOW-02** | Local fetch (yt-dlp + youtube-transcript-api) + throttle + snapshot-on-ingest (hash + retrieval date) surviving takedowns | `fetch_youtube.py` (home-IP, lazy); `IntervalRateLimiter`+`Clock`; `pure/snapshot.py`; `corpus_fs.py` immutable snapshot files + `registry.sqlite`; idempotent via `dedup_already_ingested`/`store.has` |
| **KNOW-03** | ASR fallback when captions missing/poor + extractability score; flag visual-only/low-signal instead of faking | `pure/fallback.py`; `transcribe_whisper.py` (faster-whisper, fallback-only); `pure/extractability.py` (visual-only multiplicative penalty → REJECT) |
| **KNOW-04** | ≥100 north-star videos; registry inspectable by genre/extractability (live ingest env-gated) | grid math (4×11 + anchors × `--limit`, deduped > 100); `corpus list --by-genre/--by-extractability` + `corpus stats`; fixture corpus for tests |

---

## Verification (honest: reviewed/run vs env-gated)

### RAM-safe — actually RUN here (base env: Python 3.12, pydantic 2.11, pytest 8.3, sqlite3 stdlib)
- **`python -m pytest -q` → 77 passed** (~1.7s). No yt-dlp / youtube-transcript-api / faster-whisper in the
  test path; heavy/network adapters import their libs lazily and are never touched by tests.
- Coverage that genuinely ran: the pure scorer (rich KEEP / visual-only REJECT / source-weight ordering /
  bounds), fallback ladder, snapshot hash+injected-date+drift, dedup + idempotency, VTT parser,
  **throttle verified in virtual time on the FakeClock** (no real sleep), the CorpusStore contract against
  **both** the in-memory fake **and the real `FilesystemCorpusStore` (sqlite is stdlib)** incl.
  cross-instance durability, the **pipeline end-to-end** on the fixture corpus (right caption path per video,
  ASR fired only on the fallback branch, honest verdicts, idempotent re-run), and the **CLI** through argv.
- Package import-cleanliness confirmed: `import knowledge_pipeline.{pipeline,cli,adapters}` succeeds with
  `faster_whisper` absent from the env (proves lazy imports hold).
- Offline CLI smoke run executed: `corpus ingest --fixtures` → `ingested=5 rejected=1`; `list --by-genre`,
  `list --by-extractability`, `stats`, `show altpiano_visual_only --segments 3` all render correctly
  (visual-only scored 0.08 → REJECT with `visual_only` flag and `visual_penalty=0.85`).

### Env-gated — NOT run here (network + ToS + ASR weights; run from a HOME IP)
Exact commands (also in README):
```bash
cd knowledge-pipeline
uv sync --extra ingest --extra asr          # pin the EXACT yt-dlp version first (ships ~biweekly)
uv run corpus discover --limit 5            # inspect the grid → candidate plan (no ingest)
uv run corpus ingest  --limit 5 --corpus-root ./.nameless-knowledge/corpus --min-interval 2.5 --jitter 0.5
uv run corpus list    --corpus-root ./.nameless-knowledge/corpus --by-genre
uv run corpus stats   --corpus-root ./.nameless-knowledge/corpus    # confirm ≥100 + north-star concentration
uv run corpus show <VIDEO_ID> --corpus-root ./.nameless-knowledge/corpus --segments 5
```
**ToS / local-first caveat:** yt-dlp + youtube-transcript-api are unofficial and against YouTube ToS at
scale; run from a **home/residential IP** (datacenter IPs get `RequestBlocked`). Treat ingest as a slow,
throttled, idempotent background batch. The ≥100 KNOW-04 count is reached only by this live run; the
bundled 6-video fixture corpus is for tests + the offline demo.

---

## Notes / deferred
- Hard-rejects (no captions + ASR disabled) are registered as a `none`/REJECT row for an honest, idempotent
  record. To re-process them after enabling ASR, clear the entry (documented tradeoff).
- `cheap_auto_quality` in the real fetcher is a deliberately crude proxy (punctuation + density) that only
  gates the "worth re-ASR-ing this auto track?" decision — not the final extractability score.
- Out of scope (next phases): claim extraction + cross-reference (Phase 4); synthesis + citation gate +
  authored Skills (Phase 5); sparse-genre audio grounding (Phase 6).
