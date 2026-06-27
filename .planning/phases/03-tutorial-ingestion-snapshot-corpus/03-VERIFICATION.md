---
phase: 3
phase_name: Tutorial Ingestion + Snapshot Corpus
status: passed
verified_by: tests-run (77 RAM-safe) + review (course-project mode)
date: 2026-06-28
---

# Phase 3 Verification — Tutorial Ingestion + Snapshot Corpus

**Executed here (orchestrator re-ran):** `cd knowledge-pipeline && python -m pytest -q` → **77 passed in 1.43s**. Covers the pure core (query grid + anchors, extractability scoring incl. the multiplicative visual-only penalty → REJECT, caption-source weighting, fallback decision, snapshot hashing with injected date, dedup), throttling in virtual time (FakeClock, no real sleep), the CorpusStore contract against BOTH the in-memory fake AND the real `FilesystemCorpusStore`+sqlite (incl. cross-instance durability), the full ingest pipeline e2e on a 6-fixture corpus (correct caption path per video, ASR only on fallback, idempotent re-run), and the CLI via argv. Import-cleanliness confirmed with `faster_whisper` absent.

## Success criteria
| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Discovery across stage×genre grid + artist anchors → candidate queue | ✅ executed (fake) / reviewed (yt-dlp) | `query_grid`, `domain/genres.py`, `DiscoverySource` |
| 2 | Local fetch + throttle + snapshot-on-ingest (hash + date), survives takedown | ✅ executed (fake) / reviewed (real) | `fetch_youtube`, `IntervalRateLimiter`+Clock, `snapshot_record`, `corpus_fs`+registry.sqlite |
| 3 | ASR fallback + extractability score + visual-only flag | ✅ executed | `fallback_decision`, `transcribe_whisper` (fallback-only), `extractability_score` (visual-only→0.08/REJECT) |
| 4 | ≥100 north-star videos visible in corpus registry | ⏳ env-gated (live ingest) / ✅ logic executed | grid math >100; `corpus list/stats --by-genre/--by-extractability`; fixture corpus for tests |

## Requirement coverage
KNOW-01 ✅ · KNOW-02 ✅ · KNOW-03 ✅ · KNOW-04 ✅ (logic + registry; live ≥100 ingest env-gated)

## Testability law — satisfied
✅ ports (Discovery/Fetcher/Transcriber/CorpusStore/Clock/RateLimiter) × real+fake · ✅ pure core (query_grid/extractability/fallback/snapshot/dedup) · ✅ SoC (domain/pure/adapters/pipeline) · ✅ loose coupling (Protocols, lazy heavy imports) · ✅ tests RUN (77).

## Learning artifact
`knowledge-pipeline/LEARNING.md` — captions (manual/auto/none), datacenter-IP blocking + local-first, extractability + the visual-only danger ("quality in, quality out"), snapshot-on-ingest for citation durability, faster-whisper/CTranslate2.

## Env-gated (home/residential IP, real env)
`cd knowledge-pipeline && uv sync --extra ingest --extra asr` (pin exact yt-dlp first) · `uv run corpus discover/ingest/list/stats/show …`. ToS: unofficial tooling, local-first only; the live run is what reaches KNOW-04's ≥100.

**PASS** — RAM-safe layer executed (77 tests), heavy/live leaf reviewed-complete + env-gated.
