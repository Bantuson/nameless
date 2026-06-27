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

## Further reading / sources

- youtube-transcript-api IP-blocking (cloud vs residential), 2025–26 — project GitHub issues; PoToken.
- faster-whisper (SYSTRAN) + CTranslate2 quantization — project READMEs; `large-v3` / `large-v3-turbo`.
- ITU-R BS.1770 / sampling-evidence durability — general practice; mirrored from the project PITFALLS.md.
- The project's own `.planning/research/{STACK,PITFALLS,ARCHITECTURE}.md` — the grounding for every
  decision above.
