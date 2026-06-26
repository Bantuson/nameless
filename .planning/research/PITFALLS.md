# Pitfalls Research

**Domain:** Audio-native AI music composition — tutorial-distilled knowledge layer + reference/sampling grounding + melody-conditioned generation, solo/local-first/portfolio
**Researched:** 2026-06-26
**Confidence:** HIGH (most pitfalls verified against tooling docs and 2025–2026 reports; sparse-genre and eval-threshold items are MEDIUM — judgment-based)

> This file goes deeper than PRD §16. §16 names four risks (niche-genre weakness, latency, model churn, directional token estimates). This document treats those as baseline and concentrates on the **failure modes of the three NEW capabilities** added at init: the tutorial-knowledge layer, reference-track context, and attributed sampling — plus the audio-ML and token-budget realities that bite a solo build.

---

## Critical Pitfalls

### Pitfall 1: Transcript ingestion silently degrades to garbage (auto-caption noise, missing captions, visual-only knowledge)

**What goes wrong:**
The knowledge layer is built from "100+ YouTube tutorials," but YouTube auto-captions are lossy in exactly the ways that matter here: producer jargon ("sidechain the log drum," "Serum," "OTT," "300 Hz," "amapiano shaker") is mis-transcribed; numbers and units (Hz, dB, BPM, ms) are frequently wrong; speaker overlap and music beds corrupt segments. Worse, a large fraction of production knowledge is **visual, not spoken** — the producer drags a filter cutoff, A/Bs two presets, or points at a piano roll while saying "like this." The transcript captures "and then you just do that and boom" with zero recoverable craft. Many tutorial channels have **no captions at all** (or auto-captions disabled), and target genres skew toward **code-switched / non-English** speech (amapiano/SA producers mixing English with isiZulu/Sesotho/Afrikaans slang), which auto-caption mangles or drops.

**Why it happens:**
Builders assume "transcript = the lesson." They count videos, not extractable claims. The pipeline ingests whatever the API returns and never measures whether a transcript actually contains teachable, grounded technique versus filler.

**How to avoid:**
- Treat transcript quality as a **gating feature, not an input**. Compute a per-video "extractability score" before distillation: caption type (manual > auto), language match, density of recognized domain terms (match against a producer-jargon lexicon), presence of numeric parameters. Reject or down-weight low-scoring videos.
- **Do not pretend visual knowledge was captured.** Tag every distilled claim with a modality flag (spoken-explicit vs. inferred). When a technique is demonstrated but not verbalized, the honest output is "this video shows X exists but does not explain it" — feed that to the gap tracker, not to a SKILL.md as if it were taught.
- Prefer **manually-captioned** videos and channels in the discovery query; keep a fallback to Whisper-based re-transcription of the audio for high-value videos with bad/missing captions (Whisper handles producer jargon and code-switching far better than YouTube auto-captions, at GPU cost).
- For code-switched SA content, accept partial coverage and lean harder on the audio-analysis grounding (Pitfall 7) rather than forcing a bad transcript through the LLM.

**Warning signs:**
- Distilled skill claims that are vague ("add some flavor," "make it slap") with no parameter.
- Citations clustering on a few well-captioned channels while target-genre artists are absent.
- Numeric values in skills that don't appear in any source on manual inspection (caption corrupted the number, LLM "fixed" it).

**Phase to address:** M0 — Transcript Ingestion (the first sub-phase of the production-knowledge layer). Build extractability scoring before any distillation runs.

---

### Pitfall 2: YouTube ToS / IP-blocking / rate-limiting kills ingestion mid-build (and channel takedowns rot citations)

**What goes wrong:**
Scraping transcripts at 100+ video scale trips YouTube's bot defenses. **Verified 2025–2026 reality:** YouTube now blocks most cloud-provider IP ranges (AWS, GCP, Azure, DigitalOcean) outright — `youtube-transcript-api` raises `RequestBlocked`/`IpBlocked` from any cloud worker even though identical code works on a home machine. Volume-based **429 rate-limiting** is the most common production breakage and looks identical to an IP-reputation block. YouTube's 2025–2026 **PoToken** ("proof of origin") bot-detection adds a token an automated script can't easily produce. Separately, scraping transcripts at scale is against YouTube ToS. And because citations point at `video_id + timestamp`, **channel/video takedowns silently rot the evidence trail** — a core promise of the project ("every claim traceable to source video + timestamp") quietly breaks.

**Why it happens:**
The local dev machine works fine, so the builder assumes it scales. They move ingestion to a GPU/cloud worker (where Whisper and Demucs already live) and ingestion dies. Citation rot is invisible until someone audits a claim months later.

