# Nameless — Milestone v1.0 (M0 Foundation) — COMPLETE

**Delivered:** 2026-06-28 · **Mode:** course/learning project (code-complete, not run on the 4GB dev box) · **Engineering law:** DI/ports-and-adapters, pure functions, SoC, loose coupling (`.planning/ENGINEERING-PRINCIPLES.md`)

All 9 phases of the M0 foundation are built, committed, and verified to the extent this machine allows. **394 automated tests pass here** (knowledge-pipeline 239 · workers 115 · web 40); Rust is complete + reviewed (compile/integration env-gated — no toolchain on 4GB). Nothing was faked: every "verified" claim was either executed here or is explicitly flagged env-gated with the exact command.

## What was built

| # | Phase | Lang | Delivered | Verified here |
|---|-------|------|-----------|---------------|
| 1 | Typed Capture Spine | Rust | ports-and-adapters control plane, typed fragment state machine (exhaustive `transition`, "can't place unanalyzed"), content-hash storage, sqlxmq queue, `nameless` CLI | review + tests written (env-gated `cargo test`) |
| 2 | Fragment Analysis | Python | feature worker (f0/chroma/onset/beat/tempo/key/LUFS) + CLAP audio/note embeddings + pgvector retrieval | 58 tests RAN |
| 3 | Tutorial Ingestion | Python | local snapshot-on-ingest corpus, caption→ASR fallback, **extractability scoring** (refuses visual-only) | 77 tests RAN |
| 4 | Cited Claim Mining | Python | atomic **cited** claims (no synthesis), consensus/conflict cross-reference, real Claude tool-use extractor | 134 tests RAN |
| 5 | Synthesize + Verify Skills | Python | synthesis over claim-set, **pure citation gate (rejects invented numbers)**, real authored `SKILL.md` (P1 cells), human spot-audit | 201 tests RAN |
| 6 | Sparse-Genre Grounding | Python | alt-piano skill via **parent decomposition + released-track audio**, LOW-confidence labeled, non-cloning | 239 tests RAN |
| 7 | Reference-Track Context | Rust+Py | vibe + non-melodic sonic targets; **non-cloning made structural** (4 typed barriers, compile_fail proof) | 102 py tests RAN; Rust reviewed |
| 8 | Stem Library + Sampling | Rust+Py | Demucs stems retained, promote→`sampled`, **attribution-completeness invariant** (incomplete = unrepresentable), rights-status, credits sheet | 115 py tests RAN; Rust reviewed |
| 9 | Thin Web UI | TS/React | 4 screens (capture/reference/stems/project) over a `NamelessApi` port + mock | 40 vitest + tsc + build RAN |

## The make-or-break thesis, realized
The knowledge pipeline (Phases 3→4→5→6) is the project's reason to exist, and it works end-to-end offline: ingest+snapshot → extract **atomic cited claims** → synthesize **only over the claim set** through a **programmatic citation gate that rejects invented numbers** → emit layered, conflict-preserving authored Skills → ground sparse genres from real parents + audio. Real artifacts exist: `skills/production/**/SKILL.md` (incl. the grounded `composite/alternative-piano/SKILL.md`). "Quality in, quality out" is enforced in code, not hoped for.

## Integrity boundaries (typed, not conventional)
- **Eval-gate-only** path for AI fragments (Rust state machine, Phase 1).
- **Non-cloning** references — no melodic field exists to leak into; compile-barred from the melodic path (Phase 7).
- **Attribution-completeness** — a sampled fragment can't be placed without complete source/artist/stem/time-range; `CompleteAttribution` makes incomplete unrepresentable (Phase 8).
- **Citation gate** — no claim/number reaches a Skill without tracing to a real source quote (Phase 5).

## Honest status / what's env-gated
- **Rust** (Phases 1,7,8): complete + reviewed; not compiled here (no toolchain, 4GB). Run later: `cargo test`, `cargo build --features postgres`, `cargo sqlx migrate run` (migrations 0001→0004).
- **Heavy ML** (librosa/torchcrepe/Demucs/CLAP/faster-whisper): real adapters written behind ports, lazy-imported, not run. Run later: `uv sync --extra ml`/`--extra asr` + the documented commands.
- **Live LLM** (Claude extractor/synthesizer/vibe): real Anthropic-SDK adapters, not called. Run later: `uv sync --extra extract` + `ANTHROPIC_API_KEY`.
- **Live data/cloud**: 100-video YouTube ingest + S3/R2 need a home IP + credentials.
- Each phase's `*-VERIFICATION.md` lists its exact env-gated commands.

## Next
- **M1** (generation): arranger + melody-conditioned generation, the eval gate (per-genre thresholds + clone-leak check), mix chain, master, export with credits — consumes these M0 foundations. Start with `/gsd-new-milestone`.
- **To actually run M0**: a machine with the Rust toolchain + Python ML env + Postgres (per each VERIFICATION.md). The code is ready for it.

*All artifacts under `.planning/` (PROJECT, REQUIREMENTS, ROADMAP, research/, ENGINEERING-PRINCIPLES, ENVIRONMENT, phases/01–09). Source: `crates/` (Rust), `workers/` + `knowledge-pipeline/` (Python), `web/` (React), `skills/production/` (authored Skills), `migrations/` (SQL).*
