---
status: issues
phase: 09-thin-web-ui
depth: standard
files_reviewed: 40
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
---

# Phase 09: Thin Web UI — Code Review Report

**Depth:** standard
**Files Reviewed:** 40
**Status:** issues_found

## Summary

The web layer is clean and well-architected: the `NamelessApi` port is the single seam, no
component touches `fetch`/URLs, the Mock+Http adapters are both real, and the testability law is
honored throughout. The high-risk attribution surface holds up: `missingAttributionFields` mirrors
the Rust gate exactly, the "Add as sample" button is genuinely disabled until attribution is
complete, `CreditsList` renders every sample (`credits.samples.map`, no slicing/filtering), and the
"attribution is not permission" notice is unconditional on the form, the credits list, and the
markdown sheet. No XSS was found — there is zero `dangerouslySetInnerHTML`, no `eval`, no
href/SVG construction from user data; user-controlled text (artist, notes, vibe) flows only through
React's escaped text nodes and a `<pre>` for the markdown sheet. There are no Critical findings.

The defects are: one confirmed Http↔server contract mismatch that the Mock hides (camelCase request
bodies vs the server's `snake_case` serde contract), a stale-data-during-load issue that contradicts
`useAsyncData`'s own docstring, two silent error-handling gaps, and Mock/Http parity gaps that mask
error states. Plus minor a11y/quality items.

## Warnings

### WR-01: Http request bodies use camelCase keys that mismatch the server's `snake_case` serde contract

**File:** `web/src/api/HttpNamelessApi.ts:100-105, 117-126`
**Issue:** `attachReference` sends `{ referenceId, role }` and `addSample` sends
`{ stemId, artist, startMs, endMs, rights, title }`. The Rust core
(`crates/nameless-core/src/attribution.rs:43,105`) is `#[serde(rename_all = "snake_case")]` with
fields `stem_id`, `source_artist`, `start_ms`, `end_ms` (and the response types in `types.ts` are
all snake_case). So the real backend will fail to deserialize these bodies — `stemId` is not
`stem_id`, `startMs` is not `start_ms`, and `artist` is not `source_artist`. The `MockNamelessApi`
reads the input object's TS properties directly, so it never exercises wire naming — the bug is
completely invisible until the axum server lands. Multipart fields (`note`, `kind`, `title`,
`artist`) are single words and happen to be fine, which makes the JSON-body mismatch easy to miss.
**Why it matters:** The two write paths that carry attribution data (the integrity-critical sample
creation, plus reference attach) will 4xx/deserialize-fail against the real control plane, and the
client-side gate's whole point is to make the round-trip honest.
**Fix:** Serialize request bodies in snake_case to match the contract, e.g.
`{ stem_id: input.stemId, source_artist: input.artist, source_title: input.title, start_ms: input.startMs, end_ms: input.endMs, rights: input.rights }`
and `{ reference_id: input.referenceId, role: input.role }`. Add a parity test that asserts the
serialized body keys. [env-gated — server does not run here; mismatch proven against the existing
`attribution.rs` serde contract]

### WR-02: Stale data from the previous entity is rendered during a load, contradicting `useAsyncData`'s contract

**File:** `web/src/hooks/useAsyncData.ts:27-47`; `web/src/screens/ProjectScreen.tsx:42-51`; `web/src/screens/ReferenceScreen.tsx:153-155`
**Issue:** `useAsyncData` sets `loading=true` and clears `error` on a deps change, but never resets
`data`. Its docstring claims it "Cancels stale resolutions (so a fast project switch can't render the
previous project's data)" — it cancels the stale *resolution* but the already-set `data` stays
mounted. `ProjectScreen` then renders `{graph.loading ? <Loading/>}` AND `{graph.graph ? <GraphView/>}`
simultaneously, so on a project switch the spinner shows next to the *previous* project's graph and
credits until the new fetch resolves. `ReferenceScreen` has the same with the summary card on
selection change. (`CaptureScreen:126` gets this right by gating the list on `!loading`, which makes
the inconsistency clear.)
**Why it matters:** Cross-project data leakage on screen — the graph view briefly attributes one
project's fragments/credits to another, which is exactly what the docstring promises won't happen.
**Fix:** In `useAsyncData`, `setData(undefined)` when deps change (before the load), OR gate the
data renders on `!loading` in `ProjectScreen`/`ReferenceScreen` as `CaptureScreen` does.

### WR-03: `separate()` and `createProject()` failures are swallowed with no user feedback

**File:** `web/src/screens/StemLibraryScreen.tsx:46-53`; `web/src/App.tsx:27-35`
**Issue:** `onSeparate` wraps `await separate()` in `try/finally` with **no `catch`**; the function
is fired from `onClick` without awaiting, so a rejection (any Http/server error from
`separateStems`) becomes an unhandled promise rejection — the button re-enables but the user sees
nothing, and the list's `error` state only covers the *list* load, not the separate action.
`App.handleCreate` has the identical `try/finally`-no-`catch` shape for `createProject`. Contrast
`onAddSample` (StemLibraryScreen:71) and `onAttach` (ReferenceScreen:73), which do catch and surface
errors — so the error handling is inconsistent across actions.
**Why it matters:** Against the real backend, a failed separation or project-create looks like a
no-op to the producer (it silently "did nothing"), and the Mock never errors on these paths so tests
won't catch it.
**Fix:** Add a `catch` that sets a visible error state (mirror `onAddSample`), e.g. a
`separateError`/`createError` rendered via `<ErrorMessage>`. [Http error paths are env-gated;
the missing-handler structure is provable by reading]

### WR-04: Mock never errors on missing project for `getProjectGraph`/`getCredits`; Http will — masking error states

**File:** `web/src/api/MockNamelessApi.ts:308-322, 324-344`
**Issue:** `getProjectGraph` does not call `requireProject` and returns an empty `{ nodes:[], edges:[] }`
for an unknown id; `getCredits` falls back to `project?.title ?? projectId` and also never throws.
Every other Mock read (`getFragment`, `getReferenceSummary`, `getSample`, `listStems`) throws
`NotFoundError` for a missing entity, and the real server's `CliError::NotFound` contract (which the
Http adapter maps at `HttpNamelessApi.ts:174`) will 404 here too. So these two read paths are the
only ones where Mock-vs-Http behavior diverges, and the divergence is in the "Mock never errors"
direction the brief warns about — `ProjectScreen`'s error branch for the graph/credits is never
exercised by any test or dev run.
**Why it matters:** A whole error-handling branch ships untested; a 404 from the real backend (e.g.
a deleted/invalid active project) will render differently than anything seen here.
**Fix:** Make the Mock authoritative-consistent: call `this.requireProject(projectId)` at the top of
both `getProjectGraph` and `getCredits` so it throws `NotFoundError` like the server, and add a test
covering the `ProjectScreen` error state. [parity]

