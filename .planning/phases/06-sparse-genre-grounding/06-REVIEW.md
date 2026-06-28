---
status: issues
phase: 06-sparse-genre-grounding
depth: standard
files_reviewed: 15
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
---

# Phase 6: Code Review Report — Sparse-Genre Grounding

**Depth:** standard (Python-specific, read-by-reading; the real librosa/CLAP TrackAnalyzer was never executed here — audio-path correctness is reviewed statically and marked env-gated where it depends on real ML output)

## Summary

The integrity boundary of this phase holds well. `grounding_confidence` is conservative by construction (no direct tutorials → `LOW`, default → `LOW`, ceiling `MED`, `HIGH` is **unreachable**), and `AuthoredSkill.confidence_tier` independently forces `LOW` for any `grounded` skill, so the registry/CLI can never present a sparse-genre skill as settled. Audio-derived claims carry only measured non-melodic surface, every number is read from the analysis record (no hardcoded craft numbers), and the grounded path runs the same `citation_gate` before emitting. No Critical defects found.

The findings are about (a) a second source of truth for confidence that can disagree with the registry inside the emitted file, (b) the honesty banner over-claiming relative to the un-cited editorial decomposition prose it sits above, and (c) error-handling/robustness gaps on the audio leg.

## Warnings

### WR-01: Confidence label can diverge between the emitted SKILL.md and the registry/CLI

