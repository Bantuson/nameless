# Phase 8 — Stem Library + Attributed Sampling — SUMMARY

**Built:** 2026-06-28 · **Mode:** course/learning (code-complete; Rust review-only, Python tests run).

Two-language slice: the Rust control plane gains the stem-library + attribution schema, the **typed
attribution-completeness invariant**, rights-status, the CLI, and the credits sheet; the Python worker
plane gains the Demucs `StemSeparator` (lazy real + deterministic fake) and the content-addressed
separation orchestration.

---

## Requirement coverage

| Req | What | Where |
|---|---|---|
| **SAMP-01** | Demucs stems retained + browsable, with separator model/version provenance | Py `domain/separation.py`, `separation_ports.py`, `adapters/stem_separator_{demucs,fake}.py`, `adapters/stem_store_mem.py`, `pure/separation.py`, `separation_consumer.py`; Rust `stems.rs`, `StemStore`, `stems` table; CLI `stems separate` / `stems list` |
| **SAMP-02** | Promote a stem → `sampled` fragment anytime, human lifecycle (never the eval gate) | Rust `Fragment::new_sampled` (provenance `Sampled`, state `Captured`); CLI `sample add` enqueues `FeatureExtract` (human analysis path); `provenance::travels_human_path` unchanged |
| **SAMP-03** | Attribution-completeness HARD gate — incomplete placement unrepresentable | Rust `attribution.rs` (`PartialAttribution` vs `CompleteAttribution`, `into_complete`), `state_machine.rs::place` (+ `Fragment::place`, `apply` refuses sampled `Place`), `PlaceError` |
| **SAMP-04** | `rights_status` enum + "attribution ≠ permission" surfaced in-context | Rust `RightsStatus` (+ `note()`); `credits_sheet` notice; `sample show` notice; migration `rights_status` enum; LEARNING §11c |
| **SAMP-05** | Credits sheet generator | Rust pure `credits_sheet(project_title, rows)`; CLI `credits <project>` |

---

## File map

### Rust (`crates/`, review-only — written, not compiled here)

**New**
- `crates/nameless-core/src/stems.rs` — `StemId`, `StemType` (vocals/drums/bass/other/piano/guitar), `Stem` index row. +4 tests.
- `crates/nameless-core/src/attribution.rs` — `RightsStatus`, `AttributionField`, `IncompleteAttribution`, `PartialAttribution` (+ `missing_fields`/`is_complete`/`into_complete`), `CompleteAttribution`, `SampleAttribution`, pure `credits_sheet`. +7 tests.
- `crates/nameless-adapters/src/sample_store_mem.rs` — `InMemorySampleStore` (both ports). +2 tests.
- `crates/nameless-adapters/src/sample_store_file.rs` — `FileSampleStore` (`--local`, both ports). +2 tests.
- `crates/nameless-adapters/src/sample_store_pg.rs` — `PostgresSampleStore` (postgres feature). +1 ignored live-DB test.
- `migrations/0004_sampling.sql` — `rights_status` enum, `stems`, `sample_attribution` (all credited columns `NOT NULL` + positive-span check), idempotency `unique`.

**Modified**
- `state_machine.rs` — `PlaceError`, free `place(...)` gate, `Fragment::place`, `apply` refuses sampled `Place`. +4 tests (incl. the no-bypass proof).
- `ports.rs` — `StemStore`, `AttributionStore`, `SampleStore` supertrait + blanket impl.
- `fragment.rs` — `Fragment::new_sampled`. +1 test.
- `job.rs` — `JobEnvelope::SeparateTrack { reference_track_id }`. +1 round-trip test.
- `lib.rs`, `adapters/lib.rs` — module registration + re-exports.
- `nameless-cli/src/cli.rs` — `stems` / `sample` / `credits` command tree, `do_stems_separate`, `do_sample_add`, `parse_time_range`, `parse_stem_id`, `RightsArg`. +8 tests.
- `nameless-cli/src/output.rs` — `print_stem_list`, `print_stems_separate`, `print_sample_added`, `print_sample_show`, `print_credits`.
- `nameless-cli/src/profile.rs` (Plane gains `samples`), `nameless-cli/src/error.rs` (`IncompleteAttribution`).

### Python (`workers/`, tests RUN)

**New**
- `domain/separation.py` — `StemType`, `SeparatedStem`, `SeparationResult`, `StemRecord` (mirror Rust).
- `separation_ports.py` — `TrackLoader`, `StemSeparator`, `StemBlobStore`, `StemRecordStore` Protocols.
- `pure/separation.py` — `content_hash`, `build_stem_records` (pure).
- `adapters/stem_separator_demucs.py` — `DemucsStemSeparator` (lazy; htdemucs_ft / _6s; NOT run).
- `adapters/stem_separator_fake.py` — `FakeStemSeparator` (deterministic, 4- or 6-stem).
- `adapters/stem_store_mem.py` — `InMemoryStemBlobStore`, `InMemoryStemRecordStore`.
- `adapters/track_loader_fake.py` — `InMemoryTrackLoader`; `adapters/track_loader_store.py` — `StoreTrackLoader` (real, composition).
- `separation_consumer.py` — `SeparationJobConsumer` + `SeparationOutcome`.
- `tests/test_separation.py`, `tests/test_stem_separator_fake.py`, `tests/test_separation_consumer.py` (13 tests).

