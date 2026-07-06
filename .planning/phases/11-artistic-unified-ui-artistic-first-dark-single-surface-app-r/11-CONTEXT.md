# Phase 11: Artistic Unified UI - Context

**Gathered:** 2026-07-06 (dictated directly by the user — treat every decision below as LOCKED)
**Status:** Ready for UI-SPEC research

<domain>
## Phase Boundary

Replace the thin, multi-view M0 web UI with an artistic-first, single-surface application over the existing `NamelessApi` contract (Phase 10 axum backend, Phase 9 TS client). No backend changes; the API contract is fixed. All M0 functionality must be reachable: capture (record/upload + intent note), fragment graph (nodes, notes, key/tempo), reference upload + vibe/target summary, stem library + promote-to-sample, project credits.

</domain>

<decisions>
## Implementation Decisions (USER-LOCKED)

### Artistic direction
- **Artistic-first UI** — the interface itself is a piece of art, not a form-filling tool. Templated/bootstrap-looking output is a failure condition.
- **Dark theme** with carefully chosen aesthetic color palettes (plural: a base palette + accent moods is acceptable; garish neon-on-black is not).
- **North-star atmosphere: Sonder / Brent Faiyaz** — moody, spacious, intimate, analog-warm; the fusion genres are R&B × amapiano × deep house × alternative piano. The UI should *feel* like that music sounds.

### Structure
- **Landing view with a Three.js generative centerpiece** — the hero is a living, audio-reactive-capable 3D/generative scene (use the threejs-animation skill's craft), not a static hero image.
- **ONE home surface after landing** — ALL functionality in one place. Explicitly NOT a traditional multi-page web app with routed pages per feature. Panels/layers/overlays over a single canvas-like home, not navigation between screens.
- **Progressive disclosure** — think the layout through carefully: the surface starts calm and minimal; depth (feature detail, advanced options, data tables) reveals on intent, never all at once.

### UX philosophy
- **AI-native interface + human UX** — the interface should assume an intelligent system underneath (intent-first input, summaries over raw data, the system explains itself) rather than exposing raw CRUD.
- **Radically easier to learn than FL Studio or Logic** ("1000x less complicated") — a first-time user should do the core loop (capture → see it understood → sample → credits) without a tutorial. Jargon-free labels, one obvious next action, no wall-of-knobs.

### Craft process
- Apply the **impeccable** and **design-taste-frontend** skills' sensibilities to the spec: real design-system tokens, intentional typography, no slop.

### Claude's Discretion
- Exact palette values, type pairing, spacing scale, and the Three.js scene concept — within the locked direction above.
- How progressive disclosure is staged (which layer reveals what) — as long as the single-surface rule holds.
- Whether landing and home are one continuous scene (scroll/zoom transition) or a two-state app shell.

</decisions>

<specifics>
## Specific Ideas

- Three.js centerpiece on landing is the signature moment — worth real craft (generative, ideally reactive to project audio when available).
- The fragment graph is the natural heart of the home surface — the producer's material as a living constellation rather than a data table.
- Existing app (web/src) is React 18 + Vite, MockNamelessApi/HttpNamelessApi behind createClient(); keep that seam.

</specifics>

<canonical_refs>
## Canonical References

- `web/src/api/NamelessApi.ts` — the fixed API contract the UI must cover
- `.planning/ROADMAP.md` Phase 9 (UI-01..04 requirements — still the functional floor)
- PRD §4/§14 — M2 will add Tone.js real-time surfaces later; leave room, don't build it now

</canonical_refs>
