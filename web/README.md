# Nameless — Web (thin M0 surface)

A minimal, accessible React + TypeScript surface over the Nameless control plane: capture a fragment,
upload a reference and read its vibe/sonic-target summary, browse a track's retained stems and promote
one to an attributed sample, and watch a project's fragment graph + sample credits take shape.

It is deliberately **thin** — the interactive surface over the already-built control plane, **not** a
DAW. No real-time pad/timeline (M2), no generation/mix UI (M1).

---

## Architecture: a typed port + a mock = testable with no backend

The whole app talks to the control plane through a **single typed interface**, the `NamelessApi`
*port* (`src/api/NamelessApi.ts`). Nothing above it knows about `fetch`, a URL, or a server detail.

```
components/screens ─▶ hooks (useFragments, useReference, useStemLibrary, useProject)
                         │  depend on
                         ▼
                    NamelessApi  (the port — an interface)
                    ╱            ╲   two implementations satisfy it
        HttpNamelessApi          MockNamelessApi
        (real fetch adapter,     (in-memory fixtures;
         talks to axum)           powers dev + every test)
```

- **`NamelessApi`** — the contract. Mirrors the `nameless` CLI / control-plane operations: projects,
  capture, fragments, reference upload/show/attach, stems separate/list, sample add/show, project
  graph, credits.
- **`HttpNamelessApi`** (`src/api/HttpNamelessApi.ts`) — the real adapter. Sends multipart for audio,
  parses the server's compact JSON, maps errors to typed client errors. **Env-gated**: the axum server
  is built in `crates/` but is not run on the dev box, so this adapter is complete + reviewed but not
  exercised against a live server here.
- **`MockNamelessApi`** (`src/api/MockNamelessApi.ts`) — an in-memory implementation seeded from fixed
  fixtures (`src/api/fixtures.ts`). It enforces the same invariants the server does (most importantly
  the attribution-completeness gate) and is what dev mode + every test runs against. **No backend, no
  network required.**

The client is injected via React context (`src/api/context.tsx`); the composition root
(`src/main.tsx` → `src/api/createClient.ts`) is the **only** place a concrete adapter is named. Swap
the real server in with one env var — nothing else changes.

### Separation of concerns

- **Client** (`src/api/*`) — the contract, adapters, and typed errors. The only layer that knows a
  transport exists.
- **Data hooks** (`src/hooks/*`) — own the load/loading/error lifecycle and the write actions, over the
  injected port. No JSX.
- **Pure logic** (`src/lib/*`) — deterministic helpers: attribution-completeness (`attribution.ts`, a
  port of the Rust `missing_fields` rule), the credits-sheet renderer (`credits.ts`, a port of the Rust
  `credits_sheet`), formatting, graph-edge derivation. No I/O, no React → trivially unit-testable.
- **Presentational components** (`src/components/*`) — props in, JSX out. No data fetching.
- **Screens** (`src/screens/*`) — compose a hook + pure components. Orchestration only.

### The compact contract

Every type in `src/api/types.ts` mirrors the JSON the Rust CLI emits under `--json`. The defining
property is what is **absent**: no type can carry a waveform, a feature array, or an embedding vector.
The contract carries ids, labels, scalars, and the embedding *dimension* (a count) — never the vector.
The reference summary has **no** melodic field (`f0`/`chroma`/`melody`/`key`/`chord`/`structure`),
exactly the structural non-cloning guarantee the server enforces. (Asserted in
`src/api/MockNamelessApi.test.ts`.)

---

## Screens → requirements

| Screen | Route | Requirement | What it does |
|--------|-------|-------------|--------------|
| **Capture** | `/capture` | **UI-01** | Capture/upload a fragment + intent note → listed by id/state. |
| **Reference** | `/reference` | **UI-02** | Upload a reference → vibe + non-melodic targets (genre, tempo range, LUFS, tonal balance, stereo width, vibe prose, embedding dim) + the "context, never cloned" note; attach to a project. |
| **Stem Library** | `/library` | **UI-03** | Browse a track's retained stems → "add as sample" with attribution fields + rights status; surfaces "attribution ≠ permission". |
| **Project** | `/project` | **UI-04** | Fragment graph (nodes + notes + key/tempo + lineage) + sample credits list. |

---

## Run it

```bash
npm install
npm run typecheck     # tsc --noEmit
npm run test          # vitest run (component/hook + contract + pure-logic tests)
npm run dev           # Vite dev server, using the in-memory MockNamelessApi (no backend)
npm run build         # tsc --noEmit && vite build
```

By default the app uses the **mock** client, so `npm run dev` works with no backend.

### Env-gated: wire the real control plane

The real axum server is **not** run on the dev box (course-project build mode). To point the web app at
a running control plane:

```bash
# .env
VITE_NAMELESS_CLIENT=http
VITE_API_BASE_URL=http://127.0.0.1:8080
```

`HttpNamelessApi` then issues the real HTTP calls (see its JSDoc for the endpoint mapping, e.g.
`POST /projects/:id/fragments` multipart, `GET /projects/:id/graph`, `POST /projects/:id/samples`).
Bringing up the axum server + Postgres is the env-gated step the user runs in their real environment;
the typed contract + the mock are the deliverable here.

---

## Tests

- `src/lib/*.test.ts` — pure logic: attribution gate, formatters, credits-sheet renderer.
- `src/api/MockNamelessApi.test.ts` — the **client-interface contract**: every method, the
  attribution-completeness gate (incomplete → throws, creates nothing), and the no-array/no-melody
  invariant. The same assertions hold for any conformant `HttpNamelessApi`.
- `src/screens/*.test.tsx` + `src/App.test.tsx` — each screen renders + a key interaction, and the app
  shell routes + auto-selects a project — all over the `MockNamelessApi`, no backend.

All tests run in jsdom via Vitest + React Testing Library.