**How to avoid:**
- **Run ingestion locally / from a residential IP, not from the cloud worker plane.** This is local-first anyway — keep transcript fetching on the home machine; reserve the GPU worker for Whisper/Demucs/CLAP on already-fetched audio.
- Throttle hard (seconds between requests, jitter, resume-on-failure). Treat ingestion as a slow background batch, not a one-shot. Persist progress so a block doesn't lose work.
- If cloud is unavoidable, budget for **rotating residential proxies** (static proxies get banned after extended use) — but recognize this is ToS-adjacent and not appropriate for a clean portfolio narrative.
- **Snapshot the evidence at ingest time.** Store the raw transcript text + a content hash + retrieval date alongside the `video_id`/timestamp, so a claim stays auditable even after takedown. The citation references your immutable snapshot, with the YouTube URL as a (possibly-dead) pointer.
- Keep ingestion **idempotent and incremental** — re-running must not re-fetch what's already snapshotted.

**Warning signs:**
- Ingestion succeeds locally, fails the moment it runs on the worker.
- Sudden cluster of empty/blocked responses (429 storm) after N videos.
- A spot-check of an old citation 404s and there's no local snapshot to fall back on.

**Phase to address:** M0 — Transcript Ingestion. Bake in local-fetch + snapshot-on-ingest + throttling from the first script.

---

### Pitfall 3: "Garbage in, garbage out" distillation — LLM hallucinates craft, conflates genres, over-generalizes (the user's explicit fear)

**What goes wrong:**
This is the heart of the user's "quality in, quality out" anxiety, and it is the single highest-stakes pitfall. When an LLM synthesizes technique across 100 noisy transcripts, it characteristically:
- **Fabricates specificity** where evidence is thin — inventing exact Hz/dB/ratio values that no source stated, because confident-sounding numbers read as expertise.
- **Conflates genres** — amapiano log-drum technique bleeds into the "deep house bass" skill; an R&B vocal-chain tip gets generalized into a universal "mixing" rule it doesn't belong to.
- **Over-generalizes from one source** — a single producer's idiosyncratic habit becomes "the way to do it."
- **Handles contradictions badly** — when two videos disagree (very common in production: everyone has a different compression philosophy), the LLM either silently averages them into mush, picks one arbitrarily, or asserts a false consensus.
- **Citation drift** — attaches a real citation to a claim that source didn't actually make, because the claim "feels" supported. This is the most corrosive failure: it *looks* auditable but isn't.

The skills then teach the arranger/mixer **confident wrong craft**, and because the agents trust the SKILL.md, bad craft propagates into every generation. Garbage in, garbage out — exactly the failure the project exists to avoid.

**Why it happens:**
LLMs are fluent and reward-shaped toward confident, complete-sounding answers. A naive "summarize these transcripts into a skill" prompt optimizes for readability, not faithfulness. There's no separation between *what was said* and *what the model concluded*.

**How to avoid:**
- **Extraction before synthesis, as two separate passes.** Pass 1: extract atomic, individually-cited claims verbatim-grounded ("Video X @ 4:32 says: high-pass the log drum around 30–40 Hz"). Pass 2: synthesize *only over the extracted claim set*, never over raw transcripts. The synthesizer can only cite claims that exist in Pass 1's table — structurally prevents citation drift.
- **Make the layered output the PROJECT decision, not an aspiration.** PROJECT.md already commits to "opinionated default PLUS preserved consensus/conflict evidence, every claim traceable." Enforce it: every skill claim carries (a) the opinionated default, (b) supporting source count, (c) dissenting sources verbatim. A claim with **one source and no corroboration is flagged LOW-confidence**, not promoted to a default.
- **Quote-and-cite verification gate.** For each synthesized claim, programmatically check the cited timestamp's transcript text actually contains the supporting tokens (string/embedding overlap). Claims that fail are demoted or dropped. This catches both hallucinated specificity and citation drift.
- **Never let the LLM invent numbers.** Numeric parameters must be extracted spans, not generated. If no source gave a number, the skill says "sources don't specify" — that honesty is the product.
- **Contradiction is data, not noise.** When sources disagree, preserve the disagreement as a first-class "conflict" object with both sides. The agent at runtime can then reason about tradeoffs instead of inheriting a laundered false consensus.
- **Human spot-audit before promotion.** Solo build — sample 10–20% of distilled claims against their sources manually before a skill is allowed to ship to the agents. Cheap insurance against systemic distortion.

**Warning signs:**
- Skills full of precise numbers but conflict-evidence sections are empty (synthesis ate the disagreement).
- A claim's cited timestamp, when you actually watch it, doesn't say that.
- Every genre's skill reads suspiciously similar (genre conflation / over-generalization).
- Single-source claims presented with the same confidence as 10-source consensus.

**Phase to address:** M0 — Knowledge Distillation. This is the make-or-break phase; design the two-pass extract→synthesize pipeline + verification gate + layered output here. Flag for **deep, dedicated planning** — do not let it be a thin "summarize" step.

---

### Pitfall 4: Sparse-genre decomposition misleads (alternative piano reconstructed from wrong parents)