**Modified**
- `domain/models.py` — `SeparateTrackJob` added to the `JobEnvelope` union.
- `adapters/__init__.py` — export the Phase-8 fakes.
- `LEARNING.md` (§11c), `README.md` (Phase-8 section + verification).

---

## The attribution-completeness invariant (SAMP-03), explained

The integrity boundary mirrors the eval gate — *the harness gates; the agent explores* — applied to
attribution:

- **`PartialAttribution`** has every field `Option<…>` (what the CLI gathers from the stem + flags).
- **`CompleteAttribution`** has every field **non-`Option`**, so it *cannot represent* a missing field.
  The only path from user input to one is `PartialAttribution::into_complete()`, which validates and
  returns the typed list of what is missing (a whitespace-only artist is missing; an inverted/zero
  time-range is missing). `derive(Deserialize)` is safe because a JSON object missing any field fails
  to deserialize — completeness survives the serde boundary.
- The **placement gate** `state_machine::place(provenance, from, Option<&CompleteAttribution>)` requires
  `Some(&CompleteAttribution)` for `Sampled` provenance (the *gate*, not the caller, decides this from
  provenance, so passing `None` is a hard `PlaceError::AttributionRequired`). And `Fragment::apply(Place)`
  is **refused** for `Sampled` — so there is no ungated path that writes `Placed` onto a sample.
- **No bypass.** Rust tests prove: a sampled fragment with partial attribution cannot be placed (via
  `apply` *or* `place(None)`); with a `CompleteAttribution` it can; and the only door is
  `place(Some(&complete))`. The DB mirrors this — every credited `sample_attribution` column is `NOT
  NULL` with a positive-span `check`. Type + schema agree.

`sampled` still travels the human lifecycle (Captured→Analyzing→Analyzed→Placed), never the AI eval
gate — a sample *is* source audio; the attribution gate is layered specifically on its `Analyzed →
Placed` edge.

---

## Example credits sheet (`nameless credits <project>`)

```markdown
# Credits — Late Night Tape

> **Attribution is not permission.** Sampling a copyrighted recording is infringement regardless of
> personal or portfolio intent; crediting a source does not make using it legal. Clear every
> `copyrighted_uncleared` / `unknown` sample before publishing output that contains it.

2 sampled fragments in this project:

1. **Trust** — Brent Faiyaz
   - stem: `vocals`  ·  range: 12000–18000 ms (6000 ms)
   - rights: `copyrighted_uncleared` — copyrighted, NOT cleared — do not publish output containing this sample
2. **Wasting Time** — Brent Faiyaz
   - stem: `piano`  ·  range: 12000–18000 ms (6000 ms)
   - rights: `own_work` — the producer's own recording
```

---

## Verification

### Python — tests RUN here (RAM-safe, fakes only)

```
cd workers && python -m pytest -q
→ 115 passed   (102 prior + 13 new Phase-8)
```

The 13 new tests cover: `content_hash` (sha256-hex, matches the Rust object-store key layout),
`build_stem_records` (naming, content-hash uris, model/version provenance, 6-stem variant), the fake
separator (deterministic, distinct stems, 6s piano/guitar), the `SeparationJobConsumer` (stems retained
in the blob store, records written with provenance, **idempotency** — a redelivered job retains nothing
new and writes no duplicate rows, the `skipped` flag, track-not-found), the compact outcome (no audio),
and the `SeparateTrack` job round-trip against the exact Rust JSON shape.

### Rust — review-only (no toolchain on this box; written + reviewed, NOT compiled)

Env-gated commands the user runs on a real dev machine:

```
# Core domain + state machine + CLI (lean default build — no Postgres):
cargo test -p nameless-core        # incl. attribution completeness, the no-bypass placement proof,
                                   #      credits sheet, rights-status, stems, new_sampled
cargo test -p nameless-adapters    # incl. InMemory/File sample store round-trips
cargo test -p nameless-cli         # incl. sample add (complete + incomplete-rejected), stems separate,
                                   #      time-range parsing, credits enumeration

# Heavy leaf (Postgres adapter + migrations) — real DB required:
DATABASE_URL=postgres://… cargo sqlx migrate run                 # applies 0004_sampling.sql
cargo test -p nameless-adapters --features postgres -- --ignored # live PostgresSampleStore round-trip
```

~30 Rust tests were written across the new/modified files (stems 4, attribution 7, state-machine gate 4,
fragment 1, job 1, mem store 2, file store 2, pg 1 ignored, cli 8). They are complete and reviewed; they
are **not** compiled here (no `cargo`/`rustc` on the 4 GB box).

### Demucs — env-gated (NOT run here)

The real `DemucsStemSeparator` needs `demucs` + `torch` + `torchaudio` (GPU wanted). Importing the
adapter is free (heavy imports are lazy, verified). The exact env-gated wiring is in `workers/README.md`
(Phase-8 section): `nameless stems separate <track>` → `SeparateTrack` job → `SeparationJobConsumer`
with `DemucsStemSeparator("htdemucs_ft")` → retain by content-hash → write `stems` rows.

### Honest status

- **Rust:** complete, idiomatic, reviewed — **not compiled** (no toolchain).
- **Python (fakes/pure/orchestration):** complete and **tests run green (115)**.
- **Demucs / Postgres:** complete real adapters, **env-gated, not run** here.
