# Phase 4: Cited Claim Mining + Cross-Reference - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

Turn the Phase-3 transcript corpus into a registry of **atomic, individually-cited claims**, grouped by topic into **preserved consensus and conflict**. This is the EXTRACT half of the make-or-break two-pass design — **extraction only, ZERO synthesis** (no opinionated defaults, no merged "best way", no skills — those are Phase 5). The discipline here is what prevents the GIGO failure the project exists to answer.

In scope: a typed claim schema; an LLM `ClaimExtractor` (structured/tool-use output) bound to source video_id + timestamp + exact quote; pure cross-reference clustering into consensus/conflict; claim/cluster persistence; a `claims` CLI to inspect + trace any claim to its source. Out of scope: synthesis + citation-verification GATE + SKILL.md (Phase 5), sparse-genre grounding (Phase 6).
</domain>

<decisions>
## Implementation Decisions

### Architecture (ports-and-adapters — testability law)
- `ClaimExtractor` port: `RawTranscript(+segments) → list[Claim]`. Real adapter = Claude (Anthropic SDK / `claude -p`) with **structured output (tool-use / pydantic schema)** — reliable LLM output comes from structure, not clever prose. Fake adapter = deterministic fixture/rule-based extractor for tests. The API call is the heavy/external leaf (key + tokens) → env-gated.
- `SimilarityIndex` port (for semantic dedup/grouping): real = embeddings; fake = keyword/exact. Default grouping is a deterministic normalized `(stage, technique)` key; semantic similarity is an optional pluggable refinement so the core stays testable.
- `ClaimStore` port: claims + clusters persistence (extends Phase 3 `registry.sqlite`). Real (sqlite) + in-memory fake.
- `MiningPipeline` = pure orchestration over injected ports (extract → bind citation → cross-reference → persist).

### Typed claim schema (pydantic) — KNOW-05
`Claim { id, claim_text, technique, stage, genre[], source_video_id, timestamp_ms, quote, confidence, caption_source }`. NO synthesized/derived fields. Every claim MUST carry its citation (video_id + timestamp + verbatim quote from the snapshot segment).

### Citation binding + traceability (KNOW-05 #2)
- Each claim binds to a Phase-3 snapshot segment. A PURE `verify_citation(claim, snapshot)` checks the quote actually occurs at/near the cited timestamp — testable, and the precursor to Phase 5's hard citation gate.
- `claims show <id>` traces back to the exact source quote + timestamp + video.

### Cross-reference: consensus + conflict (KNOW-06)
- PURE `cross_reference(claims) → list[ClaimCluster]` where a cluster has a topic key + `consensus` (corroborating claims) + `conflicts` (claims that disagree, e.g. amapiano log-drum FLEX-synth vs layered-samples — preserve BOTH). A conflict is recorded as first-class data, **never silently deleted**. Corroboration counts distinct sources, not repeats.

### The extraction prompt is a real artifact
- Author a careful, structured extraction prompt enforcing: atomic single-technique claims, mandatory citation, "extract only — do NOT synthesize, do NOT invent numbers not spoken", confidence calibration. Research flagged this prompt design MEDIUM-confidence — treat it as load-bearing even though not run here.

### Claude's Discretion
- sqlite schema for claims/clusters, normalization rules, similarity threshold, prompt wording details.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 3 `knowledge-pipeline/` — `RawTranscript`+segments, `SnapshotRecord`, `registry.sqlite`, the ports+fakes+pure-core+LEARNING pattern, and CLAUDE.md's pydantic/tool-use extraction note. EXTEND this package (same `knowledge_pipeline` namespace) — do not start a new one.
- `.planning/research/PITFALLS.md` (GIGO distillation: extract-then-synthesize split, never invent numbers, preserve contradiction, citation-drift) and `FEATURES.md` (consensus/conflict layered output; amapiano FLEX-vs-layered example).

### Established Patterns
- typing.Protocol ports + real+fake; pure-function core tested with fixtures; lazy heavy imports (anthropic SDK only inside the real extractor); pydantic typed boundaries; tests RUN on the base env (pydantic/numpy/pytest).

### Integration Points
- Input = Phase 3 corpus (snapshots + segments). Output (claims + consensus/conflict clusters in registry.sqlite) is the INPUT to Phase 5 synthesis + citation gate.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — write complete real code incl. the real Anthropic-SDK extractor; DO NOT call the API or install it. Verify by review + tests-that-RUN against the FAKE extractor + fixtures (cross-reference consensus/conflict, citation verification, schema, dedup, pipeline e2e). Real extraction is env-gated (`ANTHROPIC_API_KEY`, token cost).
- **Ship a `LEARNING.md` section** (extend knowledge-pipeline LEARNING) teaching: why structured/tool-use output beats free-form for reliable extraction; the extract-THEN-synthesize split and WHY it defeats GIGO (hallucinated craft, genre conflation, citation drift); citation discipline; consensus vs conflict as first-class data; semantic dedup trade-offs. This is the project's intellectual core — teach it genuinely.
</specifics>

<deferred>
## Deferred Ideas
- Synthesis, the programmatic citation-verification GATE, authored SKILL.md, human spot-audit → Phase 5.
- Sparse-genre decomposition + released-track audio grounding → Phase 6.
</deferred>