**What goes wrong:**
Alternative piano (newer amapiano subgenre via Ben Produces, Liyana Ricky, Lowbass Djy) is under-tutorialized, so the chosen fallback is **decompose into parent techniques** (amapiano groove/log-drum + jazzy/soulful piano + deep-house space). Decomposition misleads when:
- **The genre's identity is in what the parents *omit or break*, not their sum.** A subgenre often defines itself by *subverting* its parents (sparser arrangement, a specific swing, a deliberately "wrong" chord voicing). Reassembling from parent techniques reconstructs the cliché, not the genre — you get "generic amapiano + generic jazz piano," which is precisely the soulless average the project is trying to beat.
- **Parent weighting is guessed, not measured.** How much amapiano vs. how much deep-house? The decomposition has no ground truth, so the LLM picks plausible-sounding ratios that may be wrong.
- **Naming a parent the model knows well pulls the output toward that parent's dominant training prior** (deep house is heavily documented; alt-piano is not), so the well-documented parent silently dominates.

**Why it happens:**
Decomposition is the only available move when tutorials are absent, and it feels rigorous. But "sum of documented parents" is a hypothesis about the genre, not a measurement of it.

**How to avoid:**
- **Decomposition proposes; audio analysis disposes.** Treat the parent-technique decomposition as a *hypothesis* that must be validated against the artists' actual released tracks (the second fallback). Where the CLAP/feature signature of real Ben Produces / Liyana Ricky / Lowbass Djy tracks **disagrees** with the decomposition, the audio wins. Don't let decomposition stand alone.
- **Measure the parent blend, don't guess it.** Use feature/CLAP distances from the real tracks to *estimate* how the subgenre sits relative to its parents, rather than asserting a ratio.
- **Capture the negative space.** Explicitly note what the subgenre *doesn't* do versus its parents (density, tempo band, voicing choices) — the omissions are often the identity.
- **Hold sparse-genre skills at lower confidence and label them as such**, so the arranger treats them as softer guidance than well-grounded genres.

**Warning signs:**
- The alt-piano skill is indistinguishable from "amapiano skill + piano skill" concatenated.
- Decomposition asserts blend ratios with no citation to a measurement.
- Generated alt-piano output sounds like textbook deep house or textbook amapiano, never the target artists.

**Phase to address:** M0 — Sparse-genre grounding (sits inside the Knowledge Distillation phase but needs its own treatment). Couple it to the audio-analysis pipeline so the two fallbacks cross-check each other.

---

### Pitfall 5: Audio-analysis grounding over-claims (CLAP and DSP features asserting craft they can't see)

**What goes wrong:**
The second sparse-genre fallback — and the reference-track layer — lean on CLAP embeddings + DSP features to extract "real sonic signatures." This over-claims when:
- **CLAP is coarse.** Verified: zero-shot CLAP classification is subpar versus supervised methods, language supervision helps *tagging* but is "less useful for genre classification," and CLAP struggles to generalize beyond its training prompt vocabulary. So "the CLAP embedding says this is the vibe" is a weak, noisy signal for *fine-grained* subgenre distinctions — exactly what alt-piano needs.
- **DSP features describe surface, not craft.** Tempo, key, LUFS, chroma, stereo width are measurable, but they don't encode *why* a track works (arrangement choices, groove feel, tension/release). Turning a feature vector into a confident "sonic signature" attributes intent the analysis never measured.
- **The LLM "vibe description" (mood/space/era/texture) hallucinates** on top of the embedding — it's an LLM narrating a vector, and it will produce evocative prose whether or not it's grounded.

**Why it happens:**
Numbers feel objective. A 512-dim embedding and a LUFS reading look like ground truth, so the pipeline treats derived descriptions as fact rather than as a lossy, biased measurement.

**How to avoid:**
- **Restrict audio analysis to what it actually measures well, and stop there.** Tempo, key, loudness, tonal balance, stereo width, broad CLAP-nearest-genre — yes. "This track's emotional intent is melancholic nostalgia" — only as clearly-labeled LLM interpretation, never as a measured sonic target. PROJECT.md already draws this line for reference tracks ("measurable non-melodic sonic targets" vs. "vibe description"); enforce the same discipline in sparse-genre grounding.
- **Aggregate, don't single-shot.** A signature from one track is noise; a signature from many tracks by the same artist, where features *converge*, is signal. Report variance, not just centroid.
- **Validate CLAP genre claims against ground truth** (artist/genre labels you trust) before relying on them; calibrate how much weight CLAP gets per genre.
- Keep measured targets (drive generation/mix) and interpreted vibe (human-facing context) in **separate fields with different trust levels**, so the agent never conditions generation on an LLM's poetic guess.

**Warning signs:**
- Vibe descriptions are vivid and specific but the underlying features are near-identical across very different tracks (LLM is confabulating).
- Sparse-genre "signature" derived from 1–2 tracks.
- CLAP-driven genre tags that contradict the obvious genre.

**Phase to address:** M0 — Reference-track layer + Sparse-genre grounding (shared audio-analysis pipeline). Define the measured-vs-interpreted boundary as a schema constraint.

---

### Pitfall 6: The cloning boundary leaks — "style-only conditioning" quietly becomes melodic/structural copying

