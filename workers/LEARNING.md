# Fragment Analysis — the DSP & ML, explained

> This is the teaching artifact for Phase 2. It explains, at a real (not hand-wavy) level, every
> technique the feature worker uses: **why** it exists in Nameless, **how** it works (the
> math/algorithm), the **trade-offs**, and **how it serves the product** — translating a hummed idea
> into parts that lock to your key and tempo. Read it alongside the code in
> `src/nameless_workers/`. Nothing here requires the heavy libraries to be installed.

## 0. The big picture: from a hum to a locked arrangement

You record a fragment — say you hum a chorus hook. To later generate a bass/drum/pad that *locks to
your key and tempo*, the system first has to **understand** that audio as music. Phase 2 is that
understanding step. One captured fragment goes through:

```
raw audio bytes
   │  decode → mono float samples y[n] @ sample-rate sr
   ├──────────────► f0 contour            (torchcrepe)      "what melody did you hum, instant by instant?"
   ├──────────────► chromagram (CQT)      (librosa)         "which pitch-classes are active over time?"
   │                   └► key             (Krumhansl-Schmuckler, pure)   "what key is it in?"
   ├──────────────► onsets                (librosa)         "when do notes/hits start?"
   ├──────────────► beat grid + tempo     (librosa)         "where is the pulse; how fast?"
   ├──────────────► loudness (LUFS)       (pyloudnorm)      "how loud, perceptually?"
   └──────────────► CLAP audio embedding  (LAION-CLAP)      "what does this *sound like*, as a vector?"
the note text "chorus hook…" ──► CLAP text embedding (same space)  "what did you *say* it is?"
```

Everything except the two short embeddings is a **large array** — it is stored in Postgres
(`fragment_features`) and **never** shown to the agent (PRD §12). The agent only ever sees compact
summaries (key, tempo) and IDs. The two 512-d embeddings are the one thing we *do* index, because they
make the whole library searchable by *meaning* (next sections).

Why this matters: the f0 + chroma + tempo + key are exactly the **conditioning signals** M1's
generator needs. "Generate a bass that locks to this hook" = "generate a bass whose notes fit *this
chroma/key* and whose hits fall on *this beat grid*." Phase 2 produces those signals; M1 consumes them.

---

## 1. Digital audio in one paragraph

Sound is air-pressure over time. A microphone + ADC samples that pressure `sr` times per second
(`sr` = the **sample rate**, e.g. 44 100 Hz) into a sequence of numbers `y[0], y[1], …`. A 4-second
mono clip at 44.1 kHz is ~176 400 floats. Stereo has two such channels; we average to mono for
analysis (we care about *what was played*, not where it sits in the stereo field — that is a mixing
concern, Phase 7+). The **Nyquist theorem** says a sample rate `sr` can faithfully represent
frequencies up to `sr/2`; 44.1 kHz covers the ~20 kHz limit of human hearing. Different stages want
different rates: CREPE wants 16 kHz, CLAP wants 48 kHz — so we **resample** as needed (`librosa.resample`).

---

## 2. f0 / pitch tracking with CREPE

**What:** the *fundamental frequency* `f0(t)` — the perceived pitch — as a continuous curve over time.
A hummed melody is monophonic (one note at a time), and its pitch glides, scoops, and vibratos. We
keep that as a **signal**, not a sequence of named notes, because "C♯, then D" throws away the feel
(PRD §2: "the audio is the source of truth and is never reduced to text"). `src/.../feature_librosa.py
:_f0_contour`.

**Why not just FFT-and-pick-the-peak?** Real instruments/voices are *harmonic*: a note at `f0` also has
energy at `2·f0, 3·f0, …`. Naïve peak-picking frequently locks onto a harmonic — the classic
**octave error** (reporting `2·f0` or `f0/2`). Autocorrelation methods (YIN, pYIN) are better but still
brittle on noisy/breathy hums.

**How CREPE works (the idea):** CREPE is a convolutional neural network trained directly on audio
frames to output a pitch *probability distribution* over a set of ~360 pitch bins spanning the musical
range. Concretely:

- Slide a window over the 16 kHz signal with a hop (we use 160 samples = **10 ms**), so you get a
  pitch estimate every 10 ms.
- For each frame the CNN emits a 360-way distribution over cents (1 cent = 1/100 of a semitone); the
  expected/argmax bin → `f0` in Hz. Because the network *learned* what a real pitched sound looks like
  (harmonics and all), it sidesteps the octave-error trap that fools peak-pickers.
