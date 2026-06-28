# Phase 7: Reference-Track Context — Summary

**Status:** Code-complete. Python tests RUN (102 passed). Rust written + reviewed (NOT compiled — no
toolchain on this box, per `.planning/ENGINEERING-PRINCIPLES.md`).

A producer uploads a finished song they love and gets its **vibe + measurable non-melodic sonic
targets** as project conditioning context — with cloning made **structurally impossible** (REF-03,
the headline). Two-language: the Rust control plane (entity + schema + typed non-cloning barrier +
CLI) and the Python worker plane (restricted non-melodic analysis reusing Phase-2 CLAP).

---

## File map

### Rust control plane (`crates/`, review-only)

**New (`nameless-core`):**
- `src/reference.rs` — `ReferenceTrackId`, `ReferenceTrack` (separate type from `Fragment`),
  `ReferenceContext` (non-melodic ONLY — no melody/chroma/f0/chord/structure/key column),
  `ReferenceContextSummary` (compact, array-free — drops the embedding to a dim), `TonalBalance`,
  `ReferenceRole`, `ProjectReference`. + unit tests (role round-trip, summary drops vector, "carries
  no melodic field" tripwire).
- `src/conditioning.rs` — `MelodicConditioning` + `gather_melodic_conditioning(&[Fragment])` (the
  type-level non-cloning barrier, with a `compile_fail` doctest proving a `ReferenceTrack` cannot be
  passed) and `ReferenceConditioning::from_context` (non-melodic bundle; drops vibe prose). + tests.

**Edited (`nameless-core`):**
- `src/lib.rs` — module decls + flat re-exports (`ReferenceTrack`, `ReferenceContext`, …,
  `gather_melodic_conditioning`, `ReferenceStore`).
- `src/ports.rs` — `ReferenceStore` trait (insert/get/list tracks, `get_context_summary`, `attach`,
  `list_project_references`).
- `src/job.rs` — `JobEnvelope::AnalyzeReference { reference_track_id }` variant + JSON round-trip test.

**New (`nameless-adapters`):**
- `src/reference_store_mem.rs` — `InMemoryReferenceStore` (fake; `set_context` test seam) + tests.
- `src/reference_store_file.rs` — `FileReferenceStore` (`--local` JSON persistence) + tests.
- `src/reference_store_pg.rs` — `PostgresReferenceStore` (behind `postgres` feature; reads
  `vector_dims(...)` never the vector; ignored live-DB test).

**Edited (`nameless-adapters` / `nameless-cli`):**
- `nameless-adapters/src/lib.rs` — module decls + re-exports (incl. `#[cfg(feature="postgres")]`).
- `nameless-cli/src/cli.rs` — `reference upload|show|attach` subcommands + `do_reference_upload` +
  `RoleArg` + parsing/behavior tests.
- `nameless-cli/src/profile.rs` — `references` added to `Plane`; wired `--local`
  (`FileReferenceStore`) + server (`PostgresReferenceStore`).
- `nameless-cli/src/output.rs` — `print_reference_uploaded/show/attached` (compact; the style vector
  is never printed — only its dimension).

**New (migration):**
- `migrations/0003_reference_tracks.sql` — `reference_role` enum; `reference_tracks`;
  `reference_context` (`vector(512)` style embedding + non-melodic columns, **no melodic column**);
  `project_reference_context` link.

### Python worker plane (`workers/`, tests RUN)

**New domain/ports:**
- `src/nameless_workers/domain/reference.py` — `TonalBalance`, `NonMelodicFeatures` (sealed
  `extra="forbid"` — a melody can't be constructed in), `ReferenceContext`, `ReferenceContextSummary`,
  `FORBIDDEN_MELODIC_FIELDS`.
- `src/nameless_workers/reference_ports.py` — `ReferenceAnalyzer`, `VibeDescriber`, `GenreTagger`
  protocols + `GenreTag`.

**New pure modules:**
- `pure/tonal_balance.py` (band RMS ratios), `pure/stereo_width.py` (mid/side + correlation),
  `pure/non_melodic.py` (the restricted-feature invariant: `assert_non_melodic` / `is_non_melodic`),
  `pure/reference_summary.py` (compact, array-free formatting).

**New adapters:**
- `adapters/reference_analyzer_fake.py` — `FakeReferenceAnalyzer` (deterministic, composition-shaped).
- `adapters/reference_analyzer_clap.py` — `RestrictedReferenceAnalyzer` (real, lazy librosa STFT +
  pyloudnorm + CLAP; **never** chroma/f0).
- `adapters/vibe_describer_fake.py` / `vibe_describer_claude.py` — `FakeVibeDescriber` /
  `ClaudeVibeDescriber` (lazy `anthropic`, `claude-opus-4-8`, adaptive thinking, `effort:"low"`).
- `adapters/genre_tagger.py` — `ClapZeroShotGenreTagger` (reuses the CLAP Embedder) + `FakeGenreTagger`.

**Edited:**
- `domain/models.py` — `AnalyzeReferenceJob` added to the `JobEnvelope` discriminated union.
- `adapters/__init__.py` — export the Phase-7 fakes.

**New tests (44, all run + pass):** `test_tonal_balance.py`, `test_stereo_width.py`,
`test_non_melodic.py`, `test_reference_summary.py`, `test_genre_tagger.py`, `test_vibe_describer.py`,
`test_reference_analyzer.py`, `test_reference_models.py`.

**Docs:** `workers/LEARNING.md` §11b (the structural non-cloning teaching section) + references;
`workers/README.md` (Phase-7 layer + verification); root `README.md` (reference CLI + REF coverage).

---

## Requirement coverage

| Req | What | Where |
|-----|------|-------|
| **REF-01** | Upload + persist a reference by ID (content-hash audio) | `cli::do_reference_upload` (store by `content_hash` via `ObjectStore`), `ReferenceTrack::new_upload`, `ReferenceStore` (mem/file/pg), `reference_tracks` table |
| **REF-02** | Non-melodic vibe + measurable targets + LLM vibe description | Python `RestrictedReferenceAnalyzer` → `ReferenceContext` (CLAP style embedding + genre + tempo range + LUFS + tonal balance + stereo width + `ClaudeVibeDescriber` prose); Rust reads the compact summary |
| **REF-03** | **Structural** non-cloning | Rust: `ReferenceContext` has no melodic column; `gather_melodic_conditioning(&[Fragment])` compile-bars a `ReferenceTrack` (`compile_fail` doctest). Python: `NonMelodicFeatures` sealed `extra="forbid"`; `RestrictedReferenceAnalyzer` never computes f0/chroma; `assert_non_melodic` tripwire |
| **REF-04** | Attach a reference to a project as conditioning | `cli` `reference attach`, `ReferenceStore::attach`, `project_reference_context` link (idempotent upsert) |

---

## The structural non-cloning guarantee, explained (REF-03)

The hard line: *imitate the vibe* must never become *reproduce the song*. A melody-conditioned
generator follows whatever reaches its melodic input — so the leak is "one shared feature path + one
forgotten branch". Phase 7 closes it by **type**, in four mutually-reinforcing ways:

1. **Separate entity.** `ReferenceTrack` is a different type from `Fragment` — no provenance, no
   lifecycle state, no `kind`. It can never enter the state machine, so it is never placed/mixed/
   rendered into an arrangement.
2. **Compile-time barrier on the consuming side.** `gather_melodic_conditioning` accepts only
   `&[Fragment]`. A `ReferenceTrack` has no conversion into `Fragment`, so passing one does not
   type-check — proven by a `compile_fail` doctest (an executable proof, not a comment).
3. **No melodic field exists to leak into.** `ReferenceContext` (Rust) and `NonMelodicFeatures`
   (Python, sealed `extra="forbid"`) have no f0/chroma/melody/chord/structure/key field. Adding one
   is an explicit, reviewable schema + type change. What you cannot store, you cannot clone from.
4. **Restricted extraction.** The analyzer never calls `chroma_cqt`/`torchcrepe` (contrast the
   Phase-2 extractor, which does — for the producer's OWN fragments). It runs `assert_non_melodic`
   on its own output as a belt to the structural suspenders.

The asymmetry is *typed*, the same rigour the PRD applies to the eval gate.

---

## Verification

### Python — RUN here (RAM-safe, base env: pydantic + numpy + pytest)

```bash
cd workers && python -m pytest -q        # 102 passed (58 Phase-2 + 44 Phase-7)
```
Covered by the run: tonal-balance band math + normalization; stereo-width mid/side + correlation; the
non-melodic invariant (the type cannot be *constructed* with a melodic field; the tripwire fires on a
deliberately-leaky model and recurses into nested models); compact summary formatting (no vector
leaks); zero-shot genre ranking logic (via `FakeEmbedder`, plus margin/withhold + determinism); the
fake vibe describer (deterministic, mentions no melodic terms, numbers drive the prose); the analyzer
e2e on byte fixtures (complete non-melodic context, determinism, no melodic key in the dump, array-free
summary, composition with injected real logic); the `AnalyzeReference` job JSON round-trip + the
discriminated union; `ReferenceContext.summary()` drops the vector.

### Rust — REVIEWED (written, NOT compiled here — no `cargo`/`rustc`)

Complete idiomatic Rust mirroring the established Phase-1/2 patterns (ports + real + fake; typed
errors; heavy leaf behind the `postgres` feature; `#[cfg(test)]` units). The melodic barrier's
`compile_fail` doctest and the new unit tests are written to run under `cargo test` in a real env.

### Env-gated (NOT run here — exact commands for later)

- **Compile + run the Rust unit/doc tests** (incl. the `compile_fail` non-cloning proof):
  `cargo test` (lean) and `cargo test -p nameless-cli` — on a machine with the toolchain.
- **Postgres reference store** (sqlx compile-checked SQL + live round-trip), after applying
  migrations `0001`→`0003`:
  `cargo sqlx migrate run` then
  `DATABASE_URL=postgres://… cargo test -p nameless-adapters --features postgres -- --ignored`.
- **Real reference analysis** (CLAP + librosa + pyloudnorm): `uv sync --extra ml` then run the
  analyzer over a real upload (composes `RestrictedReferenceAnalyzer(ClapEmbedder(),
  ClapZeroShotGenreTagger(...), ClaudeVibeDescriber())`).
- **The LLM vibe call** (`ClaudeVibeDescriber`): `pip install anthropic` + `ANTHROPIC_API_KEY` — uses
  `claude-opus-4-8` with adaptive thinking. **NOT run here.**

Nothing above was compiled, installed, or called on this box.