**What goes wrong:**
The hard non-negotiable: reference tracks and samples must **never recreate or clone** the source — only style/atmosphere conditioning and explicitly-attributed samples. This boundary leaks in subtle, dangerous ways:
- **Melody-conditioned generators ARE designed to follow melody.** MusicGen-Stem / MuseControlLite condition on chroma/melody. If a *reference track* (not the user's own fragment) ever reaches the generator's melodic conditioning input, the system will reproduce the reference's melody/harmony — i.e., clone — while the builder believes it's doing "style transfer." The boundary between "the user's hummed hook (OK to condition on)" and "a finished reference song (NOT OK to condition melodically on)" must be enforced in code, not convention.
- **CLAP retrieval can surface a reference's melodic content** if embeddings or features derived from the reference flow into generation conditioning.
- **A promoted sample is literal copied audio.** That's fine *if* it's tracked and attributed — but it's a different legal/ethical object than generated material, and conflating "sampled" provenance with "ai_generated" hides the copy.

**Why it happens:**
The same feature pipeline (chroma, CLAP) serves both "the user's fragment" (condition freely) and "the reference track" (condition on vibe ONLY). One shared code path + one forgotten branch = silent cloning. The PRD's provenance enum makes this *expressible* but doesn't *enforce* the asymmetry.

**How to avoid:**
- **Type the asymmetry into the schema and state machine.** A `reference` / `sampled`-origin fragment must be physically incapable of entering the **melodic/structural conditioning** path. Only `human_recorded` fragments feed melody conditioning. Reference tracks feed *only* the non-melodic target fields (genre, tempo range, LUFS, tonal balance, stereo width, CLAP-vibe). Enforce with Rust's exhaustive matching — the same rigor the PRD already applies to the eval gate.
- **Strip melody from reference-derived context at extraction time.** Never compute or store an f0 contour / detailed chroma *as a conditioning target* from a reference track; extract only the aggregate non-melodic descriptors. What you don't store, you can't accidentally clone from.
- **`sampled` is its own provenance value with mandatory attribution**, distinct from `ai_generated`. A sample is copied audio and must carry source-track/artist/stem/time-range or it cannot be promoted (gate it).
- **Add a clone-detection check to the eval gate.** For any generated fragment, if melodic similarity to a *reference* track (not the user's own source) exceeds a threshold, reject it as a clone-leak. The gate already computes chroma similarity to the source; extend it to a *negative* check against references.

**Warning signs:**
- Generated output that sounds like the reference song's tune, not the user's idea.
- A shared "extract features" function called on both fragments and references with the same output schema.
- `sampled` fragments stored as `ai_generated` or `derived` to "keep it simple."

**Phase to address:** M1 — Generation + Reference layer (and the M0 schema that types provenance). The clone-leak negative check belongs in the M1 eval gate.

---

### Pitfall 7: Sampling copyright/licensing reality understated — even for personal/portfolio

**What goes wrong:**
The project is explicitly personal/portfolio, and PROJECT.md correctly defers "commercial distribution and licensing clearance." The trap is over-reading that deferral as "copyright doesn't apply yet." Reality:
- **Sampling copyrighted recordings is infringement regardless of commercial intent** in most jurisdictions; "personal use" and "it's just a portfolio" are not blanket defenses, and there is **no de-minimis safe harbor** for sound-recording sampling in key precedent (US *Bridgeport*). A portfolio piece is *published* the moment it's on a public portfolio — that's not private use.
- **MusicGen output itself is restricted.** Verified: MusicGen weights are **CC-BY-NC 4.0** (code is MIT, weights are not). Output produced by a NC-licensed model is encumbered for any commercial path — and arguably for a public portfolio that functions as professional self-promotion. The PRD's §15 deferral is honest, but a portfolio is a gray zone, not clearly "personal."
- **Attribution ≠ permission.** A credits sheet is honest and good practice, but crediting a sample does **not** make using it legal. The project's framing ("attribution-clean sampling rather than copy-and-claim-original") is ethically better but must not be mistaken for legal clearance.

**Why it happens:**
"Personal/portfolio" gets treated as a legal safe harbor it isn't. The credits-sheet feature creates a false sense of compliance.

**How to avoid:**
- **Be honest in the system's own framing and docs:** attribution tracks *provenance and honesty*, it does **not** confer rights. Say so in the credits sheet and the project README.
- **Make clearance status a first-class, visible field** even though clearance gating isn't built: tag every sample source with a license/rights status (`copyrighted-uncleared`, `royalty-free`, `own-work`, `unknown`). This is cheap now and makes any future commercial step tractable instead of a forensic nightmare.
- **Prefer royalty-free / Creative-Commons / self-made source material** for samples and reference tracks wherever the work will be public. Keep copyrighted references strictly as private conditioning context that never ships in output.
- **Keep MusicGen's NC license visible in provenance** so a future commercial pivot knows exactly which fragments are model-encumbered (the PRD's swap-the-generator plan depends on knowing this).
- Treat the portfolio as **published**: the safest public output uses your own samples + clear-licensed generators, with copyrighted material confined to private experiments.

**Warning signs:**
- Credits sheet treated as "we're covered."
- No rights-status field on samples; everything is just "attributed."
- Copyrighted reference audio ending up embedded in exported output rather than only informing it.

**Phase to address:** M0 — Sampling library schema (add rights-status field) and the export/credits feature. Provenance honesty is cheap to build in early and expensive to retrofit.

---

### Pitfall 8: Generator licensing + GPU cost/availability sink the M1 budget

**What goes wrong:**
- **MusicGen non-commercial license** (verified CC-BY-NC 4.0 weights) means the *default generator* is a dead end for any commercial future — a swap is inevitable if the project ever monetizes. Building tightly coupled to MusicGen's output characteristics makes that swap painful.
- **GPU reality:** generation + Demucs are GPU-heavy (PRD §15 admits this). Solo builders underestimate that GPU workers are either *expensive when on* or *cold-start-slow when off*, and that hosted inference endpoints have queueing, rate limits, and model-version churn. A "rented GPU worker" line item can quietly dominate cost, and availability gaps stall M1 entirely.

**Why it happens:**
M0 runs on CPU and feels cheap, so GPU cost is out of sight until M1. The non-commercial license feels irrelevant for a portfolio until the project succeeds and the constraint surfaces at the worst time.

**How to avoid:**
- **Keep the generator behind the worker interface** (PRD §16 already mandates this for model churn — apply it equally to license-driven swaps). The control plane, schema, and Skill must not encode MusicGen-specific assumptions.
- **Design GPU work as batch, ephemeral, and resumable.** Spin up, drain the job queue, spin down. NATS JetStream's durability/backpressure (already chosen) makes this natural — don't require a hot GPU.
- **Cache aggressively and dedupe generation requests** — the same conditioning + seed should never pay for GPU twice.
- **Track per-job GPU minutes as a real metric** from the first M1 generation, the way token spend is tracked. Surface it.
- Keep a **CPU-only smoke path** (even if low quality) so development/testing of the pipeline doesn't require GPU for every run.

**Warning signs:**
- Generator-specific fields leaking into the schema or Skill.
- GPU costs discovered only when the bill arrives.
- M1 development blocked whenever the GPU endpoint is unavailable.

**Phase to address:** M1 — Generation worker. Enforce the worker-interface abstraction and GPU cost metering from the first generation job.

---

### Pitfall 9: Eval-gate thresholds mis-tuned for niche genres (false rejects everything OR rubber-stamps junk)

**What goes wrong:**
PRD §16 says niche-genre generation may be weak and the gate "turns silent failure into a visible reject" — good. But the gate's *thresholds* are the hidden trap:
- **Too strict** → every niche-genre generation fails the gate, the arranger regenerates endlessly (burning GPU *and* agent tokens in the loop), and the system produces nothing. The eval gate becomes a wall.
- **Too loose** → junk passes, defeating the entire quality premise.
- **The metrics themselves are weak for niche material.** Chroma-similarity "melody fidelity" and CLAP-alignment are exactly the measures that are *least reliable* on under-documented genres (Pitfall 5: CLAP is coarse on fine-grained genre). So the gate may be measuring the wrong thing precisely where judgment matters most.
- **Thresholds set once, never calibrated**, with no ground-truth of what "good" looks like for alt-piano.

**Why it happens:**
Thresholds are picked by intuition with no labeled examples, and the agent-in-the-loop regeneration hides the cost — you don't see that "the gate works" actually means "it rejected 40 generations and spent the GPU/token budget to get one pass."

**How to avoid:**
- **Calibrate thresholds against labeled examples per genre**, not globally. Use the user's own liked tracks / the real artist tracks (from the sparse-genre pipeline) as positive anchors to set where "pass" should sit for each genre.
- **Make thresholds per-project/per-genre configurable** (PRD already says "configurable per project") — and actually vary them; don't ship one global default.
- **Bound the regeneration loop hard.** Cap attempts; on repeated failure, the arranger must *ask the human* rather than burn budget (the loop already terminates on gate-pass — add a max-attempts terminator on gate-fail). This protects the metered token budget directly.
- **Log every gate score, not just pass/fail**, so you can see the distribution and re-tune. A gate that rejects 90% needs threshold review, not more regeneration.
- **Add a human-override path** for niche genres where the metrics are known-weak — the gate flags, the human adjudicates, the decision is recorded.

**Warning signs:**
- Generation loop runs many attempts before a pass (GPU + token burn).
- Gate pass-rate near 0% or near 100% for a genre.
- All niche-genre fragments rejected; well-documented genres sail through.

**Phase to address:** M1 — Eval gate. Threshold calibration + max-attempts terminator + score logging are part of building the gate, not an afterthought.

---

### Pitfall 10: Token-thin discipline silently violated — the metered budget blows up

**What goes wrong:**
The whole architecture (Skill + CLI + externalized graph, no MCP, audio/features by ID only) exists to keep agent context near-empty. It's a *discipline*, not a guarantee — and it erodes in predictable ways on the metered Agent SDK / API paths:
- **CLI output bloat.** A `nameless fragments` or `nameless graph` command that dumps verbose JSON (full feature arrays, large slices, raw eval JSON) pulls exactly the low-entropy content that should never enter context. One chatty command in a loop = budget gone.
- **The Skill grows.** SKILL.md + reference docs creep past the lean target; the distilled production knowledge (Pitfall 3) is *large*, and if it all loads into context instead of loading on-demand by trigger, the "Skill costs ~its description" promise breaks.
- **The agent reads files it shouldn't** (no ignore file → it greps the repo, pulls audio metadata dumps, logs).
- **Regeneration loops** (Pitfall 9) multiply every per-turn token cost.
- **Banking on unmeasured compression.** PRD §16 already warns Headroom/Skill numbers are directional — assuming "60–95%" without measuring on *this* workload over-commits the budget.

**Why it happens:**
On the flat-rate interactive path during M0/M1 dev, none of this costs money, so the discipline isn't enforced. Then the project moves to a metered path (autonomy/headless) and the latent bloat becomes real spend instantly.

**How to avoid:**
- **CLI commands return compact summaries + IDs by default**, with verbosity opt-in. Make terseness the default contract of every subcommand. Audio and feature arrays are *never* returned, only referenced — enforce in the CLI layer, not by agent goodwill.
- **Keep distilled knowledge in reference docs that load on trigger**, not in the always-loaded SKILL.md body. The layered output (default + evidence) means the evidence lives in loadable docs, only the opinionated default sits near the top.
- **Ship the ignore file and path-scoped rule loading from day one** (PRD §13 item 2).
- **Measure token cost per operation on the actual workload before trusting any compression %** (PRD §16). Treat Headroom as a safety net, not a planned reduction.
- **Stub the headless Agent SDK driver early** (PRD open decision #6) — running the metered path even occasionally during dev forces the Skill/CLI to stay clean *before* bloat calcifies. The discipline is only real if exercised.
- **Bound agent loops** (ties to Pitfall 9): every loop needs a token/attempt ceiling.

**Warning signs:**
- A single CLI call returns kilobytes of JSON.
- SKILL.md + always-loaded docs growing past a couple hundred lines.
- Token cost per generation cycle unmeasured.
- "We'll measure compression later."

**Phase to address:** Cross-cutting, but enforce in M0 — CLI design (compact-by-default contract) and M1 — agent loops (bounding). Exercise the metered path early.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One-pass "summarize transcripts into a skill" (skip extract→synthesize split) | Ships the knowledge layer fast | Citation drift + hallucinated craft baked into every agent decision; the core "quality in" promise breaks silently | **Never** — this is the project's central value |
| Skip extractability scoring; ingest every video raw | More videos, bigger number | Garbage transcripts dilute distillation; visual-only "lessons" become fake spoken claims | Only for a throwaway spike, never for the shipped layer |
| Reuse one feature-extraction code path for user fragments AND reference tracks | Less code | Clone-leak risk (Pitfall 6) — reference melody can reach the generator | Never — the asymmetry must be typed |
| Global eval-gate thresholds (not per-genre) | Simpler config | Niche genres either all-rejected (budget burn) or junk passes | MVP smoke test only; calibrate before M1 exit |
| Store `sampled` as `ai_generated`/`derived` | Avoids a schema change | Copy provenance hidden; attribution + rights tracking broken | Never |
| Verbose CLI JSON output | Easy debugging | Blows metered token budget when agents loop over it | Behind a `--verbose` flag, never default |
| Run transcript ingestion from the cloud GPU worker | One environment | YouTube blocks cloud IPs (verified) → ingestion dies | Never; fetch locally |
| Assume Headroom 60–95% reduction in budget math | Optimistic planning | Over-committed budget; overflow billing disabled means hard stop | Never bank it; measure first (PRD §16) |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| YouTube transcript API | Fetch from cloud worker at high rate | Local/residential fetch, throttled, idempotent, snapshot-on-ingest (verified: cloud IPs blocked, 429s, PoToken in 2025–26) |
| Whisper (caption fallback) | Re-transcribe everything (GPU cost) | Only re-transcribe high-extractability-value videos with bad/missing captions or heavy code-switching |
| Demucs htdemucs | Trust stems as clean; ignore rescaling | Verified artifacts: hi-hat/cymbal bleed into vocals, vocal reverb left in instrumental, phasey wide-stereo output, per-stem auto-rescale **breaks relative stem volume**. Re-normalize deliberately; expect bleed on dense mixes; avoid experimental 6-stem (piano stem has artifacts) |
| MusicGen-Stem / MuseControlLite | Feed reference-track melody as conditioning | Only user fragments feed melodic conditioning; references feed non-melodic targets only (Pitfall 6) |
| CLAP (LAION) | Treat embedding as fine-grained genre truth | Verified weak for fine-grained genre; use for coarse vibe/retrieval, validate against labels, report variance (Pitfall 5) |
| MusicGen license | Assume portfolio = unrestricted | Verified CC-BY-NC 4.0 weights; track NC encumbrance in provenance; portfolio is published, not private |
| GPU inference endpoint | Assume always-available, fixed cost | Batch + ephemeral + resumable via NATS; meter GPU minutes; keep CPU smoke path |
| Headroom compression | Bank a fixed % reduction | Measure on this workload; it's a safety net, not a budget line (PRD §16) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded regeneration loop on niche-genre gate failures | GPU minutes + agent tokens spike per track; few outputs | Per-genre calibrated thresholds + hard max-attempts terminator + ask-human fallback | As soon as niche-genre generation is attempted (M1) |
| Distillation reprocesses all transcripts on every run | Ingestion/distillation takes hours; re-fetches blocked | Idempotent, incremental, content-hashed snapshots | At ~100+ videos / first re-run |
| Full feature arrays or eval JSON returned through the CLI into context | Token cost per turn balloons on metered path | Compact-by-default CLI; arrays by ID only | The moment work moves to Agent SDK / API metering |
| pgvector similarity over a growing fragment + sample library without index tuning | Retrieval slows as library grows | Appropriate index (HNSW/IVF) + filtered queries; the agent reads slices not scans | As the persistent stem/sample library accumulates over weeks |
| Hot GPU worker left running between batches | Idle GPU cost dominates | Ephemeral spin-up/down driven by queue depth | Continuously, silently |

## Security / Integrity Mistakes

(Solo/local-first — "security" here is mostly provenance integrity, rights hygiene, and gate-bypass prevention.)

| Mistake | Risk | Prevention |
|---------|------|------------|
| Citation points only at a live YouTube URL | Evidence trail rots on takedown; auditability claim breaks | Snapshot transcript + hash + retrieval date locally; URL is a secondary pointer |
| Reference/sample audio embedded into exported output | Inadvertent copyright reproduction / cloning | Type the asymmetry: references inform, never ship; only attributed `sampled` audio appears, with rights status |
| No rights-status field on samples | Future commercial pivot becomes a forensic nightmare; accidental infringement in public portfolio | `copyrighted-uncleared` / `royalty-free` / `own-work` / `unknown` field from day one |
| Eval-gate bypass via an alternate write path | Ungated generation enters arrangement; quality premise broken | Rust state machine: `generated→placed` only through the gate, exhaustive matching, no other transition (PRD §7) — audit there is no second path |
| Treating attribution/credits sheet as legal clearance | False sense of compliance on a published portfolio | Document explicitly: attribution = honesty, not rights; prefer clear-licensed/own material for public output |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Skills present single-source or hallucinated craft as confident fact | User (and agents) trust wrong technique; output quality drops; trust in the system collapses | Layered output: opinionated default + confidence + dissent visible; LOW-confidence flagged honestly |
| Gate silently rejects niche-genre generations with no explanation | User thinks system is broken / can't do their genre | Surface gate scores + reason; offer human-override for known-weak metrics |
| Vibe descriptions read as objective measurement | User over-trusts an LLM's poetic guess about a reference | Separate measured targets from interpreted vibe; label trust level |
| Latency (minutes for arrange+generate+eval) framed as a bug | User expects real-time, feels system is slow | PRD already frames M0/M1 as batch; set expectation explicitly; M2 real-time operates on rendered material |
| Credits sheet implies the track is cleared to publish | User publishes infringing material believing they're covered | Credits sheet states attribution ≠ permission; show rights status per sample |

## "Looks Done But Isn't" Checklist

- [ ] **Knowledge distillation:** Skills render and read well — but verify every claim's cited timestamp *actually contains* the supporting tokens (citation-drift check passed), conflicts are preserved not averaged, and no numbers were invented.
- [ ] **Transcript ingestion:** "100+ videos ingested" — but verify extractability scoring ran, visual-only lessons are flagged not faked, and code-switched/uncaptioned videos were handled or honestly excluded.
- [ ] **Sparse-genre grounding:** Alt-piano skill exists — but verify it's cross-checked against real artist audio, isn't just "parent A + parent B" concatenated, and carries LOW/MEDIUM confidence labels.
- [ ] **Reference layer:** Vibe + targets extracted — but verify NO melodic/structural data is stored as a conditioning target, and references are physically barred from the melodic generation path.
- [ ] **Sampling:** Credits sheet exports — but verify each sample has a rights-status field and `sampled` is its own provenance value, not aliased to `ai_generated`.
- [ ] **Eval gate:** Generations pass/fail — but verify thresholds are per-genre calibrated, the regen loop is attempt-bounded, and all scores (not just pass/fail) are logged.
- [ ] **Clone boundary:** "Style-only" works — but verify a generated-vs-reference melodic-similarity negative check exists and actually fires.
- [ ] **Token discipline:** Interactive path is cheap — but verify the metered path was exercised, CLI output is compact-by-default, and per-operation token + GPU-minute costs are measured (not assumed).
- [ ] **Ingestion robustness:** Works on the dev machine — but verify it runs locally (not cloud), throttles, resumes after a block, and snapshots evidence.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Hallucinated/citation-drifted craft already in skills | HIGH | Re-run distillation with extract→synthesize split + citation-verification gate; re-audit a sample; regenerate affected skills. Cheaper if extraction claims were stored separately |
| Ingestion blocked mid-run (cloud IP) | LOW | Move fetch local, throttle, resume from snapshotted progress (idempotent design makes this trivial) |
| Citation rot (videos taken down) | LOW if snapshotted, HIGH if not | Fall back to local transcript snapshot; if none, claim becomes unverifiable and must be demoted/dropped |
| Clone leak discovered in output | MEDIUM | Add negative melodic-similarity check to gate; type the reference/fragment asymmetry; re-evaluate affected fragments |
| Eval thresholds reject everything | MEDIUM | Recalibrate per-genre against liked-track anchors; add human-override; cap regen attempts to stop budget bleed |
| Metered budget blown by CLI bloat | MEDIUM | Make CLI compact-by-default, move knowledge to on-trigger docs, add ignore file, bound loops; re-measure |
| Sample rights ambiguity at commercialization | HIGH if untracked | Was preventable with a rights-status field; without it, manual forensic review of every sample's source |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Transcript noise / visual-only / code-switch | M0 — Transcript Ingestion | Extractability scores logged; visual-only flagged; spot-check distilled numbers exist in source |
| 2. YouTube ToS / IP block / citation rot | M0 — Transcript Ingestion | Runs locally + throttled; resumes after block; every citation has a local snapshot + hash |
| 3. GIGO distillation (hallucination/conflation/drift) | M0 — Knowledge Distillation *(flag for deep planning)* | Two-pass extract→synthesize; citation-verification gate passes; layered output with confidence; human spot-audit |
| 4. Sparse-genre decomposition misleads | M0 — Sparse-genre grounding | Decomposition cross-checked against real artist audio; blend measured not asserted; confidence-labeled |
| 5. Audio analysis over-claims (CLAP/DSP) | M0 — Reference + Sparse-genre (audio pipeline) | Measured vs. interpreted fields separated; CLAP validated vs. labels; variance reported |
| 6. Clone boundary leaks | M0 schema + M1 Generation/Eval | Reference fragments barred from melodic conditioning (typed); gate has reference negative-check |
| 7. Sampling copyright reality | M0 — Sampling schema + Export/credits | Rights-status field present; credits state attribution ≠ permission; public output uses clear material |
| 8. Generator license + GPU cost | M1 — Generation worker | Generator behind worker interface; GPU minutes metered; CPU smoke path exists |
| 9. Eval thresholds mis-tuned for niche | M1 — Eval gate | Per-genre calibration; max-attempts terminator; full score logging |
| 10. Token-thin discipline violated | M0 CLI design + M1 loops (cross-cutting) | CLI compact-by-default; on-trigger docs; ignore file; metered path exercised; costs measured |

## Sources

- [jdepoix/youtube-transcript-api Issue #511 — IP blocked even with proxy](https://github.com/jdepoix/youtube-transcript-api/issues/511) — verified cloud-IP blocking (HIGH)
- [Fixing YouTube Transcript API RequestBlocked Error (Medium)](https://medium.com/@lhc1990/fixing-youtube-transcript-api-requestblocked-error-a-developers-guide-83c77c061e7b) — 429 vs IP-block distinction (HIGH)
- [SkipTheWatch — YouTube Transcript API Not Working (2026)](https://skipthewatch.com/blog/youtube-transcript-api-not-working) — PoToken, cloud-range blocking 2025–26 (MEDIUM)
- [Avoiding YouTube Blocking on GCP (DEV)](https://dev.to/evanlin/avoiding-youtube-blocking-on-gcp-using-a-proxy-30f1) — cloud worker failure mode (MEDIUM)
- [facebook/musicgen-large — Hugging Face](https://huggingface.co/facebook/musicgen-large) — weights CC-BY-NC 4.0, code MIT (HIGH)
- [audiocraft Issue #198 — Weights protected under CC-BY-NC](https://github.com/facebookresearch/audiocraft/issues/198) — non-commercial weights confirmed (HIGH)
- [facebookresearch/demucs (GitHub)](https://github.com/facebookresearch/demucs) — per-stem rescaling breaks relative volume; 6-stem piano artifacts (HIGH)
- [StemSplit — Demucs setup / limitations](https://stemsplit.io/blog/demucs-local-setup-guide) — hi-hat/reverb bleed, stereo phasiness (MEDIUM)
- [CLAP: Learning Audio Concepts From Natural Language Supervision (arXiv 2206.04769)](https://arxiv.org/pdf/2206.04769) — language supervision weaker for genre classification (HIGH)
- [ReCLAP (arXiv 2409.09213)](https://arxiv.org/html/2409.09213v1) — CLAP zero-shot subpar; limited prompt-augmentation gains (MEDIUM)
- Project sources: `nameless-prd.md` §7 (state machine), §10 (eval gate), §13 (token budget), §15 (licensing/compute), §16 (risks); `.planning/PROJECT.md` (knowledge layer, reference/sampling, sparse-genre decisions)
- Domain/legal: US sound-recording sampling precedent (*Bridgeport Music v. Dimension Films* — no de-minimis for recordings) — general legal knowledge (MEDIUM)

---
*Pitfalls research for: audio-native AI music composition with tutorial-distilled knowledge + reference/sampling grounding*
*Researched: 2026-06-26*