- **Periodicity** (a 0..1 confidence) tells you how pitched the frame is. Silence, consonants, or a
  snare hit have low periodicity — we store it as `confidence` so later stages can ignore unvoiced
  frames rather than chasing a phantom pitch.

```
f0_hz:      [ ...,  219.8, 220.1, 220.0, 233.0, ... ]   # ~A3 gliding up
confidence: [ ...,  0.95,  0.96,  0.94,  0.31,  ... ]   # last frame = breath, untrustworthy
times_s:    [ ...,  1.20,  1.21,  1.22,  1.23,  ... ]
```

**Trade-offs:** CREPE `model='full'` is accurate but heavy on CPU; `'tiny'` is faster, less accurate.
STACK.md flags `SwiftF0` (2025) as a faster swap if CPU latency bites — and because it lives behind the
`FeatureExtractor` port, swapping it touches one adapter, nothing else.

**Why it matters for Nameless:** the f0 contour *is* your melody. When M1 fleshes out the hook, the
generator and the eval gate compare against this contour (melody-fidelity scoring, PRD §10). It is also
the precision-fallback's raw material: `basic-pitch` can turn it into editable MIDI (PRD §9).

---

## 3. The chromagram (Constant-Q Transform)

**What:** a 12 × T matrix. Row = one of the 12 pitch-classes (C, C♯, …, B); column = a time frame;
value = how much energy is in that pitch-class at that moment, **folded across all octaves**. So a C2,
a C4, and a C6 all add into the "C" row. `librosa.feature.chroma_cqt`.

