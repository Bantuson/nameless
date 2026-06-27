# Phase 4: Cited Claim Mining + Cross-Reference — SUMMARY

**Status:** Code-complete (course/learning build mode — written, reviewed, fakes-only tests RUN here;
real Claude extraction is env-gated, NOT run). EXTENDS the existing `knowledge-pipeline/` package.
**Requirements:** KNOW-05, KNOW-06.
**Tests:** **134 passed** on the base env (pydantic + pytest), of which **57 are Phase-4** (77 Phase-3
remain green — nothing regressed).

---

## What was built

The EXTRACT half of the make-or-break two-pass design: turn the Phase-3 snapshot corpus into a registry
of **atomic, individually-cited claims**, grouped into **preserved consensus and conflict** — extraction
+ grouping only, **ZERO synthesis** (no opinionated default, no merged "best way", no SKILL.md — Phase 5).

Mirrors the Phase-3 pattern exactly: typed pydantic domain → pure testable core → ports with REAL + FAKE
adapters → pure orchestration → compact CLI → fixtures → fakes-only pytest → LEARNING/README.

## File map (all under `knowledge-pipeline/`)

**Typed domain (KNOW-05/06)**
- `src/knowledge_pipeline/domain/claims.py` — `Claim` (claim_text, technique, stage, genre[], stance,
  confidence + citation: source_video_id, timestamp_ms, quote, caption_source; computed `id`/`topic`),
  `ClaimCluster` (topic, consensus[], conflicts[], `sides()`, distinct-source computed fields), `ClaimStats`.
- `src/knowledge_pipeline/domain/keys.py` — pure normalization: `normalize_text`/`normalize_key`/
  `topic_key`/`compute_claim_id` (content-addressed id; idempotency + dedup substrate).

**Pure core (no I/O, no `anthropic`)**
- `pure/extraction_schema.py` — `EXTRACTION_TOOL_SCHEMA` (closed `emit_claims` JSON Schema),
  `parse_extractor_output` (model output → bound, re-anchored Claims), `rule_based_extract` (LLM-free fake).
- `pure/citation.py` — `verify_citation` → `CitationCheck` (verified | drift | not_found | empty); the
  precursor to Phase 5's hard gate.
- `pure/cross_reference.py` — `cross_reference` (consensus XOR preserved conflict; distinct-source corroboration).
- `pure/claim_dedup.py` — `dedup_claims` (exact + same-source near-dup; never cross-source; optional semantic hook).
- `prompts.py` — `EXTRACTION_SYSTEM_PROMPT_V1` + `EXTRACTION_PROMPT_VERSION` (the careful, versioned prompt).

**Ports + adapters** (`ports.py` extended; `adapters/__init__.py` exports the stdlib-safe ones)
- `ClaimExtractor` → `adapters/claim_extractor_anthropic.py` (REAL, Claude `claude-opus-4-8` forced
  tool-use, lazy `import anthropic`) + `adapters/claim_extractor_fake.py` (scripted + rule-based).
- `ClaimStore` → `adapters/claim_store_sqlite.py` (REAL, extends `registry.sqlite`, sqlite stdlib) +
  `adapters/claim_store_mem.py` (in-memory fake).
- `SimilarityIndex` → `adapters/similarity_embeddings.py` (REAL, lazy sentence-transformers) +
  `adapters/similarity_keyword.py` (Jaccard fake).
- `claims_sql.py` — additive DDL (`claims`, `clusters`, `cluster_members`) extending the Phase-3 registry.

**Orchestration + CLI + fixtures**
- `mining_pipeline.py` — `MiningPipeline` (extract → verify citation → dedup → globally cross-reference →
  persist; idempotent; `MineTarget`/`MiningConfig`/`MiningReport`).
- `claims_cli.py` — `claims mine | list (--by-stage/--by-genre/--conflicts) | show <id> | stats`.
- `claim_fixtures.py` + `fixtures/claims/*.json` — a real 3-source consensus set (sub-bass high-pass
  across deep-house/R&B/amapiano) **and** the amapiano log-drum **FLEX-vs-layered conflict**.

