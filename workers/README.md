# `workers/` — Nameless Python worker plane

The audio-ML half of Nameless (PRD §4–5). **Phase 2** delivers *fragment analysis*: take a captured
fragment to `analyzed` by computing audio features + joint CLAP embeddings, persist them, advance the
typed lifecycle, and make fragments retrievable by note text or audio similarity (pgvector).

- Requirements covered: **CAP-03** (f0, chroma, onsets/beat-grid/tempo, key, LUFS) and **CAP-04**
  (CLAP audio + note-text embeddings indexed in pgvector for retrieval).
- The DSP/ML is explained in depth in **[`LEARNING.md`](./LEARNING.md)**.

## Design: ports & adapters (why the tests need no ML or DB)

Every heavy/external dependency sits behind a `typing.Protocol` **port** with a REAL adapter and a
deterministic **FAKE**. The orchestration (`AnalyzeJobConsumer`) is pure over those ports.

| Port (`ports.py`) | Real adapter | Fake adapter |
|---|---|---|
| `AudioLoader` | `FilesystemAudioLoader` / `S3AudioLoader` (`adapters/audio_loader_store.py`) | `InMemoryAudioLoader` |
| `FeatureExtractor` | `LibrosaFeatureExtractor` (librosa + torchcrepe + pyloudnorm) | `FakeFeatureExtractor` |
| `Embedder` | `ClapEmbedder` (LAION-CLAP `larger_clap_music`) | `FakeEmbedder` (hash-seeded) |
| `FragmentRepo` / FeatureStore | `PgFragmentRepo` (psycopg + pgvector) | `InMemoryFragmentRepo` (numpy cosine) |
| `JobSource` | Rust sqlxmq runner → `analyze`, or a SKIP-LOCKED poller | `InMemoryJobSource` |

The real adapters import their heavy libraries **lazily inside methods**, so importing the package (and
running the whole test suite) needs only `pydantic` + `numpy`. That is what makes verification honest on
a 4 GB / no-Docker box: the production impl and the fake satisfy the same protocol, so a test against the
fake exercises the real control flow with only the heavy leaf swapped.

```
src/nameless_workers/
  domain/        models.py (pydantic: AudioFeatures, Embedding, FeatureExtractJob, FragmentRecord, SearchHit)
                 provenance.py · state.py   ← mirror of the canonical Rust enums + transition() rules
  pure/          key.py (Krumhansl-Schmuckler) · vectors.py (normalize/cosine/rank)   ← pure, no I/O
  ports.py       AudioLoader · FeatureExtractor · Embedder · FragmentRepo · JobSource
  adapters/      *_fake.py / repo_mem.py / job_source_mem.py  (fakes, eager) +
                 feature_librosa.py · embed_clap.py · repo_pg.py · audio_loader_store.py (real, lazy)
  consumer.py    AnalyzeJobConsumer — load → extract → embed → persist → advance (idempotent)
  runner.py      run_once / run_forever over a JobSource
  cli.py         `nameless-workers fragments search … | analyze … | run`
tests/           fakes-only pytest suite (state mirror, key, vectors, consumer, repo, runner, models)
```

## Build mode (course/learning project) — code-complete, NOT run on the build box

This machine cannot install `torch`/`librosa`/`laion-clap`/Postgres. The code is complete and real; the
heavy paths are **env-gated** below. Nothing here was installed on the build box.

## Verification

### RAM-safe (the fakes — runnable anywhere with the light base)

```bash
cd workers
uv sync --extra dev          # installs only pydantic + numpy + pytest
uv run pytest -q             # 58 tests: state mirror (480-triple), key-from-chroma, vectors,
                             # orchestration, retrieval ranking, persistence contract, runner
```

(If not using uv: `pip install pydantic numpy pytest` then `PYTHONPATH=src pytest -q`.)

### Env-gated (real ML + real Postgres — NOT the 4 GB box)

```bash
# 1. Heavy deps (CPU is fine for features; GPU wanted for CLAP at volume):
uv sync --extra ml --extra pg

# 2. Apply the Phase-2 schema delta to the same Postgres the control plane uses:
psql "$DATABASE_URL" -f ../migrations/0002_fragment_features.sql
#    (or: DATABASE_URL=… cargo sqlx migrate run, from the repo root)

# 3. Analyze one captured fragment end-to-end (loads bytes by content hash, extracts features,
#    embeds, persists, advances Captured→Analyzing→Analyzed). This is the single-shot entrypoint
#    the Rust sqlxmq runner invokes per job:
export DATABASE_URL=postgres://…
export NAMELESS_OBJECT_ROOT=../.nameless-local/objects     # or wire S3AudioLoader for R2
uv run nameless-workers analyze --fragment <FRAGMENT_UUID>

# 4. Retrieve (compact output: id  key  tempo  score — never vectors):
uv run nameless-workers fragments search --note "the chorus-like ideas" --limit 5
uv run nameless-workers fragments search --similar-to <FRAGMENT_UUID> --field audio
uv run nameless-workers fragments search --note "spacious amapiano pad" --json
```

## Running the worker (the cross-language seam)

The control plane (Rust) owns the durable queue (`sqlxmq`); this Python plane consumes `FeatureExtract`
jobs. Two equivalent bindings satisfy the `JobSource` port — pick one when wiring M0→M1:

1. **Rust runner → Python single-shot (recommended).** The Phase-1 `feature_extract_job` sqlxmq handler
   (currently a no-op placeholder) shells out to `nameless-workers analyze --fragment <id>` per job, or
   calls it over a thin local socket. Durability, retry, and backpressure stay in sqlxmq (Phase 1); the
   Python side is a pure function of one fragment id. The `analyze` subcommand is built for exactly this.
2. **Python poller.** A `JobSource` that claims rows with `SELECT … FOR UPDATE SKIP LOCKED` and drives
   `run_forever`. Keep it behind the same port so swapping (1)↔(2) is a config change.

Either way the work runs **file-to-file**: audio is loaded by content-hash ID, features/embeddings are
written to Postgres, and only compact summaries (key/tempo/score) ever surface — the token strategy
holds across the language boundary.

## Supply chain

Versions in `pyproject.toml` are pinned to the STACK.md research picks (librosa 0.11.0, pyloudnorm 0.1.1,
laion-clap 1.1.7, torchcrepe, psycopg 3, pgvector). **Pin the CLAP checkpoint too** — its weights have
drifted historically (see `embed_clap.py`). Verify packages on PyPI before the first real `uv sync`.

## Licensing note

LAION-CLAP and librosa are permissive for personal/portfolio use; this worker plane does not bundle a
generator (that is M1). See the repo CLAUDE.md "License Constraints" before any commercial use.
