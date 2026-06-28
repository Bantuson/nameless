---
status: issues
phase: 08-stem-library-attributed-sampling
depth: standard
files_reviewed: 27
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
---

# Phase 8: Code Review Report — Stem Library + Attributed Sampling

**Depth:** standard (read every file; Rust + Python language checks)
**Status:** issues_found (no BLOCKERs; 4 WARNING, 4 INFO)

## Summary

This is a strong, type-driven implementation of the attribution integrity boundary. The headline
invariant — a `sampled` fragment cannot be placed without complete attribution — is genuinely well
built: `CompleteAttribution` is structurally complete (every field non-`Option`, no public
constructor yields an incomplete value, serde-safe), `PartialAttribution::into_complete` is the sole
gate, whitespace titles/artists and inverted/zero time-ranges are treated as missing, `--rights` is a
required first-class field (no silent default), the credits sheet always leads with the
"attribution is not permission" notice, and migration 0004 mirrors the type with `NOT NULL` columns +
a positive-span CHECK. The ports/adapters discipline (real Demucs adapter + deterministic fake behind
a `Protocol`/trait, pure content-hashing core) is clean and testable. No security vulnerabilities
were found: all SQL is parameterized `query!`, no path traversal (content-hash keys only), no eval/
injection, no hardcoded secrets.

The findings below are correctness/robustness gaps, not invariant breaks. The most important is that
the no-bypass guarantee is partly conventional rather than fully structural (WR-01), and that
`do_sample_add` performs three non-atomic writes (WR-02).

Build-mode honesty: nothing here is a "won't compile/can't run Demucs" complaint. WR-01/02/04 and all
INFO items are provable by reading. WR-03's runtime wrap behavior is marked [env-gated] where it needs
a live Postgres to observe the exact failure.

---

## Warnings

### WR-01: Sampled-attribution gate is enforced at the chokepoint, not structurally — `transition()` still returns `Ok(Placed)` for an unattributed sample

