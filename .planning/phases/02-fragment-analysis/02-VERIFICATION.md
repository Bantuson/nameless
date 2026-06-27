---
phase: 2
phase_name: Fragment Analysis
status: passed
verified_by: tests-run (RAM-safe fakes suite) + review (course-project mode)
date: 2026-06-27
---

# Phase 2 Verification — Fragment Analysis

**Mode:** Course-project. The RAM-safe layer was **actually executed** here; the heavy ML/DB leaf is env-gated.

## Executed here (independently re-run by orchestrator)
`cd workers && python -m pytest -q` → **58 passed in 0.97s** (Python 3.12, pydantic 2.11 / numpy 2.2 / pytest 8.3). Covers: `AnalyzeJobConsumer` orchestration, the **480-triple state-mirror matrix** (matches the Rust canonical rules), Krumhansl-Schmuckler key-from-chroma, vector cosine/ranking, in-memory repo search, runner, model/job-envelope contracts. Confirmed real adapters import with **zero heavy deps** (lazy-import testability holds).

## Success criteria
| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Feature worker extracts f0/chroma/onsets/beat/tempo/key/LUFS → `analyzed` | ✅ reviewed-complete (real impl) | `LibrosaFeatureExtractor` (torchcrepe/librosa/pyloudnorm); consumer advances Captured→Analyzing→Analyzed |
| 2 | CLI shows key/tempo, never raw arrays | ✅ executed (fake path) | `cli.py` compact output; arrays kept in `fragment_features` |
| 3 | CLAP audio + note-text embeddings indexed in pgvector | ✅ reviewed-complete | `ClapEmbedder` (audio+text one space); `0002_fragment_features.sql` vector(512) + HNSW |
| 4 | Retrieve by note text or audio similarity, ranked | ✅ executed (fake) / reviewed (pg) | `InMemoryFragmentRepo.search` (tested) + `PgFragmentRepo.search` (`<=>` cosine) |

## Requirement coverage
CAP-03 ✅ (all features, real impl) · CAP-04 ✅ (CLAP joint embeddings + pgvector retrieval)

## Testability law — satisfied
✅ ports (AudioLoader/FeatureExtractor/Embedder/FragmentRepo) × real+fake · ✅ pure functions (key, vectors) · ✅ SoC (domain/pure/adapters/consumer) · ✅ loose coupling (Protocols, lazy heavy imports) · ✅ tests RUN (58).

## Learning artifact
`workers/LEARNING.md` — reviewed: genuinely educational (CREPE/octave-error, CQT vs FFT, onsets/beat/tempo, K-S key, LUFS/BS.1770, CLAP, pgvector ANN) with correct math + product tie-in.

## Env-gated (user runs in a real environment)
`cd workers && uv sync --extra ml --extra pg` · `psql "$DATABASE_URL" -f migrations/0002_fragment_features.sql` · `DATABASE_URL=… NAMELESS_OBJECT_ROOT=… uv run nameless-workers analyze --fragment <id>` · `… fragments search --note/--similar-to`. Verify pinned PyPI pkgs + CLAP checkpoint first (workers/README "Supply chain").

**PASS** — RAM-safe layer executed (58 tests), heavy leaf reviewed-complete + env-gated.