**File:** `knowledge-pipeline/src/knowledge_pipeline/grounding_pipeline.py:236-245`, `knowledge-pipeline/src/knowledge_pipeline/pure/confidence.py:53-59`, `knowledge-pipeline/src/knowledge_pipeline/domain/skills.py:252-254`
**Issue:** The pipeline passes `grounding_confidence(...)` into the frontmatter (`emit_grounded_skill_md(..., confidence=confidence)`), and that function can legitimately return `MED` (when `direct_tutorial_sources >= 3 and parent_techniques >= 2 and audio_track_count >= 3`). But `AuthoredSkill.confidence_tier` hard-codes `LOW` whenever `grounded is True`. The registry has no stored confidence column — the only persisted confidence text is the frontmatter inside `body_md`. So in the `MED` branch the **file the M1 agent loads says `confidence: MED`** while `skills show` / `list` / `audit` / `stats` all report `LOW`. Two sources of truth that can disagree, on the exact field that gates how the arranger weights the skill. (In the shipped alt-piano case `direct = 0 → LOW`, so it is not triggered today — but the divergence is latent and reachable.)
**Why it matters:** The phase's honesty law is "sparse-genre skills are LOW and labeled as such." If a genre reaches the `MED` branch it also has ≥3 direct tutorials, i.e. it should arguably not be on the grounding path at all — the `MED` is an internally inconsistent state, and whichever value the consumer reads is non-deterministic across surfaces.
**Fix:** Make one of them authoritative. Either force the emitter to use `AuthoredSkill.confidence_tier` (always `LOW` for grounded) for the frontmatter, or have `grounding_confidence` return `LOW` unconditionally for the grounded path and delete the `MED` branch (the module docstring's "ceiling MED" is the thing that creates the divergence). Add a test asserting `frontmatter.confidence == authored_skill.confidence_tier`.

### WR-02: Honesty banner over-claims relative to the un-cited editorial decomposition prose beneath it

**File:** `knowledge-pipeline/src/knowledge_pipeline/pure/grounded_emitter.py:74-93`, `knowledge-pipeline/src/knowledge_pipeline/pure/decompose.py:38-67`
**Issue:** The emitted banner asserts: *"Every assertion below is traceable to a cited tutorial claim … OR a measured audio analysis record … No claim, number, or technique was invented."* Immediately below it, the `## Grounding` section renders each parent's `contributes` text and the `negative_space` list verbatim — e.g. *"lush, extended (7th/9th) voicings that leave space"*, *"delay/dub sends, airy pads and panned organic percussion"*, *"the log drum … deliberately softer/rounder than mainstream amapiano; it is not the loudest element."* These are specific, un-cited craft/technique assertions authored editorially in `decompose._DECOMPOSITIONS`, not backed by a `SkillCitation` and not passed through the gate. The banner's absolute "nothing was invented / everything is traceable" is therefore literally false for that section.
**Why it matters:** This is the precise failure mode the phase exists to avoid — presenting an editorial hypothesis as if it carried the same citation discipline as gated claims. The grounding is honest *overall* (LOW, "decomposition not direct tutorials"), but the blanket banner launders the un-cited prose.
**Fix:** Scope the banner to the gated layers ("Every assertion in Default / Consensus / Contested is traceable…"), and explicitly label the Grounding section as an editorial decomposition hypothesis (it partially does this — make it unambiguous that `contributes`/`negative_space` are the hypothesis, not cited evidence).

### WR-03: Tracks that yield zero audio-derived claims are silently dropped; a "grounded" skill can ship claiming audio corroboration with none

**File:** `knowledge-pipeline/src/knowledge_pipeline/grounding_pipeline.py:178-186, 199-246`
**Issue:** `_analyze_tracks` does `if not adcs: continue`, so any analyzed track that produces no claims is dropped from `records` with no log. If every track drops (or the roster is empty) but parent claims exist, `ground()` still proceeds, the gate passes on decomposition-only evidence, and the skill is authored with `grounded=True`. The `grounding_note` then reads "audio analysis of 0 released track(s)", and `emit_grounded_skill_md`'s `if records:` block omits the corroboration roster — yet the fixed banner and description still say the skill was "corroborated against measured track(s)."
**Why it matters:** Honesty law again: the artifact claims an audio-grounding leg it did not actually use. Low likelihood for real audio (a valid track yields at least a tempo claim) but it is a silent, unguarded path.
**Fix:** Require at least one `AudioAnalysisRecord` for the grounded path (reject with a clear reason if `not records`), or branch the banner/description on `len(records) == 0`. Log dropped tracks at WARNING.

### WR-04: No per-track error handling on the audio leg — one bad file aborts the whole grounding run

**File:** `knowledge-pipeline/src/knowledge_pipeline/grounding_pipeline.py:178-186`, `knowledge-pipeline/src/knowledge_pipeline/adapters/track_analyzer_worker.py:88-124`
**Issue:** `_analyze_tracks` calls `self._analyzer.analyze(track)` with no try/except. The real `WorkerTrackAnalyzer` can raise on a missing/corrupt file (`_default_loader` → `open(...)`, `sf.read`/`librosa.load` decode failures, or a `KeyError`/None from the workers API). A single failing track in a multi-track roster propagates out of `ground()` and aborts the run with no partial result and no per-track context. This is inconsistent with the silent-skip behavior for empty claims (WR-03): empty→skip, exception→hard-crash. [env-gated — only reachable with the real analyzer over real audio]
**Why it matters:** Robustness of the live path. Analyzing released tracks is exactly where I/O and decode failures happen; aborting the entire skill author because file 4 of 6 is bad is a poor failure mode.
**Fix:** Wrap each `analyze` in try/except, log the failing `track_id` + error, skip it, and (combined with WR-03) require ≥1 successful record before authoring. Document the intended policy (fail-fast vs best-effort) explicitly.

## Info

### IN-01: Unused `import numpy as np` in `WorkerTrackAnalyzer.analyze`

**File:** `knowledge-pipeline/src/knowledge_pipeline/adapters/track_analyzer_worker.py:89`
**Issue:** `analyze` imports `numpy as np` at its top but never references `np` in the method body — every DSP helper imports its own `np` locally.
**Fix:** Remove the unused import (the helpers already lazy-import numpy where needed).

### IN-02: Genre slug inconsistency — `alt-piano` (records/tracks) vs `alternative-piano` (target cell)

**File:** `knowledge-pipeline/src/knowledge_pipeline/domain/grounding.py:64,94`, `knowledge-pipeline/src/knowledge_pipeline/pure/decompose.py:29`, `knowledge-pipeline/src/knowledge_pipeline/skills_cli.py:188`
**Issue:** `TrackRef`/`AudioAnalysisRecord` default `genre="alt-piano"` and audio claims carry `genre=["alt-piano"]`, while the authored cell is `genre="alternative-piano"`. `_direct_tutorial_sources` papers over this with `target.genre.replace("alternative-", "alt-")`, but the emitted artifact ends up mixing both slugs (cell = `alternative-piano`, citation/genre tags = `alt-piano`). A later genre-filtered query (`list_skills(genre=...)`, claim clustering) would treat them as different genres.
**Fix:** Pick one canonical slug for the subgenre and use it for both the cell and the records, or centralize the alias in one normalization helper rather than an inline `.replace`.

### IN-03: `skills ground --target alt-piano` does not match the only authored target

**File:** `knowledge-pipeline/src/knowledge_pipeline/skills_cli.py:255-262`, `knowledge-pipeline/src/knowledge_pipeline/pure/decompose.py:29`
**Issue:** Target matching is `t.genre == args.target or t.slug == args.target`; the only known target has `genre="alternative-piano"` / slug `alternative-piano-composite`. A user who (reasonably) types `--target alt-piano` — the slug used throughout the fixtures and records — gets "no decomposition for target 'alt-piano'". It errors clearly, so it is only a UX papercut.
**Fix:** Accept the `alt-piano` alias in the match (same alias map as IN-02).

### IN-04: Audio snapshot makes the gate's rot-check self-referential for audio claims (by design — document it)

**File:** `knowledge-pipeline/src/knowledge_pipeline/domain/grounding.py:160-204`
**Issue:** `to_claim` sets `quote = statement`, and `audio_snapshot` builds segments whose `text` is that same `statement`. So the gate's R5 "find the cited quote in the source snapshot" and its number-vs-quote check are tautological for audio claims — the record *is* its own source. This correctly catches **synthesis drift** (if the synthesizer alters "110 bpm" → "120 bpm" the prose number no longer matches the quote), but it provides **no independent verification of the measurement itself** — the trust boundary is the analyzer. This is acceptable/by-design ("the track is the citation"), but it is a meaningful limit of what the gate proves for the grounded path and is worth stating explicitly so it is not mistaken for measurement validation.
**Fix:** Add a one-line note in `audio_snapshot`/`to_claim` (and the phase docs) that the gate certifies synthesis fidelity, not measurement truth, for audio claims.

---

_Reviewer: Claude (gsd-code-reviewer) · Depth: standard · Critical: 0 · Warning: 4 · Info: 4_