**File:** `crates/nameless-core/src/state_machine.rs:178-207, 236-249, 261-271`
**Issue:** The module documents the gate as structural ("there is no bypass to forget, because the
bypass cannot be spelled"), but the actual enforcement is a runtime `if provenance == Sampled &&
attribution.is_none()` inside `place()` (line 245) plus a runtime guard inside `apply()` (line 262).
The low-level, **public** `transition(Sampled, Analyzed, Place)` returns `Ok(Placed)` with no
attribution check at all (the matrix test at line 387 confirms this is intentionally legal at the
lifecycle level). Combined with `Fragment.state` being a **public** field (`fragment.rs:155`), the
"no bypass" property holds only by the convention that all callers go through `place()`/`apply()`.
Within `nameless-core` that discipline is currently respected (`self.state =` appears only at
state_machine.rs:269 and 285, matching the Phase-1 grep-gate T-02-02), but any future driver in
`nameless-cli`/`nameless-adapters` that calls `transition()` directly, or assigns `frag.state =
FragmentState::Placed`, places an unattributed sample. Sample placement is not wired yet (M1), so no
shipped path exploits this today.
**Why it matters:** This is the phase's headline invariant. The type-level completeness of
`CompleteAttribution` is solid, but the *linkage* between "sampled + being placed" and "a
`CompleteAttribution` must be presented" is a runtime check that a caller can skip, not a type that
cannot be constructed.
**Fix:** Make the linkage structural so the bypass cannot be spelled. Options: (a) have `transition`
itself reject `(Sampled, _, Place)` (force all sample placement through `place()`); and/or
(b) introduce a witness type, e.g. only `place()` can produce the value that the repo's "mark placed"
write accepts, and make `Fragment.state` non-`pub` with a private setter. At minimum, soften the
doc-comment claim from "cannot be spelled" to "is enforced at the `place`/`apply` chokepoints" and add
a grep-gate test (mirroring T-02-02) asserting no `transition(.. Place)` call sites exist outside
`place()`.

### WR-02: `do_sample_add` is non-atomic — a mid-sequence failure orphans a sampled fragment or drops its analysis job

**File:** `crates/nameless-cli/src/cli.rs:483-501`
**Issue:** After the completeness gate passes, the handler performs three independent, non-transactional
writes against different stores: `repo.insert_fragment(&frag)` (line 490), `samples.insert_attribution(&attribution)`
(line 494), and `queue.enqueue(FeatureExtract{...})` (line 497). If `insert_attribution` fails, a
`sampled` fragment exists in the graph with **no** attribution row — invisible to `credits` (which reads
attribution rows) yet present as a fragment. If the enqueue fails, the fragment+attribution exist but no
analysis job was ever queued, so the sample never travels the human analysis path. There is no rollback.
**Why it matters:** It produces inconsistent state on the integrity boundary. The placement gate still
protects against *placing* an unattributed sample (a driver could not load a non-existent attribution
row), but the orphaned-fragment / missing-job states are silent data-quality defects with no recovery.
**Fix:** Wrap the three writes in a transaction (the Postgres profile can; the file/in-memory stores
would need a compensating cleanup on failure), or order them so a failure is self-healing and document
the recovery. At minimum, on `insert_attribution`/`enqueue` failure, delete the just-inserted fragment
before returning the error.

### WR-03: `u32 → i32` casts in the Postgres adapter silently wrap large millisecond values, diverging from the file/in-memory stores

**File:** `crates/nameless-adapters/src/sample_store_pg.rs:59-60, 164-165, 305-306`; `migrations/0004_sampling.sql:54,55,82,83`
**Issue:** The domain models `start_ms`/`end_ms`/`duration_ms`/`sample_rate` as `u32`, but the schema
columns are `int` (i32) and the adapter casts with `as i32` on write (`a.start_ms as i32`, line 165)
and `as u32` on read (`r.start_ms as u32`, line 305). For any value in `(i32::MAX, u32::MAX]`
(> ~2.147e9, i.e. ~24.8 days in ms) the write wraps to a negative `int`. `parse_time_range`
(`cli.rs:302`) accepts any `u32`, so `--time-range 0-4000000000` parses, then on the Postgres path the
end wraps negative and either trips the `check (end_ms > start_ms)` constraint or stores a corrupt
value — whereas the file/in-memory stores (no i32 narrowing) accept it fine. Same divergence for
`duration_ms`/`sample_rate`. Realistic sample slices stay well within i32, so this is latent, not
routinely hit.
**Why it matters:** Same logical input produces different outcomes on `--local` vs the server profile
(silent acceptance vs constraint error/corruption) — a correctness/consistency gap on persisted credit
data.
**Fix:** Either widen the columns to `bigint` and bind `i64`, or validate/clamp the `u32` values to
`i32::MAX` at the CLI/`into_complete` boundary and return a typed error above the range instead of
casting. [env-gated] observing the exact constraint failure needs a live Postgres.

### WR-04: Sample time-range is never bounds-checked against the stem; fragment `duration_ms` records the slice while `audio_uri` points at the full stem

**File:** `crates/nameless-cli/src/cli.rs:458-489`
**Issue:** `do_sample_add` records `start_ms`/`end_ms` straight from the flag with no check that the
range lies within the stem's actual length (`stem.duration_ms`, available at line 449). A user can
sample `12000-18000` from a 6000 ms stem; the out-of-range slice is accepted, persisted, and printed
in the credits sheet as authoritative. Separately, the new fragment's `duration_ms` is set to
`end_ms - start_ms` (the slice length, line 486) while its `audio_uri` is the **full** stem
(`stem.audio_uri.clone()`, line 485) — so `duration_ms` does not describe the bytes the URI addresses
until the M1 exporter actually trims them.
**Why it matters:** The credits sheet is the project's honesty artifact (SAMP-05); a time-range that
exceeds the source is a silent inaccuracy. The duration/URI mismatch is a latent trap for any consumer
that assumes `duration_ms` describes `audio_uri`.
**Fix:** When `stem.duration_ms` is known, reject `end_ms > stem.duration_ms` with a clear error.
Either trim the stem to the slice at promotion time (so `audio_uri` matches `duration_ms`), or store
the full-stem duration on the fragment and rely solely on the attribution range for the slice — and
document the chosen contract.

---

## Info

### IN-01: `JobEnvelope::Separate { fragment_id }` (Rust) and `SeparateJob` (Python) are dead variants — never enqueued or consumed

**File:** `crates/nameless-core/src/job.rs:35`; `workers/src/nameless_workers/domain/models.py:38-44`
**Issue:** The fragment-keyed `Separate` job is defined and round-trip tested (job.rs:185-193;
models parity), but nothing enqueues it — `do_stems_separate` (`cli.rs:423`) enqueues only
`SeparateTrack`, and the consumer handles only `SeparateTrackJob`. The Python test even calls it "a
Phase-8 job misrouted to this worker" (`tests/test_runner.py:85`).
**Fix:** Remove `JobEnvelope::Separate` / `SeparateJob` (and their parity tests) until a real
fragment-level separation path exists, or add a comment marking them reserved-for-M? so a reader does
not assume a live code path.

### IN-02: `stem_type` is unconstrained `text` in both tables while `rights_status` is a proper enum

**File:** `migrations/0004_sampling.sql:50,81`
**Issue:** `rights_status` is a DB enum (`NOT NULL`), but `stem_type` is free `text` with no `CHECK`/
enum, so an invalid label (e.g. `'kazoo'`) can be written and is only caught on read by
`parse_stem_type` (`sample_store_pg.rs:276`, returns `Serialization` error). The Rust/Python `StemType`
enums make the writers safe, but the DB itself does not mirror the type the way it does for rights.
**Fix:** Add `create type stem_type as enum (...)` (or a `check (stem_type in (...))`) for the same
type/schema lockstep the module comment claims, or note explicitly why stem_type stays `text`.

### IN-03: Separated stems are always persisted with `duration_ms = NULL`

**File:** `workers/src/nameless_workers/separation_consumer.py:97`; `workers/src/nameless_workers/pure/separation.py:34-60`
**Issue:** `build_stem_records(reference_track_id, result)` is called without `duration_ms`, and
`SeparationResult` carries no total duration, so every `stems` row has `duration_ms = None`. That is
allowed (the column/field is `Optional`), but it means `stems list` never shows duration and WR-04's
bounds check has nothing to check against.
**Fix:** Derive duration from the decoded sample count / `sample_rate` in the separator and thread it
into `build_stem_records`, or document that stem duration is intentionally deferred.

### IN-04: Mixed FK delete semantics in migration 0004

**File:** `migrations/0004_sampling.sql:49,75-78`
**Issue:** `stems.reference_track_id` and `sample_attribution.{fragment_id,project_id}` use
`on delete cascade`, but `sample_attribution.reference_track_id` and `sample_attribution.stem_id` use
the default `no action`. Net effect: a `reference_tracks` row that has any sample attribution cannot be
deleted (the cascade to `stems` is blocked by `sample_attribution.stem_id`). This is plausibly the
intended "preserve provenance" behavior, but it is implicit.
**Fix:** State the intended deletion policy in a comment (preserve credited sources by restricting),
or make it explicit/consistent so the behavior is not a surprise during data cleanup.

---

_Reviewer: Claude (gsd-code-reviewer) · Depth: standard · No source files modified._