**Tests (fakes-only, base env)** — `tests/test_claim_schema.py`, `test_claim_keys.py`, `test_citation.py`,
`test_cross_reference.py`, `test_claim_dedup.py`, `test_extraction_schema.py`, `test_claim_store.py`,
`test_mining_pipeline.py`, `test_claims_cli.py`, `test_no_synthesis_boundary.py`; `tests/conftest.py`
extended (`make_claim`, `claim_corpus`, `mining_plane`).

**Docs / packaging** — `LEARNING.md` (+ Phase-4 §§7–12), `README.md` (Phase-4 surface, RAM-safe vs
env-gated commands, token-cost note), `pyproject.toml` (`claims` script; `extract`/`embed` extras; v0.4.0).

## Requirement coverage

- **KNOW-05 — atomic cited claims, typed production-stage × genre schema, no synthesis.** `Claim` is the
  typed atom (every field extracted-or-citation; `id`/`topic` computed). The real extractor uses forced
  structured tool-use; `parse_extractor_output` binds identity/citation from the transcript (not the model)
  and re-anchors the quote's timestamp. `verify_citation` checks the quote against the snapshot
  (positive/drift/not_found). `claims show <id>` traces a claim to its source quote + ts + video.
- **KNOW-06 — cross-reference consensus + conflict preserved.** `cross_reference` groups by topic and
  partitions into consensus XOR conflicts; a contested topic keeps **both camps** (never collapsed),
  corroboration counts **distinct sources**. Persisted via `cluster_members.side`; surfaced by
  `claims list --conflicts` and the conflict fixture.

## The no-synthesis boundary — as a tested invariant

The defining discipline of Phase 4 is pinned by tests, so a future change that crosses it fails CI:
- `test_no_synthesis_boundary.py::test_schema_carries_no_synthesized_fields` — `Claim`/`ClaimCluster`
  have no `default`/`recommended`/`best`/`summary`/`verdict`/`winner` field; the cluster keeps BOTH
  `consensus` and `conflicts` as first-class lists.
- `..::test_cross_reference_never_collapses_a_conflict` and
  `test_cross_reference.py::test_contested_topic_preserves_both_sides_and_picks_no_winner` — the conflict is
  preserved (2 claims, consensus empty), never averaged into one "answer".
- `..::test_fake_extractor_emits_only_grounded_atoms_never_a_cluster` — the fake emits only `Claim` atoms
  whose quotes are verbatim transcript text; it never returns a cluster or a merged default.
- `..::test_anthropic_and_embeddings_are_not_imported_on_the_fake_path` — a clean subprocess proves
  `anthropic`/`sentence_transformers` never load on the fakes path (the base env runs the whole suite).

## Verification (honest: reviewed/run vs env-gated)

**Run here (RAM-safe, on the base env — pydantic + pytest only):**
- `cd knowledge-pipeline && PYTHONPATH=src python -m pytest -q` → **134 passed** (57 Phase-4).
- Offline e2e through the real `SqliteClaimStore` (sqlite is stdlib) + `FakeClaimExtractor`:
  `PYTHONPATH=src python -m knowledge_pipeline.claims_cli mine --fixtures --corpus-root ./demo-claims`
  → `claims=7 clusters=4 contested=1`; `... list --conflicts` shows `[flex-synth vs layered-samples]`;
  `... show <id>` traces to the source quote + ts; `... stats` → `citation_verified: 7/7`.

**Env-gated (NOT run here — needs install + key + tokens):**
- Real Claude extraction: `uv sync --extra extract`, `export ANTHROPIC_API_KEY=...`,
  `uv run claims mine --corpus-root ./.nameless-knowledge/corpus`. Model `claude-opus-4-8`, forced
  `emit_claims` tool-use. **Token cost (estimate, not a benchmark):** ~$5/$25 per 1M in/out; a transcript
  is typically <2k input tokens, so a single extraction is well under ~$0.05 — a few cents per video; the
  budget risk is volume × re-runs, controlled by content-addressed idempotent upsert.
- Optional semantic dedup: `uv sync --extra embed` (sentence-transformers; local compute, not metered).

**The LLM was NOT run.** No Anthropic API call was made, the `anthropic` SDK was not installed, and no
tokens were spent. The complete, correct real adapter + the careful versioned prompt are the deliverable;
the fakes-only suite verifies the entire control flow around them.
