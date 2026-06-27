# LEARNING — how tutorial ingestion actually works (and why each part is shaped this way)

This is the teaching companion to the Phase-3 ingestion stage. It explains the ideas the code embodies
at a real level — YouTube captions, IP blocking, extractability scoring, snapshot-on-ingest, and ASR —
so the *why* survives even if the *how* gets refactored. The thesis underneath all of it is the
project's: **quality in, quality out.** The knowledge layer is only as good as the transcripts it is
built from, so the ingestion stage's real job is not "download 100 videos" — it is "decide which sources
are teachable, and preserve them honestly."

---

## 1. YouTube captions: manual vs auto (ASR) vs none

A YouTube video can carry transcripts from three very different origins, and the difference is the single
biggest quality signal in this whole pipeline:

- **Manual captions** — a human typed (or corrected) them. They have punctuation, casing, correct
  spelling of jargon ("log drum", "Serato", "300 Hz"), and clean sentence boundaries. Gold.
- **Automatic captions (YouTube's own ASR)** — a machine transcribed the audio. They are lowercase,
  punctuation-free, and *systematically mis-hear exactly the words that matter here*: producer jargon,
  numbers + units, and code-switched speech (amapiano/SA producers mixing English with isiZulu/Sesotho).
  You can watch this happen in our fixture `amapiano_mixing_auto_noisy.json`: "log drum" → "lock drama",
  "Serato" → "serato the thing", "300 Hz" → "three hundred hurts". The *words* are present; the *craft*
  is corrupted.
- **None** — the channel disabled captions or none were generated. Many niche producer tutorials have
  this.

The pipeline tags every transcript with its `caption_source` (`manual | auto | asr | none`) and weights
it: `manual (1.0) > asr (0.85) > auto (0.5) > none (0.0)`. Note **our own ASR is ranked above YouTube's
auto-captions** — because faster-whisper (below) is dramatically better at jargon and code-switching than
YouTube's auto-caption model. That ordering is the reason the fallback ladder prefers re-transcribing a
noisy auto track over trusting it.

**The trap builders fall into:** "transcript = the lesson." It isn't. A transcript is *evidence that
words were spoken*, which is not the same as *teachable craft was captured* (see §3).

---

## 2. Why datacenter IPs get blocked — and why local-first sidesteps it

`youtube-transcript-api` and `yt-dlp` are **unofficial** — there is no sanctioned API for third-party
captions (the official `captions.download` only returns captions for videos *you own*, useless for
tutorial channels). They work by talking to YouTube's web endpoints the way a browser would.

YouTube actively defends those endpoints against automation, and in 2025–2026 the reality is stark:

- **Cloud/datacenter IP ranges are blocked outright.** AWS, GCP, Azure, DigitalOcean addresses get
  `RequestBlocked` / `IpBlocked` almost immediately — *identical code* that works on a home machine fails
  the moment it runs on a cloud worker. YouTube treats datacenter IP reputation as a strong bot signal.
- **Volume triggers 429 rate-limiting.** Too many requests too fast, from any IP, looks like a scraper.
- **PoToken ("proof of origin")** bot-detection adds a token an automated script can't easily produce.

Two design consequences, both baked into this stage:

1. **Run ingestion locally, from a home/residential IP.** This project is local-first anyway, so this
   costs nothing and sidesteps the single biggest failure mode. The GPU worker plane (Demucs/CLAP/etc.)
   is for *already-fetched* audio — ingestion stays on your machine. (If you ever *must* run from cloud,
   you need rotating *residential* proxies — ToS-adjacent and not a clean portfolio story.)
2. **Throttle hard, and make throttling a first-class, testable component.** That is the `RateLimiter`
   port + the injected `Clock`. The live throttle waits ~2s (plus jitter) between requests via
   `clock.sleep`; in tests the `FakeClock` *advances virtual time instead of really sleeping*, so we can
   assert "the limiter spaced 5 requests by 2s each = 8s of virtual time" in microseconds, deterministically.
   Randomness (jitter) is injected as a seeded `random.Random` so even the jittered throttle is reproducible.
   Time and randomness are dependencies like any other — that is the testability law applied to the clock.

---

## 3. Extractability scoring — and why visual-only tutorials are *dangerous*, not just useless

This is the heart of the phase. A huge fraction of production knowledge is **visual, not spoken**: the
producer drags a filter cutoff, A/Bs two presets, points at a piano roll and says *"and then you just do
that and boom."* The transcript captures the words and **zero recoverable craft**.

Why is that *dangerous* rather than merely empty? Because of what the **downstream LLM** does with it
(Phase 4–5). Faced with a thin, content-free transcript that it's been told is a "tutorial", a fluent
language model will **invent specificity to fill the void** — confident-sounding Hz/dB/ratio values that
*no source ever stated*. That fabricated craft then gets written into a `SKILL.md`, the arranger/mixer
agents trust it, and bad craft propagates into every generation. Garbage in, garbage out — the exact
failure this whole project exists to avoid. So **extractability is a gate that runs BEFORE distillation**,
not a metric reported after it.

`extractability_score(transcript) -> 0..1 + flags + verdict` is a **pure function** (trivially testable)
that blends four *positive* signals and then attenuates by a *visual-only penalty*:

```
base  = 0.30 * caption_source_weight   # manual > asr > auto > none
      + 0.15 * word_density            # words-per-minute vs a healthy ~120 wpm — is anyone talking?
      + 0.25 * vocab_presence          # distinct producer-jargon terms (log drum, high-pass, sidechain…)
      + 0.30 * actionable_ratio        # fraction of sentences that are INSTRUCTIONS (imperative verb OR a number+unit)
score = base * (1 - visual_only_penalty)
```

The four positives encode "is this teaching?": a real lesson talks (`density`), uses the vocabulary of
the craft (`vocab_presence`), and issues parameterized instructions ("cut **300 Hz**", "layer the
vocal") rather than commentary ("this beat is so clean") (`actionable_ratio`), and we trust the caption
source it came from.

The **visual-only penalty** is the clever bit. It counts screen-pointing deixis ("as you can see", "like
this", "do that", "boom") — but with a crucial nuance: **a numeric parameter "pays for" a deixis.**
"pull it down to like this, around 300 Hz" is fine (the pointing is *paired with a real value*); "you
just do that, boom" is not. So `penalty` only grows from the deixis phrases left *unpaid* by any numeric
parameter, and it's **multiplicative** — a transcript that is mostly unpaid pointing gets crushed even if
it name-drops a plugin. You can see it work in `altpiano_visual_only.json`: caption weight 1.00 (manual!)
but vocab 0.00, visual_penalty 0.85 → final score **0.08, verdict REJECT, flag `visual_only`**. The
honest output is "this video shows something exists but does not explain it" — fed to the gap tracker,
**never faked into a skill**.

The verdict ladder is `KEEP` (≥0.55, admit at full weight) / `LOW_SIGNAL` (0.30–0.55, admit
down-weighted and flagged) / `REJECT` (<0.30 or no captions). The thresholds are a starting calibration
in a `ScoringConfig` dataclass, *not* a law — the right move later is to calibrate them per genre against
real liked-track material. The point of keeping every component sub-score is that a low score is
*explainable* ("low_density + visual_only"), not an opaque 0.21.

---

## 4. Snapshot-on-ingest — making citations survive takedowns

Every claim the later stages distill will cite `video_id @ timestamp`. But **videos and whole channels
get taken down**, and auto-captions get silently re-generated. If the only record of a claim's source is
a live YouTube URL, the evidence trail **rots** — and "every claim traceable to its source" quietly
breaks months later when someone audits it.

So at ingest we **snapshot the evidence**:

- `snapshot_record(transcript, now)` is a **pure** function producing a `SnapshotRecord` with a
  **SHA-256 content hash** + the **retrieval date** (the date is *injected* — `now` is a clock argument,
  never `datetime.now()` inside the function, so snapshots are reproducible and the date means "when *we*
  retrieved it"). The full timestamped segments are written to an immutable snapshot **file**.
- The citation then references **our snapshot**, with the YouTube URL as a secondary, possibly-dead
  pointer. The hash also **detects drift** (a re-captioned video hashes differently) and powers
  **idempotent re-runs**: same id already present ⇒ skip, so a block mid-batch loses no work and a re-run
  doesn't re-fetch.

One subtlety: the hash deliberately **excludes** `fetched_via`, so the *same captions* pulled by
youtube-transcript-api vs by the yt-dlp fallback produce the *same* content hash — the evidence is the
text+timestamps, not the tool that fetched it. And the per-segment timestamps are load-bearing: they are
the substrate Phase 4 cites as `video_id @ ts`. Drop them and the citation anchor is unrecoverable.

---

## 5. faster-whisper / CTranslate2 — the honest ASR fallback

When captions are missing or the auto-captions are too noisy to trust, we **re-transcribe the audio
ourselves** with **faster-whisper** (`large-v3`). Why this and not something else:

- **Whisper** (OpenAI's model) is a strong multilingual speech-recognition model that produces real
  punctuation, casing, and timestamps, and handles **code-switching** (English + isiZulu/Sesotho) far
  better than YouTube's auto-captions — exactly the SA-producer content the north-star genres lean on.
- **faster-whisper** is a re-implementation of Whisper on **CTranslate2**, an inference engine that uses
  quantization + optimized kernels to run **~4× faster with less memory** than the reference
  implementation. It supports `int8` quantization on CPU (so a CPU-only worker still functions, slowly)
  and `float16` on GPU (CUDA 12 + cuDNN 9). That's why our real adapter defaults to `device="cpu",
  compute_type="int8"` and exposes a `device="cuda"` path.
- ASR is **GPU cost**, so it runs **only on the fallback branch** the pure `fallback_decision` selects —
  never when usable captions already exist. The flow is: yt-dlp pulls the bestaudio stream to a temp
  file, faster-whisper transcribes it (with `vad_filter=True` to drop music beds so we transcribe
  *speech*, not lyrics), and the result is tagged `caption_source = asr` (weight 0.85). In our fixtures,
  `rnb_vocal_no_captions` (no captions at all) and `amapiano_mixing_auto_noisy` (auto too noisy) both
  take this path and end up KEEP — craft recovered that auto-captions would have garbled or lost.

---

## 6. How it all composes (ports & adapters, the testable shape)

The orchestration `IngestPipeline` is **pure over injected ports** — it contains no yt-dlp, no
youtube-transcript-api, no faster-whisper, no sqlite, no real clock. Each external dependency sits behind
a `typing.Protocol` with a **real adapter** (heavy imports lazy, inside methods) and a deterministic
**fake**:

| Port | Real adapter (env-gated) | Fake (tests) |
|---|---|---|
| `DiscoverySource` | `YtDlpDiscoverySource` (yt-dlp ytsearch) | `FixtureDiscoverySource` |
| `TranscriptFetcher` | `YoutubeTranscriptFetcher` (api primary, yt-dlp subs secondary) | `FixtureTranscriptFetcher` |
| `Transcriber` (ASR) | `FasterWhisperTranscriber` | `FixedTextTranscriber` |
| `CorpusStore` | `FilesystemCorpusStore` (snapshots + registry.sqlite) | `InMemoryCorpusStore` |
| `Clock` | `SystemClock` | `FakeClock` (virtual time) |
| `RateLimiter` | `IntervalRateLimiter` | `NoOpRateLimiter` / `IntervalRateLimiter` on `FakeClock` |

Because the heavy/network leaves are swapped for fakes, the **entire control flow** — discovery, dedup,
the fallback ladder, ASR invocation, snapshotting, scoring, registry persistence — runs in tests with
zero network, zero models, and zero real time, yet exercises the real logic. (The `FilesystemCorpusStore`
is the one "real" adapter the tests use directly, because `sqlite3` is Python stdlib — so we verify the
*actual* persistence path, not just a fake.) This is the same ports-and-adapters discipline as the Phase-2
`workers/` plane; the production adapters drop in unchanged.

---

# Phase 4 — Cited claim mining + cross-reference (the project's intellectual core)

Phase 3 produced a *corpus of transcripts*. Phase 4 turns it into a *registry of cited claims* grouped
into preserved consensus and conflict. This is the **make-or-break** stage: it is where the project's
"quality in, quality out" promise is either kept or quietly broken. Everything here is in service of one
discipline — **extract, then (later) synthesize** — and the whole point is that Phase 4 does ONLY the
extract half. No opinionated defaults, no merged "best way", no SKILL.md. That boundary is the lesson.

## 7. Why structured (tool-use) output beats free-form for reliable extraction

The naive way to "extract claims with an LLM" is to ask for prose and parse it. That fails in exactly the
ways that matter: the model writes fluent, confident text optimized for *readability*, not *faithfulness*,
and you are left regex-scraping a paragraph that may have silently reworded the source.

The reliable way is **structured tool-use**: define a tool (`emit_claims`) whose `input_schema` is a
closed JSON Schema (`additionalProperties: false`), and **force** the model to call it
(`tool_choice={"type": "tool", "name": "emit_claims"}`). Now the model cannot return prose — it must
return a typed object whose shape *you* control. Three things follow:

- **The schema is the contract.** Each claim must carry `claim_text`, `technique`, `stage`,
  `timestamp_ms`, `quote`, `confidence`. There is nowhere in the schema to put a "summary" or a
  "recommended default" — the closed object structurally forbids smuggling synthesized fields in.
- **Parsing is validation, not scraping.** `parse_extractor_output` runs the tool input through a
  pydantic model; malformed entries are dropped, never coerced into something plausible.
- **Reliable output comes from structure, not clever prompts.** The careful prompt (below) still matters,
  but the *schema* is what makes the output machine-trustworthy.

We use `claude-opus-4-8` with **no `thinking`** — deterministic extraction does not want exploratory
reasoning, and forced tool-choice pairs cleanly with that. (Cost note for the metered path: ~$5 / 1M
input, ~$25 / 1M output tokens; a single ~3-minute tutorial transcript is well under 2k input tokens, so
extraction is cheap — the budget risk is *volume* × *re-runs*, which idempotent mining controls.)

## 8. The extract-THEN-synthesize split — and exactly which GIGO failures it defeats

This is the heart of it. An LLM asked to "summarize 100 transcripts into a skill" in one pass will,
characteristically:

- **Fabricate specificity** — invent an exact Hz/dB/ratio that no source stated (confident numbers read
  as expertise).
- **Conflate genres** — let an amapiano log-drum trick bleed into the "deep-house bass" advice.
- **Over-generalize from one source** — promote one creator's habit to "the way".
- **Launder disagreement** — average two opposing compression philosophies into mush, or assert a false
  consensus.
- **Drift citations** — attach a real citation to a claim the source did not make.

The two-pass split structurally prevents each one, and Phase 4 is **pass 1 only**:

| Pass | What it may do | What defeats the failure |
|---|---|---|
| **1 — extract (this phase)** | Emit atomic, individually-cited claims; group them; preserve conflict. | Numbers must be *quoted*, not generated. Genre is per-claim and evidenced. Each claim is one source. Disagreement becomes a first-class `conflict`. |
| **2 — synthesize (Phase 5)** | Decide an opinionated default — but **only over the extracted claim set**, never raw transcripts, and only by citing claims that already exist. | The synthesizer can cite nothing that pass 1 didn't extract, so citation drift is impossible by construction. |

The key insight: **a synthesizer that can only cite pre-extracted, pre-verified claims cannot drift, cannot
invent a number, and cannot launder a conflict** — because the conflict is sitting in the data as two
claims it must reckon with. Phase 4's job is to make that data faithful. Phase 5's freedom is bounded by it.

## 9. Citation discipline — snapshot-anchored verbatim quotes, and drift detection

Every claim cites `source_video_id @ timestamp_ms` with a VERBATIM `quote`, and that quote is checked
against the immutable Phase-3 snapshot by the pure `verify_citation`:

- **The quote must occur at/near the cited timestamp.** We find the best-matching segment (normalized
  text, **digits + units preserved** so "300" and "hz" never get stripped) and compare its start to the
  cited time.
- **Three honest verdicts, not one bool:** `verified` (found in tolerance), `drift` (found, but at the
  *wrong* time — the dangerous case), `not_found` (hallucinated). Drift is the most corrosive failure
  because it *looks* auditable; surfacing it as its own verdict is the point.
- **Re-anchoring at parse time.** Even before verification, `parse_extractor_output` snaps each claim's
  timestamp to the segment its quote actually lives in — so a model that mis-states a timestamp cannot
  poison the anchor. The model owns the *content* fields; the *identity/citation* fields
  (`source_video_id`, `caption_source`, and the re-anchored `timestamp_ms`) come from the transcript and
  cannot be hallucinated.

`verify_citation` is deliberately the **kernel of Phase 5's hard gate**: Phase 4 computes it and *records*
it (and can drop on failure with `--require-citation`), Phase 5 turns it into a non-negotiable reject.

## 10. Consensus vs conflict as first-class data (and why distinct sources, not repeats)

`cross_reference` groups claims by topic (`stage/technique`, normalized) and partitions each topic:

- **uncontested** → all claims are `consensus` (corroboration);
- **contested** (≥2 distinct stances) → all claims are `conflicts`, **both camps preserved**, and **Phase 4
  picks no winner**.

This is the answer to the producer reality that *everyone disagrees about everything* — the amapiano log
drum is built on FL Studio FLEX by some and from layered samples by others. A pipeline that "helpfully"
resolves that has destroyed exactly the nuance the user needs. So the conflict is recorded as data; the
`ClaimCluster.sides()` view shows the two camps; and the decision is deferred to Phase 5, made *on top of*
the evidence, never by deleting a side.

**Corroboration counts DISTINCT sources, not repeats.** One creator restating a point three times is not
agreement — `distinct_consensus_sources` counts unique `source_video_id`, and `dedup_claims` collapses
same-source repeats before clustering. Cross-source agreement is signal; same-source repetition is noise.
(A nice property: clusters are a *pure function of the full claim set*, so the pipeline recomputes them
globally after every mine and replaces them — incremental mining can never leave a stale cluster.)

## 11. Semantic dedup — a deliberate trade-off, kept optional

Exact-text dedup misses paraphrase ("roll off the low end" ≈ "high-pass the bottom"). A `SimilarityIndex`
hook (keyword Jaccard by default; embedding cosine when env-gated) can collapse same-source near-paraphrases.
We keep it **off by default and same-source-only** on purpose:

- *On by default* would make the core non-deterministic and risk **erasing genuine corroboration** — the
  worst possible dedup error, because corroboration is the entire confidence signal. Same-source-only means
  the dedup can never reduce a 3-source consensus to a 2-source one.
- The keyword fake keeps the pure core testable; the embedding adapter is a drop-in upgrade behind the same
  `similarity(a, b)` seam for when paraphrase detection needs to be smarter than token overlap.

## 12. Confidence calibration + caption-source provenance

Two trust signals ride along with every claim. **Confidence** is calibrated by the prompt's rubric
(0.9 explicit+parameterized, 0.7 explicit, 0.5 implied, <0.4 vague). **`caption_source`** records whether
the evidence came from a `manual` caption, our own `asr`, or YouTube `auto` captions — and auto-captions
mis-hear the very jargon and numbers that matter (PITFALLS #1: "log drum" → "lock drama", "300 Hz" →
"three hundred hurts"). Carrying both means Phase 5 can weight a parameterized claim from a manual caption
far above a vague one scraped from auto-captions — *without re-reading the audio*. That is the layered,
auditable trust the project promised, built into the claim schema rather than bolted on later.

---

## Further reading / sources

- youtube-transcript-api IP-blocking (cloud vs residential), 2025–26 — project GitHub issues; PoToken.
- faster-whisper (SYSTRAN) + CTranslate2 quantization — project READMEs; `large-v3` / `large-v3-turbo`.
- ITU-R BS.1770 / sampling-evidence durability — general practice; mirrored from the project PITFALLS.md.
- Anthropic tool-use / structured output + model ids/pricing — Anthropic SDK docs (`claude-opus-4-8`,
  forced `tool_choice`, ~$5/$25 per 1M tokens). Grounding for the Phase-4 extractor.
- LLM claim-extraction / citation-verification patterns — arXiv 2511.16198 (SemanticCite); the project's
  `.planning/research/{FEATURES,PITFALLS}.md` (consensus/conflict layered output; the GIGO failure modes).
- The project's own `.planning/research/{STACK,PITFALLS,ARCHITECTURE}.md` — the grounding for every
  decision above.
