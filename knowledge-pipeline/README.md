# `knowledge-pipeline/` — Nameless offline knowledge pipeline (ingestion + claim mining + skill synthesis)

The build-time authoring tool that grounds Nameless's craft (PRD M0 foundation, research
`ARCHITECTURE.md`). It runs in three stages, all build-time, all writing into one local `registry.sqlite`
(Phase 5 also writes `skills/production/**/SKILL.md` files):

- **Phase 3 — ingestion stage** (`corpus` CLI): discover north-star production tutorials, fetch their
  transcripts **locally** with throttling + snapshot-on-ingest, fall back to ASR when captions are
  missing/poor, score each source's **extractability** (flagging visual-only / low-signal rather than
  faking it), and register everything in a local **corpus**.
- **Phase 4 — cited claim mining + cross-reference** (`claims` CLI): mine the snapshot corpus into a
  registry of **atomic, individually-cited claims** (Claude tool-use), verify each citation against the
  snapshot, and cross-reference them into **preserved consensus and conflict** — **extraction only, ZERO
  synthesis**. This is the EXTRACT half of the make-or-break two-pass design that defeats GIGO.
- **Phase 5 — layered skill synthesis + the hard citation gate** (`skills` CLI): synthesize the cited-claim
  layer into **authored, layered Claude Skills** (opinionated default + preserved consensus/conflict, every
  claim cited) — **synthesizing ONLY over the claim set** — then run a pure, programmatic **citation gate**
  that REJECTS any draft with an invented number, an uncited assertion, or an untraceable citation. Skills
  emit as `status: draft` and ship only after a **human spot-audit** (`skills audit` → `skills promote`).
  This is the SYNTHESIZE half — where "quality in, quality out" becomes a check, not a hope.

This is a **sibling of `workers/`, NOT a runtime plane.** It runs on your machine when you want to
(re)build the corpus/claims, writes files + a local `registry.sqlite`, and then disappears from the
runtime picture. It shares **no tables and no read path** with the runtime Postgres fragment graph — the
two knowledge layers are deliberately separate.

- Requirements covered: **KNOW-01..04** (Phase 3 — discovery, fetch+snapshot, ASR+extractability, ≥100
  north-star target); **KNOW-05** (atomic cited claims, typed production-stage × genre schema, no
  synthesis), **KNOW-06** (cross-reference consensus + conflict preserved as first-class data); **KNOW-07**
  (layered synthesis over the claim set), **KNOW-08** (the hard citation gate — no invented numbers),
  **KNOW-09** (authored skills, P1 north-star cells first, `skills/production/`), **KNOW-11** (human
  spot-audit + gated promotion).
- The ideas (captions, IP-blocking, extractability, snapshots, faster-whisper **and** structured tool-use
  extraction, the extract-then-synthesize split, citation discipline, consensus/conflict, semantic-dedup
  trade-offs) are taught in depth in **[`LEARNING.md`](./LEARNING.md)**.

## Design: ports & adapters (why the tests need no network, ASR, or real time)

Every network/heavy/time dependency sits behind a `typing.Protocol` **port** with a REAL adapter (heavy
imports lazy) and a deterministic **FAKE**. The orchestration (`IngestPipeline`) is **pure** over those
ports — it contains no yt-dlp, no youtube-transcript-api, no faster-whisper, no sqlite, no wall clock.

| Port (`ports.py`) | Real adapter (env-gated) | Fake / stdlib adapter (tests) |
|---|---|---|
| `DiscoverySource` | `YtDlpDiscoverySource` (yt-dlp `ytsearch`) | `FixtureDiscoverySource` |
| `TranscriptFetcher` | `YoutubeTranscriptFetcher` (youtube-transcript-api → yt-dlp subs) | `FixtureTranscriptFetcher` |
| `Transcriber` (ASR) | `FasterWhisperTranscriber` (faster-whisper + yt-dlp audio) | `FixedTextTranscriber` |
| `CorpusStore` | `FilesystemCorpusStore` (snapshots + `registry.sqlite`) | `InMemoryCorpusStore` |
| `Clock` | `SystemClock` | `FakeClock` (virtual time) |
| `RateLimiter` | `IntervalRateLimiter` (interval + jitter) | `NoOpRateLimiter` |
| `ClaimExtractor` (P4) | `AnthropicClaimExtractor` (Claude tool-use, `claude-opus-4-8`) | `FakeClaimExtractor` (scripted + rule-based) |
| `ClaimStore` (P4) | `SqliteClaimStore` (extends `registry.sqlite`) | `InMemoryClaimStore` |
| `SimilarityIndex` (P4) | `EmbeddingSimilarityIndex` (sentence-transformers) | `KeywordSimilarityIndex` (Jaccard) |
| `SkillSynthesizer` (P5) | `AnthropicSkillSynthesizer` (Claude `emit_skill` tool-use) | `FakeSkillSynthesizer` (deterministic template) |
| `SkillStore` (P5) | `FilesystemSkillStore` (`skills/production/**/SKILL.md` + `registry.sqlite`) | `InMemorySkillStore` |

