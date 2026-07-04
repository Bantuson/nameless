#!/usr/bin/env bash
# Codespaces post-create: system deps, uv, wait for Postgres, apply migrations, web deps.
#
# Idempotent end to end — post-create can re-run on container rebuilds against the
# persisted db volume (see docker-compose.yml's nameless-pgdata volume).
#
# MIGRATION STRATEGY — per-file marker table, NOT a blind loop:
# migrations 0001/0003/0004/0005 are NOT idempotent (bare CREATE TYPE / CREATE TABLE /
# CREATE INDEX; only 0002 is fully guarded), so blindly re-applying migrations/*.sql
# fails on the second run. A fresh-vs-absent check on one table (e.g. fragments) would
# break the moment a NEW migration file lands — the per-file marker below applies only
# what is missing. This intentionally diverges from ci.yml's blind loop because CI gets
# a fresh database every run and this volume persists.

set -euo pipefail

echo "==> [1/5] System packages (postgresql-client, ffmpeg)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends postgresql-client ffmpeg

echo "==> [2/5] uv (Python env/dependency manager for the worker plane)"
# The Astral installer targets ~/.local/bin, which the devcontainer base puts on PATH;
# guard on both PATH lookup and the install location so re-runs skip cleanly.
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
else
  echo "uv already installed — skip"
fi

echo "==> [3/5] Waiting for Postgres (host db, service in docker-compose.yml)"
attempts=0
until pg_isready -h db -p 5432 -U nameless >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 30 ]; then
    echo "ERROR: Postgres at db:5432 did not become ready after 30 attempts (60s)." >&2
    echo "Check the db service logs: docker compose -f .devcontainer/docker-compose.yml logs db" >&2
    exit 1
  fi
  echo "  pg_isready attempt ${attempts}/30 — retrying in 2s"
  sleep 2
done
echo "Postgres is ready."

echo "==> [4/5] Applying migrations (marker-guarded, ON_ERROR_STOP=1)"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "create table if not exists _devcontainer_migrations (filename text primary key, applied_at timestamptz not null default now())"

# Shell glob = filename order (0001..0005), same ordering as ci.yml's loop.
for f in migrations/*.sql; do
  name="$(basename "$f")"
  applied="$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tA -c "select 1 from _devcontainer_migrations where filename = '$name'")"
  if [ "$applied" = "1" ]; then
    echo "  $name: skip (already applied)"
    continue
  fi
  echo "  $name: applying"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "insert into _devcontainer_migrations (filename) values ('$name')"
done

echo "==> [5/5] Web dependencies (npm ci, clean install from web/package-lock.json)"
npm ci --prefix web

cat <<'READY'

============================================================
Nameless Codespace ready.

Start the API (postgres profile; DATABASE_URL is already set,
migrations already applied — sqlx compile-time checks will pass):

  cargo run -p nameless-api --features postgres -- --server

Start the web UI against it:

  cd web && VITE_NAMELESS_CLIENT=http npm run dev

See README.md "Run in a Codespace" for the lean (--local) run
and the browser-based-Codespace CORS/base-URL caveats.
============================================================
READY
