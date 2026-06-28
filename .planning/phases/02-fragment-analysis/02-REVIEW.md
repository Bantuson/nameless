---
status: issues
phase: 02-fragment-analysis
depth: standard
files_reviewed: 23
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
---

# Phase 2: Fragment Analysis — Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard
**Reviewer:** Claude (gsd-code-reviewer)
**Status:** issues_found

## Summary

Reviewed the Python worker plane that takes a fragment to `analyzed` (f0/chroma/onset/beat/tempo/key/LUFS,
CLAP embeddings, pgvector retrieval), plus its cross-language mirror of the Rust lifecycle. I read the
canonical Rust (`crates/nameless-core/src/state_machine.rs`, `provenance.rs`) to verify the mirror.

The high-risk surfaces are largely **correct**, and I want to say so plainly rather than manufacture defects:

- **`pure/key.py`** — the Krumhansl-Kessler profiles are the canonical published weights, the
  tonic rotation `PROFILE[(pc - tonic) % 12]` is right, argmax uses strict `>` with deterministic tie-break,
  and the zero-variance guard is correct. Key math is sound.
- **`pure/vectors.py`** — zero-vector guards on normalize/cosine, stable descending argsort for ranking.
  Correct and deterministic.
- **`domain/state.py`** — the `transition()` table is a **byte-faithful mirror** of the Rust `transition()`
  function (verified edge-by-edge against the 480-triple Rust matrix). No drift in the mirrored function.
- **`repo_pg.py` / migration 0002** — 512-d consistency holds (`CLAP_DIM` ⇄ `vector(512)`), HNSW
  `vector_cosine_ops` matches the `<=>` query, all values are parameterized, and the one interpolated
  token (`column`) comes from a fixed enum map — **no SQL injection**.

The defects below are about the *gaps around* that correct core: the mutation chokepoint mirrors only
`transition()` and not Rust's stricter `apply()`/`place()` (the sampled-attribution surface), and the
run loop's exception handling is narrower than the failure set it can actually face.

## Critical Issues

### CR-01: Python `advance()` mirrors only Rust `transition()`, not the stricter `apply()`/`place()` sampled-placement gate

**File:** `workers/src/nameless_workers/adapters/repo_pg.py:92-111`, `workers/src/nameless_workers/adapters/repo_mem.py:55-64`, `workers/src/nameless_workers/domain/state.py:88-137`