The **pure core** is the testable heart: `query_grid`, `extractability_score`, `fallback_decision`,
`snapshot_record`, `dedup`, a VTT parser (Phase 3); `verify_citation`, `cross_reference`, `dedup_claims`,
the `emit_claims` extraction schema (Phase 4); **plus `cell_selection` (P1 north-star ordering),
`citation_gate` (the hard reject gate), `synthesis_template` (deterministic layered synthesis),
`layered_emitter` (SKILL.md), `audit` (coverage + spot-audit), and the `emit_skill` synthesis schema
(Phase 5)** — all deterministic, no I/O, no `anthropic`. **The citation gate is pure and is NOT a port**:
it must judge the real Claude synthesizer and the fake identically — there is no "test gate".

```
src/knowledge_pipeline/
  domain/      models.py (VideoRef, RawTranscript+segments, SnapshotRecord, ExtractabilityResult, CorpusEntry, …)
               claims.py  (Claim, ClaimCluster, ClaimStats — the typed KNOW-05/06 boundary)   [P4]
               skills.py  (ProductionCell, SkillCitation/Section/Draft, AuthoredSkill, P1 grid)   [P5]
               keys.py    (pure normalize_text/normalize_key/topic_key/compute_claim_id · numbers)  [P4/P5]
               genres.py  (the north-star genre x stage grid + artist anchors)
  pure/        P3: query_grid · extractability · fallback · snapshot · dedup · captions · vocab
               P4: citation.py (verify_citation) · cross_reference.py · claim_dedup.py · extraction_schema.py
               P5: cell_selection · citation_gate (the HARD gate) · synthesis_template · layered_emitter ·
                   audit · synthesis_schema (emit_skill)
  prompts.py   versioned claim-extraction (P4) + skill-synthesis (P5) system prompts (extract/synth only,
               never invent numbers, cite everything)
  ports.py     P3: DiscoverySource · TranscriptFetcher · Transcriber · CorpusStore · Clock · RateLimiter
               P4: ClaimExtractor · SimilarityIndex · ClaimStore     P5: SkillSynthesizer · SkillStore
  adapters/    fakes + stdlib (eager): *_fake.py · corpus_mem · clock_fake · rate_limiter ·
               claim_extractor_fake · claim_store_mem · claim_store_sqlite · similarity_keyword ·
               skill_synthesizer_fake · skill_store_mem · skill_store_fs (real, sqlite stdlib)   [P5]
               real, heavy-imports LAZY: discovery_ytdlp · fetch_youtube · transcribe_whisper · corpus_fs ·
               claim_extractor_anthropic · similarity_embeddings · skill_synthesizer_anthropic (anthropic) [P5]
  registry_sql.py  DDL for registry.sqlite (sources · snapshots · extractability)
  claims_sql.py    additive DDL extending registry.sqlite (claims · clusters · cluster_members)   [P4]
  skills_sql.py    additive DDL extending registry.sqlite (skills · skill_citations)               [P5]
  pipeline.py          IngestPipeline    — discover → dedup → fetch+fallback → snapshot → score → register
  mining_pipeline.py   MiningPipeline    — extract → verify citation → dedup → cross-reference → persist   [P4]
  synthesis_pipeline.py SynthesisPipeline — select cells → synthesize → GATE → emit → store (draft)        [P5]
  cli.py           `corpus discover | ingest | list | show | stats`
  claims_cli.py    `claims mine | list | show | stats`                                            [P4]
  skills_cli.py    `skills synthesize | list | show | audit | promote | stats`                    [P5]
  fixtures.py · claim_fixtures.py   load fixtures/{transcripts,claims}/*.json into the fake-adapter inputs
fixtures/transcripts/  6 fixture videos (incl. visual-only + sparse/low-signal)
fixtures/claims/       5 fixtures: a 3-source consensus set + the amapiano FLEX-vs-layered conflict
../skills/production/  the AUTHORED, COMMITTED example skills emitted by `skills synthesize --fixtures`
                       (drums/amapiano = the FLEX-vs-layered conflict; bassline/* = 3-source consensus; …)
tests/        fakes-only pytest suite — P3 (ingestion) + P4 (claim mining) + P5 (cell selection, the
              citation gate PASS+REJECT, synthesis-only invariant, layered emitter, skill store [mem +
              real fs], audit/promote, synthesis e2e, skills CLI, no-synthesis boundary). 201 tests, base env.
```

