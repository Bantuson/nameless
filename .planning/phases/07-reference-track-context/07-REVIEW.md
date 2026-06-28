---
status: issues
phase: 07-reference-track-context
depth: standard
files_reviewed: 25
findings:
  critical: 1
  warning: 3
  info: 4
  total: 8
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard (Rust + Python, non-cloning boundary focus)
**Files Reviewed:** 25
**Status:** issues_found

## Summary

Reviewed the Reference-Track Context slice: Rust control plane (reference model + conditioning barrier + 3 store adapters + CLI + output), SQL migration 0003, and the Python restricted analyzer (CLAP embedding + tonal balance + stereo width + LUFS + tempo + vibe).

**The non-cloning guarantee holds by construction, and holds well.** I traced the analyzer output type end to end (Python `NonMelodicFeatures` → `ReferenceContext` → job payload → Rust `reference_context` row → `ReferenceContextSummary` read-back) and found **no field, column, struct member, or code path** that can capture or persist melody / chroma / f0 / chord / key / structure for a reference. The four barriers are real: (1) `ReferenceTrack` is a distinct type from `Fragment` with no `From`/`Into`, so it is compile-time barred from `gather_melodic_conditioning(&[Fragment])`; (2) `NonMelodicFeatures` is sealed `extra="forbid"` with no melodic field; (3) `ReferenceConditioning::from_context` copies only non-melodic targets and drops even the vibe prose; (4) the SQL `reference_context` table has no melodic column. The analyzer deliberately uses `librosa.stft` (magnitude → 5 bands) and `beat_track` (tempo), never `chroma_cqt` or `torchcrepe`, and the ephemeral STFT magnitude is reduced to 5 ratios and discarded — not a chroma/f0 leak surface. `assert_non_melodic` runs as a runtime tripwire on every analyzer output. The `compile_fail` doctest that *proves* the wall could not be exercised in this course build (see IN-04) — it must be confirmed with a real `cargo test`.

The vibe-describer prompt is also clean: only controlled, non-melodic scalars (tempo band, LUFS, width, 5 tonal ratios, a vocabulary-constrained genre tag) flow into the prompt — user-supplied `title`/`artist` are **not** included, so there is no prompt-injection or melodic-narration surface.

The one Critical is a Postgres read-path type error provable by reading the schema against the Rust struct (env-gated to confirm via `cargo sqlx`). The rest are integration-contract and quality issues.

## Critical Issues

### CR-01: `get_context_summary` reads nullable columns into non-`Option` fields — will not compile

**File:** `crates/nameless-adapters/src/reference_store_pg.rs:154-193` (query + struct build); `migrations/0003_reference_tracks.sql:71-79` (column nullability)
**Issue:** In `0003`, `tempo_bpm_min`, `tempo_bpm_max`, `lufs`, `stereo_width` (`real`) and `vibe_description` (`text`) are all **nullable**. The `sqlx::query!` in `get_context_summary` selects them as bare columns, so sqlx infers `Option<f32>` / `Option<String>` for each — but they are assigned straight into `ReferenceContextSummary` fields typed `f32` / `String` (non-`Option`):

```rust
tempo_bpm_min: r.tempo_bpm_min,   // r.tempo_bpm_min: Option<f32>  →  field: f32   ❌
lufs: r.lufs,                      // Option<f32>  →  f32   ❌
stereo_width: r.stereo_width,      // Option<f32>  →  f32   ❌
vibe_description: r.vibe_description, // Option<String> → String   ❌
```