**Why fold octaves?** Harmony and key are octave-invariant: a C-major chord is C-major whether the bass
plays C2 or C3. Chroma throws away octave (which we don't need for key/harmony) and keeps pitch-class
(which we do). This is the bridge from "raw spectrum" to "music theory."

**Why CQT and not a plain FFT?** The **STFT/FFT** spaces its frequency bins *linearly* (e.g. every
~43 Hz). But musical pitch is *logarithmic*: the octave A2→A3 spans 110→220 Hz (110 Hz wide) while
A4→A5 spans 440→880 Hz (440 Hz wide). A linear grid gives you too few bins down low (can't separate
adjacent bass notes) and wastefully many up high. The **Constant-Q Transform** instead uses bins
*geometrically* spaced so there are a constant number per octave (e.g. 12, one per semitone) — the
"Q" (centre-freq / bandwidth) is constant. That matches how pitch actually works, so each semitone gets
its own bin at every octave. We then sum the bins of each pitch-class across octaves → the 12 rows.

**Time-averaging → the key profile:** average each row over all frames and you get a single 12-vector
`chroma_mean` — "across the whole fragment, how much was each pitch-class used?" That vector is the
input to key estimation (next section).

**Why it matters for Nameless:** chroma is the harmonic conditioning signal. "Generate a pad that fits
this hook" means "generate a pad whose chroma is consonant with *this* chroma." MusicGen-Stem is
literally **chromagram-conditioned** (STACK.md) — this row matrix is what you feed it.

---

## 4. Onset detection

**What:** the times (in seconds) where new musical events *start* — a note attack, a drum hit, a
plucked string. `librosa.onset.onset_detect`.

**How (the idea):** compute an **onset strength envelope**. Take the spectrogram, and for each frame
measure the **spectral flux** — how much energy *increased* across frequency bins versus the previous
frame (a half-wave-rectified difference: we count energy going *up*, because attacks add energy). New
events cause sharp positive flux → peaks in the envelope. Pick the peaks (with a little smoothing and a
threshold) → onset times.

```
energy↑ (flux)
   │      ▲              ▲        ▲
   │     ╱ ╲            ╱ ╲      ╱ ╲      ← each peak = an onset
   └────┴───┴──────────┴───┴────┴───┴──── time
```

**Why it matters for Nameless:** onsets are the raw rhythmic events. They feed beat tracking (below),
they tell the arranger where your phrase actually *starts* (so a generated part lands with you, not on
a leading silence), and onset density is a cheap proxy for "busy vs sparse" when classifying a fragment.

---

## 5. Beat tracking + tempo

**What:** the **tempo** (beats per minute) and the **beat grid** — the list of times where the pulse
falls, the thing your foot taps to. `librosa.beat.beat_track`.

**How (the idea), two stages:**

1. **Tempo estimate.** Take the onset-strength envelope from §4 and ask "what periodicity best
   explains these peaks?" — done by autocorrelating the envelope (or a Fourier tempogram). A strong
   recurring spacing of, say, 0.5 s between accents implies 120 BPM (60 / 0.5). This yields a global
   tempo (modern librosa returns it as a small array — we read element 0).
2. **Beat grid via dynamic programming.** Knowing the tempo gives the *spacing*, but not the *phase*
   (where beat 1 sits). librosa lays down a grid that simultaneously (a) lands on strong onset peaks
   and (b) stays evenly spaced at the estimated tempo, trading the two off with dynamic programming.
   The result is a globally consistent set of beat times, robust to a few missed/extra onsets.

**The hard cases (worth knowing):** **octave errors in tempo** — 70 BPM vs 140 BPM are equally
"valid" explanations (every beat is also a half-beat), so trackers sometimes double/halve. And a
rubato/hummed fragment may have no steady pulse at all, giving a low-confidence grid. For amapiano /
deep-house (the north-star genres) the pulse is strong and steady, so this is usually solid — but the
**eval gate's tempo-lock metric** (M1) exists precisely so a generated part that drifts off this grid
is *rejected*, turning a soft failure into a visible one (PRD §10, §16).

**Why it matters for Nameless:** the beat grid is the timeline everything snaps to. "Locks to your
tempo" = "its onsets fall on *this* grid." After generation, residual drift is *warped* to this grid
(PRD §9). No grid, no lock.

---

## 6. Krumhansl-Schmuckler key estimation (the one we implement by hand)

**What:** given the 12-vector `chroma_mean` from §3, name the **key** — e.g. `C:maj`, `A:min`. This is
the one DSP result we compute as a **pure function** (`src/.../pure/key.py`), so it is unit-tested with
no audio at all.

**The cognitive science behind it.** Krumhansl & Kessler ran "probe-tone" experiments: establish a key
in a listener's ear, then play each of the 12 pitch-classes and ask how well it "fits." Averaging many
listeners gives two **key profiles** — a 12-vector for major and one for minor — indexed by *scale
degree* (index 0 = the tonic). The tonic scores highest, then the fifth, then the third; chromatic
non-scale tones score low. These are the published weights we hard-code:

```
major = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
minor = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
          ↑tonic        ↑3rd(min)     ↑5th
```

**The algorithm (exactly what the code does):**

1. You have the observed profile `x = chroma_mean` (how much each pitch-class was actually used).
2. For each candidate **tonic** `t ∈ 0..11` and each **mode** ∈ {major, minor}: rotate the profile so
   degree 0 lands on pitch-class `t`. In code, the weight for observed pitch-class `pc` in key `t` is
   `profile[(pc − t) mod 12]`.
3. Score the fit with the **Pearson correlation coefficient** between `x` and the rotated profile:

   ```
   r = Σ (xᵢ − x̄)(yᵢ − ȳ)  /  √( Σ(xᵢ − x̄)²  ·  Σ(yᵢ − ȳ)² )
   ```

   Pearson (not raw dot product) is the right choice: it is invariant to the overall loudness of the
   fragment and to a constant offset — it asks "does the *shape* of your pitch usage match the *shape*
   of this key's profile?", which is exactly the musical question.
4. The highest of the 24 correlations wins. Its `(tonic, mode)` is the estimated key; the correlation
   `r` itself is the **confidence**.

**Why the confidence is a feature, not noise.** A clear tonal melody scores `r ≈ 0.8–0.95`. A
percussive loop, an atonal pad, or a single sustained note yields a *flat* chroma — and a flat vector
has zero variance, so every correlation collapses to ~0 (our `_pearson` returns 0 on zero variance).
Reporting `key_confidence ≈ 0` is the honest answer "this fragment has no clear key," which downstream
logic can act on instead of trusting a coin-flip label. (Tested in `test_flat_chroma_is_ambiguous`.)

**Known limitation:** the biggest confusion is **relative major/minor** (C-major vs A-minor share all
seven notes); K-S handles it via the small tonic/third weighting differences, but it is the place to
expect the occasional miss. That is acceptable here — the key is *conditioning context*, and M1's eval
gate scores actual chroma similarity, not the key *label*.

**Why it matters for Nameless:** "locks to your key" starts with knowing the key. It also makes the
graph queryable ("show me my fragments in A-minor") and gives the arranger a globally consistent
tonal centre to place parts against.

---

## 7. Loudness — LUFS and ITU-R BS.1770

**What:** one number, **integrated loudness in LUFS** (Loudness Units relative to Full Scale), modelling
how loud the fragment *sounds* to a human — not its raw peak. `pyloudnorm`, implementing the broadcast
standard **ITU-R BS.1770-4**. `src/.../feature_librosa.py:_integrated_lufs`.

**Why not just peak or RMS?** Peak (the largest sample) is about clipping, not perceived loudness — a
quiet track can have one stray peak. Plain RMS (average energy) ignores that the ear is *not* equally
sensitive at all frequencies: a 2–4 kHz tone sounds louder than a 60 Hz tone at identical energy. LUFS
fixes both:

1. **K-weighting.** Filter the signal with a standardized two-stage filter: a high-shelf approximating
   the head/torso boost in the presence region, plus a high-pass rolling off sub-bass the ear barely
   registers as "loud." Now energy is weighted the way hearing weights it.
2. **Mean square → loudness.** Take the mean square of the K-weighted signal; `LUFS = −0.691 + 10·log₁₀(mean square)` (the constant calibrates 0 LUFS to full scale).
3. **Gating.** Slide a 400 ms window; drop windows below an absolute gate (−70 LUFS, i.e. effective
   silence) and a relative gate (−10 LU below the ungated mean) so long silences don't drag the number
   down. Average the survivors → **integrated** loudness.

**Edge case we handle:** a fragment shorter than ~400 ms, or near-silent, has nothing above the gate →
BS.1770 returns `−inf`. We clamp that to a finite floor (`−70 LUFS`) so the column is always a real
number (`VOICING_FLOOR_LUFS`).

**Why it matters for Nameless:** the master targets a streaming loudness (e.g. −14 LUFS, PRD §11), and
the eval gate scores a **loudness delta** generated-vs-source (PRD §10). Both need the *same*, correct
loudness measure — the one the streaming platforms actually use. (Phase 7's reference-track LUFS target
reuses this exact function.)

---

## 8. CLAP — joint audio-text embeddings

**What:** turn a clip into a 512-d vector *and* turn a sentence into a 512-d vector **in the same
space**, so "audio that sounds chill and spacious" and the clip that *is* chill and spacious land near
each other. `src/.../embed_clap.py`. This is the engine behind "retrieve by note OR by audio in one
index" (PRD §6).

**How contrastive pretraining builds a joint space (the idea).** CLAP (Contrastive Language-Audio
Pretraining) has two encoders — an **audio tower** (an HTSAT/transformer over a spectrogram) and a
**text tower** (a language model). It trains on millions of (audio, caption) pairs with the
**contrastive (InfoNCE) objective**: in a batch of N pairs, project both sides to the same 512-d space,
L2-normalize, and compute the N×N matrix of cosine similarities. The loss pushes each clip's vector
*toward* its own caption's vector and *away* from the other N−1 captions (and symmetrically for text).
After enough data, semantically matching audio and text are **aligned by construction** — the model has
learned one shared "meaning" space spanning both modalities.

```
audio ─►[audio tower]─► aᵢ ┐
                            ├─ maximise cos(aᵢ, tᵢ),  minimise cos(aᵢ, t_{j≠i})
text  ─►[text tower ]─► tᵢ ┘
```

**What that buys the fragment graph.** Because both your **audio** and your **note text** become
vectors in this one space, a *single* pgvector index answers two different questions:

- `fragments search --similar-to <id>` — use that fragment's **audio** vector as the query → "more
  fragments that *sound* like this."
- `fragments search --note "the chorus-like ideas"` — embed the **text** with the text tower → rank
  against the **audio** vectors (cross-modal!) → "fragments that *sound like* that description," even if
  nobody wrote that phrase in their note.

We L2-normalize both towers' outputs, so cosine similarity = dot product, and the worker only ever
stores **unit** vectors — which is what makes the in-memory fake and the pgvector cosine index rank
*identically* (so a test against the fake proves the production ranking).

**Pin the checkpoint.** STACK.md is emphatic: CLAP weights have drifted historically. We pin a music
checkpoint (`larger_clap_music` / HTSAT-music family); the model name is stored per-fragment
(`embedding_model`) so a re-embed under a new checkpoint is auditable and the retrieval path can refuse
to mix two incompatible spaces.

**Why it matters for Nameless:** this *is* the memory layer's retrieval (PRD §6, "the memory layer is
this graph plus a vector index"). It is also reused as the eval gate's **CLAP-alignment** score
(generated audio vs the note's intent, PRD §10) and as the reference-track vibe embedding (Phase 7).

---

## 9. pgvector — storing & searching the embeddings (ANN, cosine, ivfflat vs HNSW)

**What:** Postgres' `pgvector` extension adds a `vector` column type and similarity operators so the
512-d embeddings live *in the same database* as the fragment graph — one store, no second service
(`migrations/0002_fragment_features.sql`).

**The distance.** We use **cosine**. pgvector's `<=>` operator is cosine *distance* = `1 − cos(θ)`;
similarity is `1 − (a <=> b)`. Since the worker writes unit vectors, cosine, dot product, and (rank-
wise) Euclidean all agree — but cosine is the honest metric for CLAP, whose vectors are
direction-meaningful, not magnitude-meaningful.

**Exact vs approximate (ANN).** A brute-force search compares the query against *every* row — perfect
recall, but O(N) per query. As the library grows you want **Approximate Nearest Neighbour**: trade a
sliver of recall for a large speedup via an index. pgvector offers two:

- **IVFFlat** (inverted file). Cluster all vectors into `lists` Voronoi cells (k-means) once; at query
  time only probe the few nearest cells. Fast and compact, **but** it must be *built on a representative
  sample* — if you create it on an empty/tiny table the clusters are garbage, and you should `ANALYZE`
  after bulk loads. Great when you already have the whole corpus.
- **HNSW** (Hierarchical Navigable Small World). Build a multi-layer graph where each vector links to
  near neighbours; search greedily hops from an entry point toward the query, descending layers. Higher
  recall and **no training step** — you can build it on an empty table and it stays good as rows are
  inserted one at a time.

**Our choice: HNSW.** Nameless is a *solo, append-as-you-go* library — you capture fragments one hum at
a time; you never have the full set up front to train IVFFlat lists on. HNSW's "no training, robust to
incremental inserts" profile fits exactly. (The migration keeps a commented IVFFlat alternative for the
day someone batch-imports a large corpus.) Rows whose embedding is still `NULL` (un-analyzed fragments)
are simply absent from the index — which is why an un-analyzed fragment never shows up in search
(`test_unanalyzed_fragments_are_absent_from_the_index`).

**The query (and the compact contract):**

```sql
select f.id, ff.key, ff.tempo_bpm, 1 - (f.audio_embedding <=> :q) as score
from fragments f
left join fragment_features ff on ff.fragment_id = f.id
where f.audio_embedding is not null
order by f.audio_embedding <=> :q
limit :k;
```

Note what comes back: **id, key, tempo, score** — never the vector, never an array. The agent gets a
ranked shortlist it can reason about cheaply; the heavy data stays on disk addressed by ID (PRD §12–13).

---

## 10. How Phase 2 serves the product

Put it together. You hummed a chorus hook and typed "chorus hook, sits over the second drop." After
Phase 2 the system knows: its **melody** (f0), its **harmony** (chroma) and therefore its **key**, its
**rhythm** (onsets) and **pulse** (beat grid + tempo), how **loud** it is (LUFS), and what it **means**
(CLAP) — both as audio and as your words. That is everything M1 needs to *generate parts that lock to
your key and tempo* and to *gate* them against your source. And because every signal is addressed by ID
and only summaries surface, the agent orchestrating all this stays token-thin (PRD §13). Quality in,
quality out.

---

## 11. The cross-language state seam (a design note)

The Rust control plane owns the **canonical** fragment state machine
(`crates/nameless-core/src/state_machine.rs`): one exhaustive `match` is the single authority on which
lifecycle transitions are legal. But the Phase-2 worker is a **separate Python process** that, after
computing features, must itself advance `Captured → Analyzing → Analyzed`.

We deliberately **mirror** the transition rules in Python (`domain/state.py`) rather than make a
network/IPC round-trip to Rust for every edge — a tiny pure function shouldn't depend on the control
plane being reachable. The risk of a mirror is **drift**: the two could disagree. We pin them together
with an **exhaustive matrix test** (`tests/test_state_mirror.py`) that reproduces the Rust 480-triple
matrix (4 provenances × 12 states × 10 transitions) against an independently hand-written allow-list. If
the Rust rules ever change, that test is where the drift surfaces. Rust stays canonical; Python is a
tested shadow. The repo's `advance()` applies this shared guard, so the worker is *structurally* unable
to drive a fragment down an illegal path (e.g. it cannot analyze an `ai_generated` fragment, and it can
never place an un-analyzed one). "The harness gates; the agent explores" — applied across the seam.

---

## 11b. Reference-track context (Phase 7) — and why non-cloning must be STRUCTURAL

Phase 7 adds a second kind of grounding alongside the producer's own fragments: **upload a finished
song you love, and the system extracts its *vibe* + measurable *non-melodic* sonic targets as
conditioning context** — *never to recreate or clone it*, only to translate your intent better. This
section teaches the ideas and, most importantly, why the non-cloning guarantee is a *type*, not a
promise.

### The thesis: a finished song is better context than a description — but it is never reproduced

"Make it warm and spacious like a late-night Sonder record" is a description; the record itself is far
richer *and* far more dangerous. Richer, because the audio carries measurable truth a sentence can't:
its loudness, its stereo image, where its energy sits, its overall vibe. Dangerous, because the same
audio also carries the *song* — the melody, the chords, the arrangement — and a melody-conditioned
generator (MusicGen-Stem, MuseControlLite) is *designed to follow whatever reaches its melodic
input*. Feed a reference's melody in and you get a clone, while believing you did "style transfer".
So the job is: extract the rich, safe part (vibe + non-melodic targets) and make the dangerous part
(melody/structure) **impossible to extract or pass through**.

### Two conditioning inputs, kept in separate types

| | Melodic conditioning | Reference (non-melodic) conditioning |
|---|---|---|
| Source | the producer's OWN `human_recorded` fragments | an uploaded reference track |
| Generator may follow… | the melody/chroma (that's the point) | atmosphere + numbers ONLY |
| Carries melody? | yes (your hum) | **no — there is no field for it** |
| Type | `MelodicConditioning` (from `&[Fragment]`) | `ReferenceConditioning` (from a `ReferenceContext`) |

The crux: these are **different types**, and the gather function that feeds the generator's melodic
input — `gather_melodic_conditioning(fragments: &[Fragment])` — accepts only `Fragment`s. A
`ReferenceTrack` is a *separate type* with no conversion into `Fragment`, so a reference is
**compile-time barred** from the melodic path. There is no runtime branch to forget (PITFALLS.md
Pitfall 6: "one shared feature path + one forgotten branch = silent cloning"). The Rust crate even
ships a `compile_fail` doctest that proves passing a `ReferenceTrack` there does not type-check.

### "What you don't store, you can't clone from" — typing the absence

The guarantee is doubled at extraction. The restricted analyzer NEVER computes f0 or chroma for a
reference (contrast the Phase-2 `LibrosaFeatureExtractor`, which *does*, for your own fragments). And
the output type makes the absence structural:

- Rust `ReferenceContext` has **no** melody/chroma/f0/chord/structure/key column. Adding one would be
  an explicit, reviewable schema + type change.
- Python `NonMelodicFeatures` is sealed with `extra="forbid"` — you literally cannot *construct* it
  with an `f0=` or `chroma=` key; pydantic raises. `assert_non_melodic()` is a belt-and-suspenders
  runtime tripwire that the analyzer runs on its own output and the tests assert on.

Non-cloning therefore falls out of the type system, exactly the rigour the PRD applies to the eval
gate ("the harness gates; the agent explores") — here the *types* gate, and an LLM-driven caller
cannot even express the cloning operation.

### What the measured targets actually capture (and what they can't)

Each non-melodic target is a *global* descriptor — true about the whole track, useless for
reconstructing a tune:

- **LUFS** (integrated loudness, ITU-R BS.1770-4): "how loud is this master?" — one number. A mastering
  target. (Phase-2 §7 covers the K-weighting + gating in depth; we reuse `pyloudnorm`.)
- **Tonal balance** (5-band energy ratios): "where does the energy sit — bass-heavy? bright?" We sum
  an STFT magnitude into 5 *wide* bands and normalize to ratios that sum to 1. Folding the spectrum
  into 5 numbers **destroys** pitch information (a melody lives in the fine structure these bands
  average over) — which is precisely why it's a safe target. Scale-invariant, so loud and quiet mixes
  with the same balance map to the same shape.
- **Stereo width** (mid/side): `mid=(L+R)/2`, `side=(L−R)/2`; width = `side_energy/(mid+side)` ∈ [0,1].
  Mono → 0, decorrelated/wide → →1. A *spatial* property; says nothing about which notes play.
- **Tempo range**: a band around `beat_track`'s estimate — rhythm, not melody.
- **CLAP style embedding**: a single joint audio-text vector over the whole track — a *vibe
  fingerprint* for advisory conditioning + retrieval. Crucially it's computed with the CLAP **audio
  tower** and we never derive chroma/f0 from it. It is also weak for *fine-grained* genre
  (PITFALLS.md Pitfall 5), so the zero-shot genre tag built on it (rank the audio embedding against
  text-embedded genre prompts) is used for **coarse** tags only, with a confidence margin that can
  honestly return "no tag".
- **Vibe description**: the one *interpreted* field — an LLM (Claude) narrates mood/space/era/texture/
  energy from the measured numbers. It is kept at a *different trust level*: human-facing context,
  never a machine conditioning target, and the model is handed only the non-melodic features so it
  cannot narrate a tune it was never shown.

### Why this is the right shape

Measured-vs-interpreted are separated by field and trust level; the embedding (a large array) is
addressed by ID and surfaces only as its *dimension* (the compact-output / token strategy holds
across the language boundary); and the reference is a first-class entity that **never enters the
fragment lifecycle** — so it can never be placed, mixed, or rendered into an arrangement. The producer
gets quality-in/quality-out grounding from a track they love, with cloning made un-representable
rather than merely discouraged.

---

## 11c. Stem separation (Phase 8) — Demucs, attribution-clean sampling, and the structural gate

Phase 8 turns every uploaded track into a **retained, browsable stem library** and lets any stem be
promoted to an **attributed `sampled` fragment**. The worker plane owns the separation half; the Rust
control plane owns promotion + the attribution invariant. This section explains the DSP, the model
choices, and — most importantly — the *honest legal framing* the system bakes in.

### How source separation works (Demucs, at a real level)

A finished mix is a sum of sources (vocals + drums + bass + everything else) collapsed to 2 channels.
Separation is the **inverse, under-determined** problem: recover the sources from the mixture. Demucs
(`htdemucs`) is a **hybrid** model — it processes the signal in *both* the waveform domain and the
spectrogram (STFT) domain in parallel branches of a U-Net with a transformer at the bottleneck, then
fuses them. Intuition for each piece:

- **U-Net (encoder→bottleneck→decoder with skip connections).** The encoder downsamples to a compact
  representation that captures *what* sources are present; the decoder upsamples back to full
  resolution; skip connections re-inject fine detail the encoder discarded, so transients (a hat, a
  pluck) survive. The network outputs, per source, a signal (waveform branch) or a **mask** applied to
  the mixture spectrogram (spectrogram branch) — a soft 0..1 gain per time–frequency bin saying "how
  much of this bin belongs to vocals".
- **Hybrid waveform + spectrogram.** The spectrogram branch is good at harmonic, tonal content (it
  *sees* pitch as horizontal lines); the waveform branch is good at transients and phase (which a
  magnitude spectrogram throws away). Fusing both beats either alone.
- **Transformer bottleneck.** Cross-attention lets the model use long-range context ("this is the
  chorus, the vocal is doubled") rather than deciding each frame in isolation.

`htdemucs_ft` is the **fine-tuned** four-stem model (vocals / drums / bass / other) — best overall
quality, the default. `htdemucs_6s` adds **piano + guitar** stems — directly useful for the project's
alt-piano focus — but its piano stem has known artifacts, so it is opt-in. Demucs is **maintenance-only**
(creator left Meta); we keep it behind the `StemSeparator` port so the SOTA **BS-RoFormer** (via
`audio-separator`) is a config swap, not a rewrite (STACK.md §4).

**Known artifacts (handle, don't trust blindly — PITFALLS.md).** Per-stem auto-rescale breaks *relative*
stem levels; hi-hat/cymbal bleed leaks into vocals; vocal reverb is often left in "other"; dense mixes
separate worse. We re-encode each stem at the model's native sample rate and **do not** re-normalize
across stems, so relative levels are preserved for a faithful sample.

### Retention is content-addressed (and that is what makes it idempotent)

Each stem's bytes are hashed (SHA-256 → the `audio_uri`) and stored once, write-if-absent — the same
content-addressing the Rust object store uses, so a stem the Python worker retains is readable by the
control plane with no format negotiation. Because a deterministic separator is a *pure function* of
(track audio, model), re-separating a track yields **identical bytes → identical hash → the same key
and the same DB row**. Retention de-duplicates for free; the DB carries a `unique (reference_track_id,
audio_uri)` constraint so a redelivered or repeated separation job is a no-op rather than a duplicated
library. Every stem records `separator_model` + `separator_version` so a re-separation under a better
model lands under a different key (both kept, distinguishable) and the credits sheet is honest about
*how* a sample was isolated.

### Attribution-clean sampling vs. copy-and-claim-original — and the honest legal reality

The project's stance is **attribution-clean sampling**: a sample is literal copied audio, so its source
is tracked and credited rather than laundered into "original" material. But credit is not a license, and
the system says so, in-context:

- **Sampling a copyrighted recording is infringement regardless of personal or portfolio intent.** In
  key precedent there is *no de-minimis safe harbor* for sound-recording sampling (US *Bridgeport*), and
  a portfolio is **published**, not private use. "It's just a portfolio" is not a defense.
- **Attribution ≠ permission.** A credits sheet is honest and good practice; it does **not** confer the
  right to use the sample. The `credits` output and `sample show` both state this explicitly, and
  `rights_status` ∈ {`copyrighted_uncleared`, `royalty_free`, `own_work`, `unknown`} is a first-class
  field from day one — cheap to record now, a forensic nightmare to reconstruct later (PITFALLS.md
  Pitfall 7). Prefer royalty-free / own material for anything that ships publicly.

### The attribution-completeness invariant is structural (SAMP-03) — the integrity boundary

This is the headline, and it mirrors the eval gate: *the harness gates; the agent explores.* The Rust
control plane makes **incomplete-attribution placement unrepresentable**:

- A `PartialAttribution` (every field `Option`) is what the CLI gathers from the resolved stem + the
  `--artist` / `--time-range` / `--rights` / `--title` flags. A `CompleteAttribution` has **every field
  non-`Option`** — it *cannot represent* a missing field. The only path from user input to a
  `CompleteAttribution` is `PartialAttribution::into_complete()`, which validates and lists exactly what
  is missing (a whitespace-only artist counts as missing; an inverted time range counts as missing).
- The sampled-placement gate (`state_machine::place`) requires a `&CompleteAttribution`, and
  `Fragment::apply(Place)` is **refused** for `sampled` provenance — so there is no ungated path that
  writes `Placed` onto a sample. With partial attribution a sample *cannot be placed*; with complete
  attribution it can; the bypass does not exist because it cannot be spelled. (Rust tests prove all
  three.) `sampled` still travels the human lifecycle — never the AI eval gate — because a sample *is*
  source audio; the attribution gate is layered specifically on its `Analyzed → Placed` edge.

The Python worker's job is to make the library *exist* (separate + retain, with provenance); the Rust
control plane's job is to make sure nothing from it reaches an arrangement uncredited. Two languages,
one guarantee.

---

## 12. References

- **CREPE:** Kim, Salamon, Li, Bello, "CREPE: A Convolutional Representation for Pitch Estimation",
  ICASSP 2018. `torchcrepe` (Max Morrison) is the PyTorch port.
- **Chroma / CQT:** Brown, "Calculation of a constant Q spectral transform", JASA 1991;
  librosa docs, `feature.chroma_cqt`.
- **Onsets / beat tracking:** Bello et al., "A Tutorial on Onset Detection" (2005);
  Ellis, "Beat Tracking by Dynamic Programming", J. New Music Research 2007 (librosa's algorithm).
- **Key finding:** Krumhansl, *Cognitive Foundations of Musical Pitch* (1990); Temperley's revisions of
  the K-S profiles.
- **Loudness:** ITU-R BS.1770-4; EBU R128; `pyloudnorm` (Steinmetz & Reiss).
- **CLAP:** Wu et al., "Large-scale Contrastive Language-Audio Pretraining…", ICASSP 2023 (LAION-CLAP);
  Radford et al., CLIP (the contrastive idea), 2021.
- **ANN / pgvector:** Malkov & Yashunin, "Efficient and robust approximate nearest neighbor search using
  HNSW graphs", 2018; pgvector documentation (IVFFlat vs HNSW, operators).
- **CLAP zero-shot genre (weakness):** Wu et al. (LAION-CLAP) note language supervision helps tagging but
  is "less useful for genre classification"; ReCLAP (arXiv 2409.09213) reports zero-shot CLAP subpar vs
  supervised — hence coarse-tag-only here (`.planning/research/PITFALLS.md` Pitfall 5).
- **Mid/side & loudness for reference targets:** ITU-R BS.1770-4 (loudness, reused from §7); mid/side
  (M/S) stereo decomposition for width — standard mastering DSP (`numpy`/`soundfile`, no extra lib).
- **Non-cloning as a typed boundary:** `.planning/research/ARCHITECTURE.md` Pattern 2 (reference as
  conditioning, not a fragment) + `PITFALLS.md` Pitfall 6 (clone-boundary leak — type the asymmetry).
- **Source separation (Demucs):** Défossez, "Hybrid Spectrogram and Waveform Source Separation" (MDX
  2021) and Rouard, Massa, Défossez, "Hybrid Transformers for Music Source Separation" (`htdemucs`,
  ICASSP 2023). BS-RoFormer (the SOTA swap path) via `nomadkaraoke/python-audio-separator`.
- **Sampling copyright reality:** *Bridgeport Music v. Dimension Films* (no de-minimis safe harbor for
  sound-recording sampling); `.planning/research/PITFALLS.md` Pitfall 7 — attribution ≠ permission; a
  portfolio is published, not private use.
- **Attribution-completeness as a typed gate:** `.planning/research/ARCHITECTURE.md` Pattern 3 (sampled
  on the human path + the attribution invariant) — mirrored in `crates/nameless-core/src/attribution.rs`
  (`Partial` vs `Complete`) + `state_machine.rs::place` (the no-bypass placement gate).
