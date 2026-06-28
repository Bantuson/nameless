# Phase 9: Thin Web UI — Summary

**Phase:** 09 (FINAL — M0) · Thin Web UI
**Status:** Complete; typecheck + tests RAN and pass here. Real axum-backend wiring is env-gated.
**Requirements:** UI-01, UI-02, UI-03, UI-04 — all covered.

A complete React + TypeScript + Vite web surface for the M0 loop, in `web/`. Four screens over a typed
`NamelessApi` port with a real `fetch` adapter and an in-memory mock, pure presentational components,
data hooks, and a compact contract that never carries waveforms/feature arrays. Built to the
testability law (DI/ports-and-adapters, pure functions, separation of concerns, loose coupling); the
whole UI runs and is tested with **no backend**.

---

## Testability design (the api-port + mock seam)

```
screens ─▶ hooks (useFragments/useReferences/useStemLibrary/useProject) ─▶ NamelessApi (port)
                                                                            ╱            ╲
                                                              HttpNamelessApi            MockNamelessApi
                                                              (real fetch → axum)        (in-memory fixtures)
```

- **`NamelessApi`** (`web/src/api/NamelessApi.ts`) — the single typed contract; mirrors the
  control-plane / CLI operations (projects, capture, fragments, reference upload/show/attach, stems
  separate/list, sample add/show, project graph, credits).
- **`HttpNamelessApi`** — the real adapter (multipart for audio, compact JSON, typed errors). Complete +
  reviewed; **env-gated** (no live axum here).
- **`MockNamelessApi`** — in-memory, seeded from fixed fixtures; enforces the same invariants the server
  does (notably the attribution-completeness gate). Powers dev + every test. **No network.**
- Injected via React context (`web/src/api/context.tsx`); the composition root
  (`web/src/main.tsx` → `web/src/api/createClient.ts`) is the only place a concrete adapter is named —
  swap real↔mock with one env var.
- **Pure logic** mirrors the Rust integrity boundaries: `lib/attribution.ts` ports
  `PartialAttribution::missing_fields`; `lib/credits.ts` ports `credits_sheet`. So the client shows the
  gate before a round-trip, and the server re-validates authoritatively.
- **Compact contract**: every type in `api/types.ts` carries ids/labels/scalars + the embedding
  *dimension* — never a vector or a melodic field (`f0`/`chroma`/`melody`/`key`/`chord`/`structure`),
  the same structural non-cloning guarantee the server enforces.

---

## File map (`web/`)

