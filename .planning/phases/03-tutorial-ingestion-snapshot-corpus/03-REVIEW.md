---
status: issues
phase: 03-tutorial-ingestion-snapshot-corpus
depth: standard
files_reviewed: 29
findings:
  critical: 1
  warning: 3
  info: 4
  total: 8
---

# Phase 3: Code Review Report — Tutorial Ingestion + Snapshot Corpus

**Reviewed:** 2026-06-28
**Depth:** standard (Python: subprocess/shell-injection, path traversal, None/empty handling, clock injection, hashing correctness)
**Files Reviewed:** 29
**Status:** issues_found

## Summary

Strong phase. The testability law is honored throughout: every network/ASR/clock/throttle dependency
sits behind a `Protocol` with a real (lazy-import) adapter and a deterministic fake; the pure core is
genuinely pure and the orchestration is port-only. Snapshot hashing is canonical/stable, the
extractability gate is explainable, and the SQL is fully parameterized (no SQL-injection surface). The
rate-limiter math is correct for the sequential pipeline, and `now`/`sleep` are injected, not wall-clocked.

Eight findings. The one Critical is a path-traversal write/read primitive: `video_id` (externally
sourced from yt-dlp metadata, and from the CLI for reads) flows unsanitized into a filesystem path. The
highest-value Warning sits in the heart of the phase — the visual-only deixis penalty double-counts
overlapping phrases and substring-matches bare `"boom"`, which false-positively penalizes legitimate
craft talk ("boomy low end"). A second Warning notes that the documented snapshot drift/tamper-detection
guarantee is unreachable in the implemented flow. Most others are quality/hardening notes.

No "can't reach YouTube / can't run whisper" issues are filed — those are env-gated by design. Findings
that only manifest against real network data are marked `[env-gated]`.

## Critical Issues

### CR-01: Path traversal via unsanitized `video_id` in snapshot path construction

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/corpus_fs.py:104` (write) and `:112` (read)
**Issue:** `video_id` is interpolated directly into a filesystem path with no validation:
```python
rel_path = f"snapshots/{transcript.video_id}.json"
abs_path = self._root / rel_path
abs_path.write_text(...)               # write_snapshot
...
abs_path = self._snapshots_dir / f"{video_id}.json"   # load_snapshot
```
`video_id` is externally sourced — `discovery_ytdlp.py:51` takes it from yt-dlp's `entry.get("id")`, and
`load_snapshot` is reachable from `corpus show <video_id>` where `video_id` is an arbitrary CLI argument.
A value like `../../../../etc/cron.d/x` (write) or `../../../../etc/passwd` (read, with a `.json` suffix)
escapes the corpus root. `pathlib`'s `/` operator does NOT collapse `..` and a leading `/` would even
reset to an absolute path. Exploitability is low in practice (this is a solo, local-first tool and real
YouTube IDs are an 11-char `[A-Za-z0-9_-]` set), but the code performs no enforcement of that, so an
unexpected/crafted id is an arbitrary-file-write/read primitive.
**Fix:** Validate the id against the known YouTube id shape before using it as a path component, and/or
resolve-and-confine to the snapshots dir:
```python
import re
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
def _safe_id(vid: str) -> str:
    if not _VIDEO_ID.match(vid):
        raise ValueError(f"unsafe video_id: {vid!r}")
    return vid
# then: rel_path = f"snapshots/{_safe_id(video_id)}.json"
# and assert abs_path.resolve().is_relative_to(self._snapshots_dir.resolve())
```

## Warnings

### WR-01: Visual-only penalty double-counts overlapping phrases and substring-matches bare tokens

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/extractability.py:163` (with `pure/vocab.py:70-91`)
**Issue:** This is the core gate, so calibration errors matter. Two compounding defects in
`_visual_only_penalty`:
```python
deixis = sum(low.count(phrase) for phrase in VISUAL_ONLY_PHRASES)
```
1. **Overlapping phrases are counted multiple times.** `VISUAL_ONLY_PHRASES` contains both `"like that"`
   and `"just like that"`, both `"like this"` and `"something like this"`, both `"boom"` and `"and boom"`.
   The text `"just like that"` contributes 2 to `deixis` (matches `"like that"` AND `"just like that"`);
   `"and boom"` contributes 2. The penalty is therefore systematically harsher than the per-phrase model
   the docstring describes.
2. **Bare-token substring matching produces false positives.** `"boom"` and `"you see"` are matched as
   substrings of the lowercased text, so `"boomy"`, `"boombap"`, `"boomier"` (all common in
   bass/drum tutorials — exactly the target genre) each register as screen-pointing deixis and attenuate
   the score of legitimately teachable craft.
**Why it matters:** Both effects push borderline-good transcripts toward the `visual_only` flag and a
lower score — the gate can down-weight or reject real craft (the opposite of the intended "quality in"
goal). A bass tutorial saying "tighten the boomy low end" is penalized for the word "boomy".
**Fix:** Count on word/phrase boundaries and de-overlap. E.g. match each phrase with `\b...\b` regex
(so `"boom"` ≠ `"boomy"`), and either order phrases longest-first consuming matched spans, or treat
deixis as a set of matched phrase-types rather than a raw substring tally.

