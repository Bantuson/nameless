# Phase 9: Thin Web UI - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

A minimal React/TS web surface for the M0 loop: capture a fragment + note, upload a reference and view its vibe/sonic-target summary, browse the stem library and "add as sample", and view a project's fragment graph + sample credits. Thin and functional — the interactive surface over the already-built control plane (CLI/API), NOT a full DAW.

In scope: the four screens (UI-01..04), a typed API-client layer with a mock for dev/tests, pure presentational components, and runnable typecheck + component tests. Out of scope: real-time pad/timeline (M2), generation/mix UI (M1), backend wiring to a live server (the API contract is defined + mocked here; the real axum server is env-gated).
</domain>

<decisions>
## Implementation Decisions

### Stack
- React 18/19 + Vite + TypeScript (per PRD/CLAUDE stack). Vitest + React Testing Library for component/hook tests. Tailwind for styling (lightweight). Node runs on this 4GB box, so typecheck + tests should genuinely RUN here.

### Architecture (testability law)
- **A typed `NamelessApi` client interface (port)** with a real `fetch`-based impl (talks to the control-plane HTTP API contract) AND a `MockNamelessApi` (in-memory fixtures) used by dev + every test. Components/hooks depend on the interface, never on `fetch` directly — so the whole UI is testable with no backend.
- **Pure presentational components** (props in, JSX out) separated from data hooks (`useFragments`, `useReference`, `useStemLibrary`, `useProject`) that call the client. SoC: presentation / data / client. Loose coupling via the client interface + React context for injection.
- Compact contract mirrored: the API returns summaries (ids, key, tempo, vibe targets, credits) — never raw waveforms/feature arrays.

### Screens (UI-01..04)
- **Capture** (UI-01): record/upload a fragment + intent note → shows it listed by id/state.
- **Reference** (UI-02): upload a reference track → shows the extracted vibe + non-melodic sonic-target summary (genre, tempo range, LUFS, tonal balance, stereo width, vibe prose). Honest "context, never cloned" note.
- **Stem Library** (UI-03): browse an uploaded track's retained stems → "add as sample" (with attribution fields + rights-status; surfaces "attribution ≠ permission").
- **Project** (UI-04): fragment graph (nodes + notes + key/tempo) + the sample credits list.

### Aesthetic (light touch)
- Clean, calm, dark/atmospheric to fit the north-star (Sonder/Brent Faiyaz) without over-designing a thin M0 tool. Accessible (labels, keyboard, contrast). Function first.

### Claude's Discretion
- Component/file structure, routing (React Router), styling details, state lib (prefer simple hooks/React Query), the exact API contract shape (document it).
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- The control-plane CLI surfaces (Phases 1/7/8: capture, fragments, reference, stems, sample, credits) + the Python workers define the operations the API exposes. The UI's `NamelessApi` contract should mirror those operations (capture, list fragments, upload reference + get summary, list stems, add sample, get project graph + credits).
- `.planning/research/STACK.md` (React 18/19 + Vite; M0–M1 capture/notes/graph view) + PROJECT.md north-star aesthetic.

### Established Patterns
- The whole project's testability law: port + real + fake. Here = `NamelessApi` interface + `fetch` impl + `MockNamelessApi`. Pure functions/components; tests RUN.

### Integration Points
- Talks to the (future) control-plane HTTP API. In course mode the real server isn't wired — the typed contract + mock client are the deliverable; real wiring is env-gated. This is the only frontend phase (UI hint: yes).
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — write the complete real app; **attempt** `npm install` + `tsc` typecheck + `vitest` run here (Node works on 4GB) and report honestly; if install thrashes the 4GB box, write code + tests and flag the exact commands. The real backend wiring (axum server) is env-gated.
- **Ship a `web/README.md`** explaining the architecture: the `NamelessApi` port + mock (why — testable with no backend), the presentation/data/client separation, the compact contract, and how to run (`npm install && npm run test && npm run dev`), plus the env-gated real-backend note.
- Keep it genuinely thin: four screens, clean and accessible, no scope creep into M1/M2 surfaces.
</specifics>

<deferred>
## Deferred Ideas
- Real-time Tone.js pad + timeline (M2). Generation/mix/eval UI (M1). Live backend wiring + auth.
</deferred>