## Info

### IN-01: `shortId` duplicated across two components

**File:** `web/src/components/FragmentList.tsx:8-10`; `web/src/components/GraphView.tsx:14-16`
**Issue:** Identical `shortId(id) => id.slice(0,8)` helper defined in both files.
**Fix:** Hoist to `lib/format.ts` (alongside the other pure label helpers) and import.

### IN-02: Attribution gate accepts a negative `start_ms`

**File:** `web/src/lib/attribution.ts:42-44`; `web/src/components/AttributionForm.tsx:56-57`
**Issue:** The range check is only `endMs > startMs`; a negative start (e.g. -100→100) passes both
the client gate and the Rust rule (which also only checks `end > start`). The `min={0}` on the input
is not enforced in validation (users can type/paste negatives). Shared spec gap, not a divergence.
**Fix:** Add `startMs >= 0` to `missingAttributionFields`'s range predicate (and mirror server-side)
if non-negative offsets are intended.

### IN-03: A11y gaps — no document `h1`, focus not managed on dynamic reveals

**File:** `web/src/components/AppHeader.tsx:44-49`; `web/src/screens/StemLibraryScreen.tsx:132-140`; `web/src/screens/CaptureScreen.tsx:65-74`
**Issue:** The brand "Nameless" is a `<span>`, so the document's first heading is a screen `<h2>` —
there is no `h1` (heading hierarchy starts at level 2). When a stem is selected the `AttributionForm`
appears below with no focus moved to it; after a successful capture the file input is remounted via
`formKey` and focus is dropped to `<body>`. Badges (`StatePill`/`RightsTag`) use color but always
carry a text label, so color-only signaling is acceptable; keyboard-nav of the graph/stem table is
the known remaining gap.
**Fix:** Promote the brand (or a visually-hidden node) to `h1`; move focus to the revealed form
heading on selection and back to a sensible control after capture reset.

### IN-04: `TonalBalanceBars` does not clamp out-of-range band values

**File:** `web/src/components/TonalBalanceBars.tsx:13-15`
**Issue:** `pct = Math.round((value/total)*100)` with no clamp; a negative or >total band value
(possible from a real analyzer) yields a negative or >100% inline bar width. Cosmetic (browser
clamps width), but the displayed `%` would be misleading.
**Fix:** Clamp `pct` to `[0,100]` before use.

---

_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