## Build mode (course/learning project) — code-complete, NOT run live on the build box

This machine cannot install `faster-whisper` and must not hit YouTube (4GB / no-Docker; ingestion must
run from a home IP). The code is complete and real; the network/ASR paths are **env-gated** below.
**Nothing here was installed or fetched from YouTube on the build box.**

## Verification

### RAM-safe (runs anywhere with the light base — this is what was actually run)

```bash
cd knowledge-pipeline
uv sync --extra dev          # installs only pydantic + pytest
uv run pytest -q             # 201 tests (P3 + P4 + P5), all on the base env:
                             # P3 — query grid, extractability gate, fallback ladder, snapshot hash/date,
                             #      dedup, throttle-on-fake-clock, corpus store (mem + real sqlite), e2e, CLI
                             # P4 — claim schema + keys, citation verify (positive/drift/not-found),
                             #      cross-reference consensus AND conflict-preservation, claim dedup,
                             #      extraction schema + rule-based fake, claim store, mining e2e, claims CLI
                             # P5 — cell selection (P1 ordering), the CITATION GATE (grounded PASS + every
                             #      reject: invented-number/uncited/nonexistent-source/tampered/ungrounded/rot),
                             #      synthesis-only-over-claims invariant, layered emitter, skill store
                             #      (mem + real fs), audit coverage + reproducible sample, promote (draft→
                             #      promoted), synthesis e2e (incl. a poisoned synthesizer → all rejected),
                             #      skills CLI, the no-synthesis boundary (anthropic never imported)
```

(If not using uv: `pip install pydantic pytest` then `PYTHONPATH=src pytest -q`.)

You can also drive **both stages offline against the bundled fixtures** (no network, no API) — the real
sqlite stores materialize a real `registry.sqlite`:

```bash
# Phase 3 — ingestion
PYTHONPATH=src python -m knowledge_pipeline.cli ingest --fixtures --corpus-root ./demo-corpus
PYTHONPATH=src python -m knowledge_pipeline.cli list   --corpus-root ./demo-corpus --by-genre
PYTHONPATH=src python -m knowledge_pipeline.cli show altpiano_visual_only --corpus-root ./demo-corpus --segments 3

# Phase 4 — cited claim mining (FakeClaimExtractor over the claim fixtures + real SqliteClaimStore)
PYTHONPATH=src python -m knowledge_pipeline.claims_cli mine  --fixtures --corpus-root ./demo-claims
PYTHONPATH=src python -m knowledge_pipeline.claims_cli list  --corpus-root ./demo-claims --conflicts   # both sides preserved
PYTHONPATH=src python -m knowledge_pipeline.claims_cli list  --corpus-root ./demo-claims --by-genre
PYTHONPATH=src python -m knowledge_pipeline.claims_cli show  <CLAIM_ID> --corpus-root ./demo-claims     # trace to source quote + ts + video
PYTHONPATH=src python -m knowledge_pipeline.claims_cli stats --corpus-root ./demo-claims

# Phase 5 — layered skill synthesis + the hard citation GATE (FakeSkillSynthesizer + real FilesystemSkillStore)
#   self-contained: mines the claim fixtures, synthesizes, GATES, and writes real SKILL.md files to <root>.
PYTHONPATH=src python -m knowledge_pipeline.skills_cli synthesize --fixtures --corpus-root ./demo-skills --skills-root ./demo-skills
PYTHONPATH=src python -m knowledge_pipeline.skills_cli list   --corpus-root ./demo-skills --skills-root ./demo-skills --by-genre
PYTHONPATH=src python -m knowledge_pipeline.skills_cli show   <SKILL_ID> --corpus-root ./demo-skills --skills-root ./demo-skills --body  # the layered SKILL.md
PYTHONPATH=src python -m knowledge_pipeline.skills_cli audit  --corpus-root ./demo-skills --skills-root ./demo-skills --sample 5        # the human spot-audit
PYTHONPATH=src python -m knowledge_pipeline.skills_cli promote <SKILL_ID> --corpus-root ./demo-skills --skills-root ./demo-skills --yes  # human-gated draft→promoted
```

