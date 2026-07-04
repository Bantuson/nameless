---
phase: quick-260704-em1
plan: 01
type: execute
subsystem: infra
tags: [devcontainer, codespaces, docker-compose, pgvector, postgres, sqlx, vite]
requires:
  - ".github/workflows/ci.yml (Postgres image/credentials/healthcheck mirrored exactly)"
  - "migrations/0001-0005 (applied by post-create; 0001/0003/0004/0005 verified non-idempotent)"
provides:
  - ".devcontainer/devcontainer.json — Codespaces entry point (rust stable / node 22 / python 3.12, forwardPorts [8080, 5173], post-create hook, 4 extensions)"
  - ".devcontainer/docker-compose.yml — app + db (pgvector/pgvector:pg16, nameless/nameless/nameless, pg_isready healthcheck, persisted volume)"
  - ".devcontainer/post-create.sh — apt deps + uv + pg_isready wait + marker-guarded migrations + npm ci"
  - "README.md 'Run in a Codespace' section with verified launch commands"
affects: []
tech-stack:
  added: [devcontainers, "ghcr.io/devcontainers/features (rust/node/python)"]
  patterns: ["per-file migration marker table for non-idempotent migrations against a persisted volume"]
key-files:
  created:
    - .devcontainer/devcontainer.json
    - .devcontainer/docker-compose.yml
    - .devcontainer/post-create.sh
  modified:
    - README.md
decisions:
  - "Marker-table migration guard (_devcontainer_migrations, per-file) instead of ci.yml's blind loop — CI gets a fresh DB every run; the Codespace volume persists and 0001/0003/0004/0005 are not re-runnable"
  - "uv installed in post-create.sh from the official Astral installer, keeping devcontainer features to the well-known ghcr.io/devcontainers/* namespace only"
  - "db port 5432 NOT published to the host — app reaches it over the compose network as host `db`; DATABASE_URL set once on the app service (no remoteEnv duplication)"
  - "No API bind change needed: Codespaces' forwarder runs inside the container, so the 127.0.0.1:8080 default is forwardable"
metrics:
  duration: "4 min"
  completed: "2026-07-04"
  tasks: 3
  files: 4
status: complete
---

# Quick Task 260704-em1: Add GitHub Codespaces Devcontainer Summary

Codespaces devcontainer (app + CI-identical pgvector Postgres via docker-compose) with an idempotent marker-guarded migration post-create and a README "Run in a Codespace" section whose every command traces to source.

## What was built

**Task 1 — `.devcontainer/docker-compose.yml` + `devcontainer.json`** (commit `08d7586`)
- `db` service mirrors ci.yml's `rust-postgres` service character-for-character: `pgvector/pgvector:pg16`, `POSTGRES_USER/PASSWORD/DB=nameless`, `pg_isready` health semantics (10s/5s/5). Data persisted in named volume `nameless-pgdata`; 5432 deliberately not published.
- `app` service: `mcr.microsoft.com/devcontainers/base:ubuntu`, repo mounted at `/workspaces/nameless`, `DATABASE_URL=postgres://nameless:nameless@db:5432/nameless` (compose hostname `db` — needed at runtime by the `--server` profile and at compile time by sqlx macros), `depends_on: db: service_healthy`.
- `devcontainer.json` is strict JSON (verified with `JSON.parse`): rust stable / node 22 / python 3.12 features (all `ghcr.io/devcontainers/*`), `forwardPorts [8080, 5173]` (8080 → `NAMELESS_API_ADDR` default in main.rs; 5173 → Vite default + `DEFAULT_CORS_ALLOW_ORIGIN` in lib.rs), labeled portsAttributes, `postCreateCommand`, and rust-analyzer/python/ruff/eslint extensions.

**Task 2 — `.devcontainer/post-create.sh`** (commit `73e2a85`)
- `set -euo pipefail`; apt installs `postgresql-client` + `ffmpeg`; uv via the Astral installer guarded on both `command -v uv` and `~/.local/bin/uv`.
- Waits for Postgres with `pg_isready -h db -p 5432 -U nameless` (30 attempts x 2s, loud failure).
- Migrations: creates `_devcontainer_migrations (filename pk, applied_at)`, then for each `migrations/*.sql` (glob = filename order, same as CI) skips if marked, else applies with `-v ON_ERROR_STOP=1` and inserts the marker. Header comment states the rationale (persisted volume vs CI's fresh DB; a single-table freshness check would break when a new migration lands). Re-running against a migrated volume applies zero migrations and fails nowhere.
- `npm ci --prefix web`, then a ready banner naming the two run commands.

**Task 3 — README "Run in a Codespace" section** (commit `c77848e`)
- Inserted between the postgres ENV-GATED section and "Supply chain" (~44 lines). Lean run `cargo run -p nameless-api`, postgres run `cargo run -p nameless-api --features postgres -- --server` (cross-references the existing sqlx compile-time NOTE), web run `VITE_NAMELESS_CLIENT=http npm run dev` with the `VITE_API_BASE_URL` default from createClient.ts.
- Browser-Codespace caveat: port 8080 visibility Public, `NAMELESS_CORS_ALLOW_ORIGIN=https://<codespace>-5173.app.github.dev`, `VITE_API_BASE_URL=https://<codespace>-8080.app.github.dev`.
- Ends with the italic env-gated closure line. `ci.yml` untouched (confirmed absent from `git diff --name-only`).

## Verification (structural — course mode, nothing executes on this machine)

| Check | Result |
|---|---|
| `node -e "JSON.parse(...)"` on devcontainer.json | PASS (strict JSON, no comments) |
| compose `db` vs ci.yml lines 54-65 (image + 3 POSTGRES_* + pg_isready 10s/5s/5) | identical |
| forwardPorts trace: 8080 → main.rs `NAMELESS_API_ADDR` default; 5173 → Vite default + lib.rs CORS default | PASS |
| `bash -n .devcontainer/post-create.sh` | PASS; marker guard wraps every `psql -f`; ON_ERROR_STOP=1 on all 5 psql invocations |
| README commands byte-traceable (bin name, feature flag, `--server`, VITE_* env vars) | PASS (per plan verified_facts) |
| `git status` — ci.yml unmodified | PASS |

## Env-gated closure (not run here)

Open the repo in a GitHub Codespace (Code → Codespaces → Create codespace on main), watch post-create apply migrations 0001–0005 and `npm ci`, then run `cargo run -p nameless-api --features postgres -- --server` and `VITE_NAMELESS_CLIENT=http npm run dev` in `web/`.

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | `08d7586` | feat(quick-260704-em1): add Codespaces devcontainer with CI-mirrored pgvector Postgres |
| 2 | `73e2a85` | feat(quick-260704-em1): add idempotent post-create with marker-guarded migrations |
| 3 | `c77848e` | docs(quick-260704-em1): README 'Run in a Codespace' section with verified launch commands |

## Self-Check: PASSED

All 4 code files + SUMMARY exist on disk; all 3 task commits present in git log; zero file deletions across the 3 commits.