**Config / shell**
- `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `.env.example`, `.gitignore`, `README.md`
- `src/main.tsx` — composition root (providers + router + injected client)
- `src/App.tsx` — shell + routes; active-project default
- `src/styles.css` — dark/atmospheric design tokens; focus-visible, reduced-motion, responsive
- `src/vite-env.d.ts`, `src/test/setup.ts`

**API (the port + adapters + contract)**
- `src/api/types.ts` — the compact contract types (mirror the CLI `--json` shapes)
- `src/api/NamelessApi.ts` — the port interface
- `src/api/HttpNamelessApi.ts` — real fetch adapter (env-gated)
- `src/api/MockNamelessApi.ts` — in-memory adapter
- `src/api/fixtures.ts` — seeded world + internal record model
- `src/api/errors.ts` — `ApiError` / `NotFoundError` / `IncompleteAttributionError`
- `src/api/context.tsx` — `ApiProvider` / `useApi`
- `src/api/createClient.ts` — env-driven adapter selection

**Pure logic**
- `src/lib/attribution.ts` (port of Rust `missing_fields`), `credits.ts` (port of `credits_sheet`),
  `format.ts`, `rights.ts` (port of `RightsStatus::note`), `graph.ts`, `ids.ts`

**Data hooks**
- `src/hooks/useAsyncData.ts`, `useProjects.ts`, `useFragments.ts`, `useReferences.ts`,
  `useStemLibrary.ts`, `useProject.ts`

**Presentational components**
- `src/components/ui.tsx` (Button/Field/Banner/Loading/ErrorMessage/EmptyState/Stat), `badges.tsx`,
  `FragmentList.tsx`, `TonalBalanceBars.tsx`, `ReferenceSummaryCard.tsx`, `StemTable.tsx`,
  `AttributionForm.tsx`, `GraphView.tsx`, `CreditsList.tsx`, `AppHeader.tsx`
- `src/ActiveProjectContext.tsx`

**Screens**
- `src/screens/CaptureScreen.tsx` (UI-01), `ReferenceScreen.tsx` (UI-02),
  `StemLibraryScreen.tsx` (UI-03), `ProjectScreen.tsx` (UI-04), `common.tsx`

**Tests (40, all passing)**
- `src/lib/attribution.test.ts`, `format.test.ts`, `credits.test.ts`
- `src/api/MockNamelessApi.test.ts` (the client-interface contract + the gate + no-array invariant)
- `src/screens/{Capture,Reference,StemLibrary,Project}Screen.test.tsx`, `src/App.test.tsx`
- `src/test/renderWithApi.tsx` (test helper: injects the mock + providers + MemoryRouter)

---

## Requirement coverage

| Req | Screen | Evidence |
|-----|--------|----------|
| **UI-01** Capture a fragment + intent note → listed by id/state | `CaptureScreen` | file + note + kind form → `useFragments.capture` → `FragmentList`; tests: render + capture interaction |
| **UI-02** Upload a reference → vibe + non-melodic targets + "context, never cloned" | `ReferenceScreen` + `ReferenceSummaryCard` | genre / tempo range / LUFS / tonal balance / stereo width / vibe / embedding-dim (vector withheld); attach control; tests assert all + the boundary note |
| **UI-03** Browse stems → add as sample (attribution + rights; "attribution ≠ permission") | `StemLibraryScreen` + `StemTable` + `AttributionForm` | stem table → completeness-gated form (mirrors Rust rule) → `addSample`; warn banner; tests assert gate + add |
| **UI-04** Fragment graph (nodes + notes + key/tempo) + credits | `ProjectScreen` + `GraphView` + `CreditsList` | nodes with provenance/state/key/tempo + lineage edges; credits with the permission notice + markdown sheet; tests assert both |

---

## Verification (honest)

**RAN here (Node 22 works on this box):**
- `npm install` — succeeded (182 packages, ~2 min).
- `npx tsc --noEmit` — **PASS** (0 errors).
- `npx vitest run` — **PASS**: 40 tests across 9 files (pure logic, the `MockNamelessApi` contract incl.
  the attribution gate + no-array/no-melody invariant, all four screens, and the app shell/routing).
- `npx vite build` — **PASS** (69 modules; 207 KB JS / 65 KB gzip, 12 KB CSS).

Exact commands to re-run:
```bash
cd web && npm install && npm run typecheck && npm run test && npm run build
```

**Env-gated (NOT run here — needs the real backend, as designed in course mode):**
- The real **axum control-plane server** + Postgres are not run on this 4GB/no-Docker/no-Rust box, so
  `HttpNamelessApi` was not exercised against a live server. It is complete + reviewed; its endpoint
  mapping is documented in its JSDoc + `web/README.md`.
- To wire it: set `VITE_NAMELESS_CLIENT=http` and `VITE_API_BASE_URL=<server>` (see `web/.env.example`),
  start the axum server + Postgres, then `npm run dev`. Full e2e against the live backend is the
  user's-environment step.

**Notes**
- React Router emits informational v7 future-flag warnings during tests (harmless).
- The mock simulates two server-async steps as immediately-complete for a smooth offline demo: reference
  analysis (job-driven on the server) and stem separation (a Demucs job). Both are flagged in code
  comments; the contract/types are identical to the real path.