The fixtures carry a real **consensus set** (the sub-bass high-pass corroborated across deep-house, R&B
and amapiano = 3 distinct sources) and the **amapiano log-drum FLEX-vs-layered conflict** (both stances
preserved, never collapsed) — so the offline run demonstrates KNOW-06 directly, and the Phase-5 synthesis
turns them into authored, gated, draft SKILL.md files (KNOW-07/08/09). **The committed example skills under
`../skills/production/` were produced exactly this way — by the fake synthesizer, with no API call** — and
because the pipeline only writes files for drafts that PASS the gate, their existence is proof the gate
passed. `drums/amapiano/SKILL.md` shows the opinionated default on one camp with both camps preserved
beside it; `bassline/deep-house/SKILL.md` shows a HIGH-confidence 3-source consensus default.

### Env-gated (the LIVE ingest — NOT run here; run from your home machine)

```bash
# 1. Install the network + ASR extras (yt-dlp ships ~biweekly — PIN THE EXACT version first):
uv sync --extra ingest --extra asr

# 2. Inspect the discovery PLAN (grid + anchors → candidate videos) without ingesting:
uv run corpus discover --limit 5

# 3. Run the real ingest from your HOME IP, throttled (this fetches transcripts + ASR-transcribes):
uv run corpus ingest --limit 5 --corpus-root ./.nameless-knowledge/corpus --min-interval 2.5 --jitter 0.5
#    add --no-asr to skip the GPU-cost faster-whisper fallback (uncaptioned videos then record as reject)

# 4. Inspect the resulting corpus (these read the registry — no network, runnable anywhere):
uv run corpus list  --corpus-root ./.nameless-knowledge/corpus --by-genre
uv run corpus list  --corpus-root ./.nameless-knowledge/corpus --by-extractability --verdict keep
uv run corpus stats --corpus-root ./.nameless-knowledge/corpus           # is it ≥100 and north-star-concentrated?
uv run corpus show <VIDEO_ID> --corpus-root ./.nameless-knowledge/corpus --segments 5
```

KNOW-04's "≥100 videos" is reached by the live ingest: the default grid is `|genres| x |stages|` = 4 × 11
= 44 grid queries + artist anchors, each fanned to `--limit` results, deduped — comfortably >100 unique
candidate videos concentrated on the north-star fusion. The bundled fixture corpus (6 videos) is for
tests + the offline demo, not the count.

### Env-gated (LIVE claim mining — Phase 4 — NOT run here)

Live mining calls Claude (`claude-opus-4-8`) with forced `emit_claims` tool-use, once per `keep`/
`low_signal` corpus video. **This is metered spend** and is never run on the build box.

```bash
# 1. Install the extractor extra (PIN the exact anthropic version first):
uv sync --extra extract

# 2. Set your key, then mine the snapshot corpus into cited claims (idempotent — re-mining upserts):
export ANTHROPIC_API_KEY=sk-ant-...
uv run claims mine --corpus-root ./.nameless-knowledge/corpus                 # all keep/low_signal videos
uv run claims mine --corpus-root ./.nameless-knowledge/corpus --video <VIDEO_ID>   # a single video
uv run claims mine --corpus-root ./.nameless-knowledge/corpus --require-citation   # drop claims whose citation fails

# 3. Inspect (these read the registry — no API, runnable anywhere):
uv run claims list  --corpus-root ./.nameless-knowledge/corpus --by-stage
uv run claims list  --corpus-root ./.nameless-knowledge/corpus --conflicts       # contested topics, both sides
uv run claims show  <CLAIM_ID> --corpus-root ./.nameless-knowledge/corpus        # trace to source quote + ts
uv run claims stats --corpus-root ./.nameless-knowledge/corpus
```

**Token-cost note (estimate, not a benchmark).** `claude-opus-4-8` is ~**$5.00 / 1M input** and
~**$25.00 / 1M output** tokens. One tutorial transcript is typically **<2k input tokens**, and a claims
array is small output, so a single extraction is well under **~$0.05** — call it a **few cents per video**.
The budget risk is therefore *volume × re-runs*, which the content-addressed, idempotent upsert controls
(re-mining an unchanged corpus does not re-extract identical claims into duplicates, but it **does** re-call
the API per targeted video — scope `--video` or re-mine deliberately). Optional `--extra embed`
(sentence-transformers) for semantic dedup is local compute, not metered.