The author correctly added `!` non-null overrides for `tonal_balance::text as "tonal_balance!"` and `coalesce(...) as "embedding_dim!"` but forgot them for these five. This fails `cargo sqlx`/`cargo check` with type mismatches — the production read path does not compile as written. (Note: `genre` is correctly `Option<String>` on both sides; `analyzer_version` and `reference_track_id` are `not null` in the schema so they're fine.) **[env-gated — confirm with `DATABASE_URL=... cargo check -p nameless-adapters --features postgres` against a migrated DB]**
**Fix:** Prefer making the measured columns `NOT NULL` (the analyzer always produces them), which also tightens the schema:
```sql
tempo_bpm_min    real not null,
tempo_bpm_max    real not null,
lufs             real not null,
stereo_width     real not null,
vibe_description text not null,
```
Alternatively, assert non-null at the query level (`tempo_bpm_min as "tempo_bpm_min!"`, etc.) if the columns must stay nullable. Do not silently make the struct fields `Option` — downstream output/formatting assumes concrete values.

## Warnings

### WR-01: `tonal_balance` jsonb cross-language shape is an unverified contract — array vs object will break the read

**File:** `crates/nameless-adapters/src/reference_store_pg.rs:180`; `migrations/0003_reference_tracks.sql:74`; `workers/src/nameless_workers/pure/reference_summary.py:23`
**Issue:** The Rust read does `serde_json::from_str::<TonalBalance>(&r.tonal_balance)`, where `TonalBalance` is a struct with **named keys** (`low`, `low_mid`, `mid`, `high_mid`, `high`). The Python `TonalBalance` model dumps to that object shape — *but* a sibling code path, `summary_to_compact_dict`, represents the same data as a **bands array** (`[round(b,3) for b in summary.tonal_balance.bands()]`). The Python module that writes `reference_context` to Postgres is not part of this phase, so the persisted jsonb shape is unverified. If that writer reuses the array representation, `get_context_summary` fails at runtime with a deserialization error.
**Fix:** Pin the contract: the analyzer's PG writer must persist `non_melodic.tonal_balance.model_dump()` (the named-key object), never the bands list. Add a Rust round-trip test that deserializes the exact jsonb the writer emits, and a Python test asserting the persisted shape. **[env-gated — needs the Python PG writer + live DB to confirm end to end]**

### WR-02: `reference_context.created_at_ms` is `NOT NULL` but the analyzer's `ReferenceContext` carries no timestamp

**File:** `migrations/0003_reference_tracks.sql:82`; `workers/src/nameless_workers/domain/reference.py:97-112`
**Issue:** The schema requires `created_at_ms bigint not null`, but the Python `ReferenceContext` model (the analyzer's output type) has only `reference_track_id`, `style_embedding`, `non_melodic`, `vibe_description`, `analyzer_version` — no timestamp field. Any insert of an analyzer result therefore must source `created_at_ms` from outside the model, or the insert violates the `NOT NULL` constraint. The writer isn't in this phase, so this is a latent integration gap rather than a confirmed crash.
**Fix:** Either add a `created_at_ms` (default via `now_ms()` equivalent) to the persistence layer's insert explicitly, or give the column a `default (extract(epoch from now())*1000)::bigint` so the writer cannot forget it.

### WR-03: `ClaudeVibeDescriber.describe` silently returns `""` on refusal/empty response; no timeout or error handling

**File:** `workers/src/nameless_workers/adapters/vibe_describer_claude.py:64-86`
**Issue:** `describe` makes a network call with no try/except, no explicit timeout, and no `stop_reason` check. The result is built as `parts = [block.text for block in response.content if block.type == "text"]`. If the model refuses for safety reasons (`stop_reason == "refusal"`, empty/altered `content`) or returns only thinking blocks, `parts` is empty and the method returns `""`. That empty string then flows into `ReferenceContext(vibe_description="")` and is persisted — a silent quality degradation rather than a loud failure or retry. (Network exceptions do propagate and fail the job loudly, which is acceptable; the refusal/empty path is the gap.)
**Fix:** After `messages.create`, check `response.stop_reason`; on `"refusal"` or an empty text result, raise (so the job queue retries / dead-letters) or fall back to a deterministic description, rather than persisting `""`. Consider a per-call `timeout` override for the worker context.

## Info

### IN-01: `project_reference_context.attached_at_ms` is a permanently-zero dead column

**File:** `migrations/0003_reference_tracks.sql:93`; `crates/nameless-adapters/src/reference_store_pg.rs:207-217`
**Issue:** The column defaults to `0` and the Rust `attach` insert never sets it; `ProjectReference` (and the in-mem/file stores) don't carry it either. Every row is `attached_at_ms = 0` — the field records nothing.
**Fix:** Either populate it on insert (`now_ms()`) and surface it on `ProjectReference`, or drop the column.

### IN-02: `stereo_width` docs overstate the achievable range

**File:** `workers/src/nameless_workers/pure/stereo_width.py:11-14,38-49`; `workers/src/nameless_workers/domain/reference.py:88`
**Issue:** The docstrings say hard-panned/decorrelated → "→1 = very wide", but `side_energy / (mid_energy + side_energy)` saturates at **0.5** for fully-decorrelated equal-power L/R; only true anti-phase (`R = -L`) reaches 1.0. The math is a legitimate, scale-invariant width metric and stays within the model's `[0,1]` bound — only the prose is misleading.
**Fix:** Reword the doc to "0 = mono, ~0.5 = fully decorrelated, →1 = anti-phase," or normalize the metric if a 0–1 "very wide" reading is actually wanted.

### IN-03: `FakeReferenceAnalyzer` LUFS comment is off by one

**File:** `workers/src/nameless_workers/adapters/reference_analyzer_fake.py:64`
**Issue:** `lufs = round(float(-14.0 + (seed % 8)), 2)` yields `[-14, -7]`, but the inline comment claims `[-14, -6]`. Cosmetic; the value is musically sane either way.
**Fix:** Update the comment to `[-14, -7]` (or use `seed % 9` for the stated range).

### IN-04: Structural non-cloning proof (`compile_fail` doctest) is unverified in this build

**File:** `crates/nameless-core/src/conditioning.rs:62-68`; `crates/nameless-core/src/reference.rs:342-386`
**Issue:** The headline guarantee that `ReferenceTrack` *cannot* enter `gather_melodic_conditioning` is asserted by a `compile_fail` doctest, and the "no melodic field" tripwires are unit tests — none were compiled or run in this course build (Rust is code-complete but never built here). A `compile_fail` block that actually *compiles* (e.g. if someone later adds a `From<ReferenceTrack> for Fragment`) would pass the doctest as a false negative is impossible, but a `compile_fail` that fails to *build the test harness for unrelated reasons* can mask regressions. The guarantee is read-sound today; it is not machine-verified here.
**Fix (env-gated):** Before relying on the barrier, run `cargo test -p nameless-core --doc` and `cargo test -p nameless-core` on real hardware to confirm the doctest genuinely fails to compile and the tripwire tests pass.

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