**Issue:** In Rust, the *mutation chokepoint* is `Fragment::apply` / `Fragment::place`
(`state_machine.rs:261-288`), which add a guard **on top of** bare `transition()`:
`apply(Place)` on a `Sampled` fragment is refused outright, and the only door to placing a sample is
`place(Some(&CompleteAttribution))` (SAMP-03 — "there is no ungated path that writes `Placed` onto a
sample"). The Python worker's mutation chokepoint is `FragmentRepo.advance()`, which calls the shared
pure `transition()` and nothing else. Because `transition(SAMPLED, ANALYZED, PLACE)` legally returns
`PLACED` (faithfully, matching Rust's bare `transition`), a Python caller invoking
`advance(fragment_id, Transition.PLACE)` on a `sampled` fragment would drive it to `placed`
**with no attribution** — exactly the bypass Rust closes. The two languages therefore disagree about
what the *mutation layer* permits for sampled placement.

Why it matters: this is the precise cross-language legality divergence on the sampled-attribution
surface. It is **latent in Phase 2** — the consumer only ever issues `ANALYZE` / `MARK_ANALYZED`
(`consumer.py:89,117`), so no Python code drives `PLACE` today, and the `transition()` mirror test
(`test_state_mirror.py`) only reproduces the `transition` matrix, not `apply`/`place`. But the moment the
worker plane is extended to drive placement (e.g. Phase-8 stem→`sampled` promotion lives in this same
package), the attribution gate is silently bypassed on the Python side, and the `advance()` docstring's
promise that "the worker is structurally unable to drive a fragment down an illegal path" no longer holds
for sampled material.

**Fix:** Mirror the *mutation* chokepoint, not just `transition`. Either (a) refuse `(Sampled, PLACE)` in
`advance()` the way Rust's `apply` does and add a separate attribution-aware `place()` to the repo port, or
(b) port `place()`/`PlaceError::AttributionRequired` into `domain/state.py` and route any placement through
it. Minimum bar: add a `(Sampled, PLACE)` refusal so Python cannot place a sample without going through an
attribution-checked path.

```python
# domain/state.py — alongside transition(), mirror Rust apply()'s sampled refusal:
def apply_guarded(provenance: Provenance, from_state: FragmentState, t: Transition) -> FragmentState:
    if provenance is Provenance.SAMPLED and t is Transition.PLACE:
        # SAMP-03: a sample reaches Placed only via an attribution-checked place(), never bare advance.
        raise IllegalTransition(from_state=from_state, transition=t)
    return transition(provenance, from_state, t)
# repo advance() should call apply_guarded(), and the mirror test must reproduce Rust's apply/place tests.
```

## Warnings

### WR-01: Run loop catches only `AnalyzeError`; `IllegalTransition` / `KeyError` / `ValidationError` escape and kill the worker

**File:** `workers/src/nameless_workers/runner.py:40-48`, `workers/src/nameless_workers/consumer.py:64-94`

**Issue:** `run_once` wraps `consumer.handle` in `except AnalyzeError` only. But `handle` can raise other
exception types that are **not** `AnalyzeError`:
- `IllegalTransition` — raised directly at `consumer.py:94` for any non-analyzable state (placed/mixed/
  ai-path/rejected), and propagated from `advance()` (`consumer.py:89`) for an `ai_generated` or
  concurrently-advanced fragment. (`AnalyzeError` and `IllegalTransition` are unrelated classes.)
- `KeyError` — `repo.advance` raises `KeyError` if the row vanished between `get_fragment` and `advance`
  (`repo_pg.py:102`, `repo_mem.py:58`).
- `pydantic.ValidationError` — `get_fragment` (`consumer.py:68`, *outside* the try block) constructs
  `FragmentRecord` from DB rows; a NULL `note_text`/`audio_uri`/`kind` would raise here.

None of these are caught by `run_once`, so they propagate out of `run_forever`'s loop (`runner.py:67`)
and **crash the entire worker**. A single poison/misrouted fragment takes down the loop instead of being
acked-and-skipped or retried/dead-lettered — the opposite of the bounded-retry DoS-safety the design
claims. The existing test only exercises the `AnalyzeError` (load-failure) path (`test_runner.py:45-76`),
so this gap is untested.

**Fix:** In `run_once`, catch the structural-illegal/not-found family explicitly and **ack** them (they
will never succeed on retry — a placed fragment will not become analyzable), and treat unexpected
exceptions as retryable. For example:

```python
try:
    outcome = consumer.handle(envelope)
except AnalyzeError as exc:
    logger.warning("analysis failed (will retry): %s", exc)
    source.retry(lease)
    return None
except (IllegalTransition, ValidationError) as exc:
    logger.error("permanently un-analyzable job, acking to drop: %s", exc)
    source.ack(lease)          # do not loop forever on a structurally-illegal job
    return None
```

### WR-02: `run_forever` polls the source a second time per idle check — leaks a claimed lease under real `poll()` semantics, and busy-loops on retry

**File:** `workers/src/nameless_workers/runner.py:66-74`

**Issue:** `run_once` already calls `source.poll()` to claim a job. The idle check then calls
`source.poll()` **again** (`runner.py:68`). The `JobSource` contract defines `poll()` as *claiming* a job
(`ports.py:138-147`: "Claim feature-extract jobs…", returns a `JobLease` = "A claimed job"). With a real
`SELECT … FOR UPDATE SKIP LOCKED` poller, this second poll **claims a second job and immediately discards
the lease** without ack/retry — that job is now locked/in-flight but unprocessed, leaking until lease
timeout and effectively being skipped this cycle. The `InMemoryJobSource.poll()` is *non-destructive*
(it peeks `self._queue[0]`, `job_source_mem.py:35-39`), so tests pass and the bug is masked. Separately,
when `run_once` returns `None` because a job was **retried** (re-queued), the second `poll()` sees that job,
`idle` stays 0, and the loop spins with no `poll_interval_s` sleep — a hot retry loop. `run_forever` has no
test coverage.

**Fix:** Do not poll twice. Have `run_once` distinguish "queue empty" from "job retried/misrouted" (e.g.
return a small status enum or `(outcome, was_idle)`), and drive the idle counter off that single claim:

```python
status = run_once(source, consumer)   # returns e.g. RunResult.IDLE | DID_WORK | RETRIED
if status is RunResult.IDLE:
    idle += 1
    ...
    time.sleep(poll_interval_s)
else:
    idle = 0
```

## Info

### IN-01: `estimate_key` on a NaN chroma returns `correlation = -2.0`, an out-of-range sentinel

**File:** `workers/src/nameless_workers/pure/key.py:70-95`

**Issue:** `best_corr` is seeded at `-2.0`. If `chroma_mean` contains NaN (e.g. a degenerate librosa
chromagram), every `_pearson` result is NaN, every `corr > best_corr` comparison is `False`, and the loop
returns `tonic_pc=0, mode="maj", correlation=-2.0` — a value outside the documented `[-1, 1]` range and
below the "silence" 0.0 floor `_pearson` is meant to produce. Downstream consumers reading
`key_confidence` as a `[-1,1]` confidence would mis-handle `-2.0`. [env-gated — requires a real librosa
chromagram to produce NaN; not reachable from `FakeFeatureExtractor`.]

**Fix:** Guard the input (`if not np.all(np.isfinite(chroma)): treat as flat/ambiguous`) and/or clamp the
returned correlation to `[-1, 1]`, returning a defined ambiguous result (`correlation=0.0`) rather than the
`-2.0` initialization sentinel.

### IN-02: Consumer validates `audio.dim == note.dim` but not `== CLAP_DIM` (512)

**File:** `workers/src/nameless_workers/consumer.py:106-110`

**Issue:** The dim-mismatch guard ensures the two towers agree, but a real embedder returning a consistent
but *wrong* width (e.g. a swapped 1024-d checkpoint) passes this check and only fails later at the
`vector(512)` column insert, surfacing as an opaque DB error rather than a clear "embedder produced
non-512 vectors" message. `ClapEmbedder.expected_dim` already exposes the target. [env-gated — needs the
real CLAP stack.]

**Fix:** Also assert `audio_embedding.dim == CLAP_DIM` (import the constant from `nameless_workers`) and
raise an `AnalyzeError` naming the joint-space width mismatch before persisting.

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