### Env-gated (LIVE skill synthesis — Phase 5 — NOT run here)

Live synthesis calls Claude (`claude-opus-4-8`) with forced `emit_skill` tool-use, once per authored cell,
synthesizing ONLY over that cell's mined claims. **This is metered spend**; the build box runs only the
deterministic fake (the committed example skills above). The hard citation gate runs identically over the
real and fake output — a draft Claude returns that asserts an uncited number is REJECTED just the same.

```bash
# 1. Install the extractor extra (shared with Phase 4; PIN the exact anthropic version first):
uv sync --extra extract

# 2. Set your key, then synthesize the P1 north-star cells from the mined claim layer (idempotent upsert):
export ANTHROPIC_API_KEY=sk-ant-...
uv run skills synthesize --corpus-root ./.nameless-knowledge/corpus --skills-root .   # P1 cells -> draft SKILL.md
uv run skills synthesize --corpus-root ./.nameless-knowledge/corpus --skills-root . --all   # every evidenced cell

# 3. Audit, then promote what survives the human spot-audit (these read the registry/files — no API):
uv run skills list   --corpus-root ./.nameless-knowledge/corpus --by-genre
uv run skills audit  --corpus-root ./.nameless-knowledge/corpus --sample 5            # coverage + flags
uv run skills show   <SKILL_ID> --corpus-root ./.nameless-knowledge/corpus --body     # review against citations
uv run skills promote <SKILL_ID> --corpus-root ./.nameless-knowledge/corpus --yes     # human-gated draft→promoted
```

A single skill is a small output (a few cited sections), so per-cell synthesis is a few cents; the budget
risk is again *cells × re-runs*, controlled by the cell-addressed idempotent upsert. The citation gate, the
emitter, the audit, and `promote` are **pure / local** — only `synthesize` (live) is metered.

## ToS / local-first (read before the live ingest)

- `youtube-transcript-api` and `yt-dlp` are **unofficial** and technically against YouTube's ToS. At
  personal research scale (~100–300 videos, occasional, from a home IP) this is the de-facto standard and
  low-risk — but it is **a known constraint, not a sanctioned API**. The official YouTube Data API
  `captions.download` only returns captions for videos *you own*, so it is useless for tutorial channels.
- **Run ingestion from your local/home (residential) IP.** Datacenter/cloud IPs (AWS/GCP/Azure) get
  `RequestBlocked` almost instantly. This project is local-first, so this is free insurance — the GPU
  worker plane is for already-fetched audio, not for ingestion. Do **not** run `corpus ingest` from a
  cloud worker without budgeting rotating *residential* proxies (ToS-adjacent; not a clean portfolio story).
- The throttle (`--min-interval` / `--jitter`) is there to be polite and dodge 429s. Treat ingest as a
  slow background batch; it is **idempotent** (content-hashed snapshots) so a block mid-run loses no work.

## Cross-stage seam

- **Phase 3 → Phase 4.** The corpus (immutable snapshot files + `registry.sqlite`) is the input to claim
  mining. The per-segment timestamps are the substrate Phase 4 cites as `video_id @ ts`; the snapshot hash +
  retrieval date keep those citations auditable even after a channel takedown.
- **Phase 4 → Phase 5 (now implemented).** The `claims` + `clusters` tables (atomic cited claims, grouped
  into preserved consensus/conflict) are the input to **synthesis + the hard citation gate**. Phase 5
  decides an opinionated default and authors `SKILL.md`, but **only over this extracted claim set** — it
  cites nothing Phase 4 didn't extract, and the pure `citation_gate` (which reuses Phase-4 `verify_citation`)
  is its non-negotiable reject gate: an invented number or an untraceable citation is REJECTED, never
  shipped. The extract-then-synthesize boundary is what makes the skills trustworthy.
- **Phase 5 → M1 (PRD §12).** The authored, human-promoted `skills/production/<stage>/<genre>/SKILL.md`
  files are what the M1 arranger/mixer agents load to ground their craft. They are version-controlled prose
  + citations — token-cheap until triggered, opinionated, and auditable — the signature architectural bet
  over a RAG vector store.

## Licensing note

This stage bundles no models. The env-gated tools carry their own terms (yt-dlp / youtube-transcript-api
unofficial; faster-whisper/CTranslate2 permissive). See the repo `CLAUDE.md` "License Constraints" and
`.planning/research/STACK.md` before any commercial use.
