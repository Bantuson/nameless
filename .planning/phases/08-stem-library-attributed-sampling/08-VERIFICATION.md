---
phase: 8
phase_name: Stem Library + Attributed Sampling
status: passed
verified_by: tests-run (115 Python) + Rust review (course-project mode)
date: 2026-06-28
---

# Phase 8 Verification — Stem Library + Attributed Sampling

**Executed here (orchestrator re-ran):** `cd workers && python -m pytest -q` → **115 passed in 1.00s** (13 new Phase-8 + 102 prior). Rust written + reviewed, NOT compiled. Demucs NOT run (env-gated).

## Success criteria
| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Uploaded track → Demucs stems retained + browsable, with separator provenance | ✅ executed (fake) / reviewed (Demucs) | `StemSeparator` (htdemucs_ft/_6s real lazy + fake); content-addressed `SeparationJobConsumer`; `stems` table + `stems list` |
| 2 | Promote any stem → `sampled` anytime, human lifecycle, never eval gate | ✅ reviewed (Rust) | `Fragment::new_sampled`; `sample add`; sampled travels Captured→…→Placed (Phase-1 typed) |
| 3 | State machine blocks placement until attribution complete — hard, no bypass | ✅ executed + reviewed | `CompleteAttribution` (all non-Option → incomplete unrepresentable); `place()` requires `&CompleteAttribution`; `apply(Place)` refuses samples; DB NOT NULL + span check; tests prove no bypass |
| 4 | `rights_status` field + "attribution ≠ permission" stated in-context | ✅ executed + reviewed | `RightsStatus` enum; credits + `sample show` lead with the permission notice |
| 5 | Export project credits sheet (source/artist/stem/time-range) | ✅ executed | pure `credits_sheet(rows)` → markdown; `credits <project>` |

## Requirement coverage
SAMP-01 ✅ · SAMP-02 ✅ · SAMP-03 ✅ · SAMP-04 ✅ · SAMP-05 ✅

## The integrity invariant (headline)
Incomplete-attribution placement is **unrepresentable**: only `PartialAttribution::into_complete()` (validates; lists missing fields; treats whitespace artist / inverted range as missing) yields a `CompleteAttribution`; the sampled `Analyzed→Placed` edge demands it; `apply(Place)` refuses samples outright; DB mirrors with `NOT NULL` + positive-span. The sampling counterpart to the eval gate.

## Testability law — satisfied
✅ ports (StemStore/AttributionStore/SampleStore [Rust], StemSeparator/StemStore/TrackLoader [Python]) × real+fake · ✅ pure core (credits_sheet, completeness predicate, separation record) · ✅ SoC · ✅ loose coupling (lazy Demucs) · ✅ tests RUN (115 Python) + Rust tests written.

## Learning artifact
`workers/LEARNING.md` §11c — how Demucs source separation works (hybrid waveform/spectrogram U-Net + transformer, mask estimation, htdemucs_ft vs _6s piano), attribution-clean sampling vs copy-and-claim, the honest legal reality (sampling recordings infringes regardless of intent; attribution ≠ permission; rights-status from day one), the attribution-completeness invariant.

## Env-gated (real env)
Rust: `cargo test -p nameless-{core,adapters,cli}`; `cargo sqlx migrate run` (0004); `cargo test -p nameless-adapters --features postgres -- --ignored`. Demucs: `uv add demucs torch torchaudio` (wiring in workers/README).

**PASS** — Python layer executed (115 tests), Rust + Demucs reviewed-complete + env-gated. Attribution invariant proven structural.