### WR-02: Snapshot drift/tamper detection is documented but unreachable in the implemented flow

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/snapshot.py:6-9, 52-62` vs `pipeline.py:106` and `adapters/corpus_fs.py:111-130`
**Issue:** `snapshot.py` states the content hash "detects drift (someone re-captioned the video)" and
`models.py:210` says the sha256 makes "tampering/drift detectable." Neither is realized:
- `pipeline.ingest` calls `dedup_already_ingested(videos, store.known_ids())` (`pipeline.py:106`), which
  drops any already-known `video_id` *before* fetching. An already-ingested video is therefore never
  re-fetched, so a re-captioning can never be observed — drift detection is dead code in the pipeline.
  Idempotency is keyed purely on `video_id`, not on the content hash.
- `load_snapshot` (`corpus_fs.py:111`) reconstructs the transcript but never recomputes/compares
  `content_sha256` against the stored value, so a tampered snapshot file is not detected on read either.
**Why it matters:** The citation-survival promise (snapshot file + retrieval date) IS satisfied, but the
secondary integrity guarantees the docstrings advertise are not. A reviewer trusting the comments would
believe drift/tamper checks exist when they don't.
**Fix:** Either (a) soften the docstrings to scope the hash to "stable fingerprint + idempotency key,"
or (b) implement it: verify `content_hash(loaded) == stored_sha256` in `load_snapshot` (raise/log on
mismatch), and add a `corpus refresh`/`--recheck` path that re-fetches and compares the hash for drift.

### WR-03: Fallback ladder can skip ASR and silently use noisy auto-captions when a manual track exists but is unusable [env-gated]

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/fetch_youtube.py:183-221` with `pure/fallback.py:45-50`
**Issue:** In the yt-dlp subtitle path, availability is computed from track *existence*:
`has_manual = bool(subs)` (`:183`). But `_pick_track` (`:211`) only returns a track that has a `vtt`
format. If a video lists a manual track in a non-`vtt` format (e.g. `srv3`) and only an auto track in
`vtt`, then: `has_manual=True` is reported, but the actually-returned transcript has
`caption_source=AUTO`. `fallback_decision` sees `has_manual=True` and returns `USE_CAPTIONS` (no ASR) —
so a noisy auto-caption track is used as-is even though policy wanted ASR for noisy auto. The decision's
`caption_source=MANUAL` also disagrees with the transcript's real `AUTO` source (cosmetic, but a smell).
**Why it matters:** Defeats the "prefer ASR over noisy auto" rule precisely in the messy real-world case
the rule exists for. Only manifests against real yt-dlp data, hence env-gated.
**Fix:** Derive `has_manual`/`has_auto` from what `_pick_track` could actually obtain (i.e. presence of a
usable `vtt` track per source), or set availability from the chosen track's real source after picking,
so the fallback decision reasons over usable tracks, not merely listed ones.

## Info

### IN-01: `_verdict` accepts a `visual_penalty` argument it never uses

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/extractability.py:172`
**Issue:** `def _verdict(score, visual_penalty, source, cfg)` — `visual_penalty` is passed
(`extractability.py:213`) but never read in the body; the verdict is purely score+source driven.
**Fix:** Drop the unused parameter, or use it (e.g. force `LOW_SIGNAL` when `visual_penalty` is high even
if the raw score squeaks past `keep_threshold`) if that was the intent.

### IN-02: `IntervalRateLimiter` is not thread/async-safe

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/rate_limiter.py:41-53`
**Issue:** `acquire` reads/writes `self._last_acquire` without a lock. Correct for the current
single-threaded sequential pipeline, but if discovery/fetch were ever parallelized, concurrent `acquire`
calls would race and under-throttle (the project's stated worst case: IP blocking).
**Fix:** Document the single-threaded assumption on the class, or guard `acquire` with a `threading.Lock`
if concurrency is anticipated.

### IN-03: Snapshots called "immutable" but `write_snapshot` overwrites without a write-once guard

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/corpus_fs.py:99-109`
**Issue:** The evidence files are described as immutable, but `abs_path.write_text(...)` will silently
overwrite an existing snapshot. The pipeline never re-fetches an existing id so this isn't hit today, but
the immutability is by convention, not enforced.
**Fix:** Optionally refuse to overwrite (or write-and-compare-hash) when the snapshot already exists.

### IN-04: `FilesystemCorpusStore` connection is never closed by CLI handlers

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/corpus_fs.py:60-74` and `cli.py:174-253`
**Issue:** `_build_store` opens a cached sqlite connection (WAL); CLI handlers never call `store.close()`.
Harmless at process exit, but leaves `-wal`/`-shm` sidecar files and an open handle for the process
lifetime. `close()` exists but is unused outside tests.
**Fix:** Close the store in the CLI handlers (e.g. `try/finally`) or use it as a context manager.

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
