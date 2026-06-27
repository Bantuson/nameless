# Build & Verification Environment

**Recorded:** 2026-06-26 (autonomous run)

This file is authoritative for HOW phases are built and verified on this machine. Every phase's discuss / plan / execute / verify must respect it. It does NOT change WHAT the project is — only the local verification strategy.

> **Build mode (supersedes "verify by running"): course / learning project — code-complete, NOT run here.** See `.planning/ENGINEERING-PRINCIPLES.md` (canonical). Deliver complete, real, end-to-end code for every phase (incl. Rust + ML) even though this 4GB/no-Docker/no-Rust machine won't compile or run it. Do NOT gate progress on compiling/running/installing. "Verify" = code review + completeness + traceability + **tests that EXIST** (written, not executed here). Testability is law (DI/ports-and-adapters, pure functions, separation of concerns, loose coupling). ML phases ship `LEARNING.md`. The table below still defines which heavy leaves get test-doubles vs. real adapters; "Verify here (RAM-safe)" now means "tests written against the fake," not "tests executed."

## Dev machine ground truth

- **OS:** Windows 11 — PowerShell (primary) + Git Bash available.
- **RAM:** ~4GB available → **Docker is UNUSABLE**; heavy ML stacks (torch + model weights) and large Rust dependency compiles risk OOM / thrash.
- **Toolchains present:** Node v22, npm v10, Python 3.12 + pip, git.
- **Absent / unusable:** `cargo`/`rustc` (absent), `psql` (absent), Docker (installed but unusable on 4GB).

## Execution & verification policy

Build real, reviewed, idiomatic code for every phase per the PRD architecture. Verify only with RAM-safe methods. **Nothing is reported "verified" unless it actually ran here.** Each env-gated item must be listed with the exact command the user runs in their real environment.

| Layer | Build here | Verify here (RAM-safe) | Env-gated (flag for user) |
|-------|-----------|------------------------|---------------------------|
| **Rust control plane** (axum/sqlx/state machine) | Yes — real code | Small units via `cargo check`/`cargo test` **only if** the toolchain installs and compiles within RAM; pure-logic unit tests | Full `axum`+`sqlx` compile + integration run if it OOMs on 4GB |
| **Postgres + pgvector** | Yes — real DDL + sqlx/pgvector code | Schema + state-machine + queue logic against **SQLite / in-memory** | Live Postgres server (`docker`/managed PG) integration |
| **Audio ML** (librosa/torchcrepe/Demucs/CLAP/faster-whisper) | Yes — real worker code behind interfaces | Pipeline plumbing with **deterministic stubs + small fixtures** | Real models/weights + GPU/CPU inference (needs RAM/GPU) |
| **Ingestion** (yt-dlp/youtube-transcript-api) | Yes — real fetch/snapshot code | Parsing/snapshot/extractability logic against **fixture transcripts** | Live YouTube ingest @100+ videos (network + ToS) |
| **Object storage** (S3/R2) | Yes — real client code behind interface | A local filesystem fake implementing the same interface | Real S3/R2 (needs credentials) |
| **Frontend** (TS/React) | Yes — real app | `tsc` typecheck + light component/unit tests (Node OK on 4GB) | Full e2e against live backend |

## Implication for the architecture (good news)

The PRD already isolates the heavy parts behind interfaces (worker-job interface for generation/separation; object storage addressed by ID; capability layer as Skill+CLI). That makes the stub/fake substitution clean and honest: the production implementation and the test fake satisfy the same trait/interface, so local verification exercises the real control flow — only the heavy leaf is swapped.
