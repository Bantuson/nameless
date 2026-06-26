# Feature Research

**Domain:** Audio-native AI music composition + tutorial-distilled production-knowledge layer + reference-track context + attribution-tracked sampling (R&B × amapiano/alternative-piano × deep house, Sonder/Brent Faiyaz north star)
**Researched:** 2026-06-26
**Confidence:** HIGH on genre/production craft and on sampling/attribution norms (verified against producer sources); MEDIUM on knowledge-ingestion feature conventions (verified against research/industry but the exact "tutorials → authored Claude Skills" shape is novel, so few direct precedents).

> Scope note: this file researches the **new and fuzzy** areas of the build — the knowledge-ingestion pipeline, reference-track vibe context, attribution-tracked sampling, and the **production-knowledge taxonomy** that the Skills must target. The PRD's core composition loop (capture → analyze → arrange → generate → eval-gate → mix → master) is treated as already-specified table stakes and is not re-derived here.

---

## Feature Landscape

Each row is tagged by sub-domain: **[KNOW]** knowledge-ingestion, **[COMPOSE]** AI composition assistant, **[REF]** reference-track context, **[SAMPLE]** attribution sampling.

### Table Stakes (Users Expect These)

Missing these makes the corresponding subsystem feel broken or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **[KNOW]** Transcript fetch + per-claim source binding (video ID + timestamp) | A distilled claim nobody can trace back is folklore, not knowledge; traceability is the baseline trust contract of any ingestion pipeline | MEDIUM | YouTube transcript API / `yt-dlp` auto-captions; store `{video_id, t_start, t_end, speaker?}` on every extracted claim. ASR fallback (Whisper) for videos lacking captions |
| **[KNOW]** Claim extraction into a structured schema (technique, parameters, genre, stage, confidence) | Raw transcript text is unusable as agent grounding; claims must be atomized and typed | MEDIUM | LLM extraction with a fixed schema. Industry pattern: chunk → claim-extract LLM → filter LLM keeps only high-quality/generalizable claims |
| **[KNOW]** Cross-referencing the same claim across multiple videos (corroboration count) | Confidence has to come from agreement across independent sources, not one creator's opinion | MEDIUM | Cluster semantically-equivalent claims; confidence rises with independent corroboration. This is the "consensus" half of the layered output |
| **[KNOW]** Contradiction handling that preserves both sides | Producers genuinely disagree (e.g. log-drum on FLEX vs. layered samples); silently picking one erases real craft nuance | MEDIUM | Flag conflicting claims, keep both with evidence; the opinionated default is a *decision on top of* preserved conflict, never a deletion |
| **[KNOW]** Organize claims into a navigable production-stage × genre taxonomy | The whole value is a *logical* stack; unstructured claims can't become loadable Skills | MEDIUM | The taxonomy below is the spine. Each leaf maps to one authored SKILL.md + reference docs |
| **[KNOW]** Confidence scoring per claim/skill | Agents and the user need to know what's well-established vs. one-creator-said-it | LOW | Tiers (HIGH/MED/LOW) from corroboration count + source authority. Surface in the Skill so the agent weights accordingly |
| **[COMPOSE]** Key/tempo/grid-locked generation conditioned on the user's actual audio | The defining promise — generated parts must lock to the recorded fragment | HIGH | PRD-specified (MusicGen-Stem / MuseControlLite + beat-grid warp). Table stakes for *this* product specifically |
| **[COMPOSE]** Objective eval gate before any generated part is accepted | Without a gate, niche-genre generation fails silently; the gate makes failure visible | HIGH | PRD-specified (melody fidelity, key match, tempo lock, loudness delta, CLAP alignment). Generator/evaluator separation |
| **[COMPOSE]** Per-part provenance (human vs AI vs derived vs sampled) | Users must always see what came from them vs. the machine | LOW | PRD graph already has provenance + lineage edges; `sampled` is an additive enum value |
| **[COMPOSE]** Genre-aware defaults (tempo ranges, mix conventions) | A generic generator produces generic output; users expect the system to "know" amapiano sits ~112-115 BPM, private-school ~108-112 | LOW-MED | Comes *from* the knowledge layer — defaults are distilled claims, not hardcoded |
| **[REF]** Upload a finished song and extract a vibe/atmosphere description + measurable sonic targets | If you can show the system a song you love, that is richer context than any text prompt | MEDIUM | CLAP embedding + LLM vibe text (mood/space/era/texture/energy) + measurable targets (tempo range, LUFS, tonal balance, stereo width) |
| **[REF]** Strict separation of "vibe/sonic context" from "melodic/structural content" | Users (and the law/ethics) expect a reference to inform *sound*, not reproduce the *song* | MEDIUM | This boundary is the product's integrity line. Extract genre/tempo/LUFS/width; never melody/chords/lyrics/structure |
| **[SAMPLE]** Stem separation of uploaded tracks (drums/bass/vocals/other) | Sampling without clean stems is unusable; Demucs-grade separation is the expected baseline | MEDIUM | PRD already has Demucs in the worker plane |
| **[SAMPLE]** Provenance record on every promoted sample (source track, artist, stem, time-range) | A sample you can't attribute is a liability; provenance is the baseline of honest sampling | LOW | Extends the existing fragment provenance/lineage model |
| **[SAMPLE]** Auto-generated credits sheet on export listing every sample used | This is the standard surfacing of sample lineage (cf. Tracklib's per-stem credit model) | LOW | Roll up `sampled` fragments + their provenance into an export artifact |

### Differentiators (Competitive Advantage)

Where this product wins. These align directly with the Core Value ("quality in, quality out" via distilled craft + your taste).

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **[KNOW]** Tutorials distilled into **authored Claude Skills**, not a RAG vector store | A loadable, opinionated SKILL.md teaches the agent craft and costs ~its description until triggered; a vector dump bloats context and reasons worse | HIGH | The signature architectural bet. Output of ingestion is *authored prose + reference docs*, human-auditable, version-controlled |
| **[KNOW]** Layered output: one opinionated default **plus** preserved consensus/conflict evidence with citations | Actionable for agents (a default to act on) AND auditable for the user (the receipts) — most pipelines give you one or the other | HIGH | "Opinionated but traceable." The default is a synthesized decision; the evidence stays attached |
| **[KNOW]** Parent-technique decomposition for under-tutorialized sounds | Alternative-piano has thin tutorial coverage; reconstruct it from amapiano groove/log-drum + jazzy/soulful piano + deep-house space rather than fabricating | MEDIUM | A defensible epistemics move: build sparse-genre skills from well-covered parent techniques + real audio analysis, never from invented claims |
| **[KNOW]** Grounding sparse genres in **analysis of the artists' actual released tracks** | When tutorials run out, the records themselves are ground truth; run them through the CLAP/feature pipeline to extract real sonic signatures | MEDIUM | Reuses the existing audio feature pipeline; turns "no tutorial exists" into measured fact, not a guess |
| **[KNOW]** Artist/producer-anchored sourcing (Sonder/Brent Faiyaz; Ben Produces, Liyana Ricky, Lowbass Djy) alongside generic stage queries | Targets the specific north-star sound, not just generic genre coverage | LOW-MED | Discovery = (genre × stage) queries ∪ artist/producer-anchored queries |
| **[COMPOSE]** Agent grounded in distilled craft, not just raw generation | The arranger/mixer make *informed* choices (vocal-stack conventions, log-drum placement) because the Skill taught them — generic AINmusic tools don't | MEDIUM | The knowledge layer is the moat; generation models are swappable commodities behind the worker interface |
| **[REF]** Reference-track context fused with distilled craft at generation time | "Make it feel like *this* record" + "and here's how this genre is actually produced" is a combination text-to-music tools can't offer | MEDIUM | REF gives target sonics; KNOW gives the techniques to reach them |
| **[SAMPLE]** Persistent personal stem library — any stem promotable to a sample weeks later | Decouples "ingest the song now" from "use the stem whenever inspiration hits"; a durable creative asset, not a one-shot import | MEDIUM | Indefinite retention + browsable library; promotion creates a `sampled` fragment with full provenance |
| **[SAMPLE]** Attribution-clean-by-construction (provenance is mandatory, not optional metadata) | "Honest sampling" as a first-class stance vs. copy-and-claim-original | LOW | The credits sheet falls out of the data model for free because provenance is required at promotion |

### Anti-Features (Deliberately NOT Building)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Cloning / recreating a reference track** (melody, chords, structure) | "Just make me a song like this one" feels like the shortest path | Destroys the product thesis (intent translation, not imitation); ethical/legal hazard; collapses into a Suno-cover clone | Extract vibe + measurable non-melodic sonic targets only; never melody/harmony/structure/lyrics |
| **RAG / pgvector vector store for the tutorial knowledge** | RAG is the default reflex for "lots of documents → LLM" | Bloats agent context, reasons worse on noisy retrieved chunks, no opinionated synthesis, hard to audit | Authored Claude Skills + scripts (token-cheap until triggered, opinionated, version-controlled, human-auditable). *Note: pgvector still used for the per-project fragment-memory graph — different layer, don't conflate* |
| **Lyric generation + vocal synthesis** | "Finish the whole song including vocals" | PRD non-goal; the user *is* the vocalist — synthesizing voice contradicts capture-your-own-fragments | Capture the user's hums/vocals as fragments; layer/arrange them, never fabricate a voice |
| **Mining interviews / reactions / breakdowns as a primary knowledge source** | More videos = more knowledge | Low signal-to-noise, hard to extract structured technique claims, citation ambiguity | v1 leans on tutorial discovery + parent-technique decomposition + audio analysis; revisit only if coverage proves thin |
| **Auto-clearing / licensing samples for commercial release** (Tracklib-style clearance) | "Make my samples legally releasable" | PRD §15 defers commercial distribution; clearance is a whole compliance subsystem out of scope for personal/portfolio | Attribution-tracking + credits sheet for honesty/personal use; clearance flags deferred |
| **One-shot "generate the whole track" button** | Text-to-music UX trained users to expect it | Bypasses the compositional loop that is the entire product thesis; bypasses the eval gate | Fragment-by-fragment assembly with gates; the loop *is* the product |
| **A "confidence number" with no evidence behind it** | A single trust score is easy to display | A bare score is unfalsifiable and erodes trust the moment it's wrong | Confidence tier *plus* the corroborating/conflicting citations that produced it |
| **Full mixing console / per-genre mastering presets in v1** | "Real producers want full control" | PRD ships one chain per track (console is M3); scope creep | One pedalboard chain per lane + one master chain to LUFS target |

---

## The Production Stack of Skill (proposed taxonomy)

This is the spine the knowledge layer targets. **Two axes: production stage × genre.** Each cell is a candidate authored Skill (SKILL.md + reference docs). Not every cell needs to ship — prioritize by the north-star sound.

### Axis 1 — Production stages (the vertical stack, signal-flow order)

```
00  Foundations / theory   key, scale, tempo, groove feel, song-section vocabulary
01  Beats & rhythm         drum selection, kick/clap, swing, ghost notes, velocity
02  Groove engine          genre-defining low-rhythm element (log drum, house kick+bass)
03  Basslines              sub design, movement, interplay with the groove engine
04  Chords / keys          voicings, extensions, pads, piano/Rhodes, progression feel
05  Melody / leads         topline, hooks, countermelody, motif development
06  Vocals & layering      lead, doubles, octaves, harmony stacks, comping
07  Adlibs                 rhythmic ad-libs, falsetto flourishes, vocal texture beds
08  Sound design / synths  patch design, the genre's signature timbres
09  Sampling               chopping, pitching, stem reuse, attribution discipline
10  FX / atmospheres       reverb/delay sends, space, risers, foley, ambience
11  Arrangement            section structure, energy curve, drops, transitions
12  Mixing                 EQ/comp per lane, panning, stereo width, vocal glue
13  Mastering              loudness (LUFS), tonal balance, limiting
```

### Axis 2 — Genres / lanes

```
R&B (Sonder / Brent Faiyaz lane)
Amapiano (mainstream / soulful)
Private-school / Alternative-piano (jazzy, soulful, slower amapiano lane)
Deep house
[Fusion]  the north-star personal blend across the above
```

### The grid (what to author, priority-tagged)

`P1` = author for v1 (directly serves north-star sound). `P2` = author after validation. `—` = decompose from parents / defer.

| Stage \ Genre | R&B | Amapiano | Alt-piano / private-school | Deep house |
|---|---|---|---|---|
| 00 Foundations | P1 | P1 | P1 (decompose) | P2 |
| 01 Beats & rhythm | P1 | P1 | P2 | P1 |
| 02 Groove engine | P2 (laid-back drums) | **P1 (log drum)** | P1 (log drum, softer) | **P1 (kick+bass pump)** |
| 03 Basslines | P1 | P1 | P2 | P1 |
| 04 Chords / keys | **P1 (lush, extended)** | P2 | **P1 (jazzy piano/Rhodes)** | P2 (pads) |
| 05 Melody / leads | P1 | P2 | P2 | P2 |
| 06 Vocals & layering | **P1 (stacked harmonies)** | P2 | P2 | — |
| 07 Adlibs | **P1 (falsetto flourishes)** | P2 | — | — |
| 08 Sound design / synths | P2 | P1 (log-drum patch) | P2 | P1 (warm sub/pads) |
| 09 Sampling | P2 | P2 | P2 | P2 |
| 10 FX / atmospheres | **P1 (space, pads)** | P2 | P1 (airy pads) | **P1 (delay/dub space)** |
| 11 Arrangement | P1 | P1 | P2 | P1 |
| 12 Mixing | P1 | P2 | P2 | P1 |
| 13 Mastering | P2 | P2 | — | P2 |

**Reading the grid:** the **P1 cells cluster** around exactly the north-star fusion — R&B vocal layering/adlibs/lush chords/atmosphere + amapiano & alt-piano log-drum groove + jazzy piano + deep-house space and groove. Author those first; decompose the rest.

### What "good" looks like per area (the rubric a Skill encodes)

- **Groove engine:** the genre's identity lives here. "Good" = the signature low-rhythm element sits correctly in the pocket and carries forward momentum without crowding the sub.
- **Vocals & layering:** "good" = depth and width without mud — center lead, doubles/harmonies panned and EQ'd, glued with short plate reverb.
- **Chords/keys:** "good" = voicings with the right extensions and *space left for each element* (the private-school discipline) rather than a dense block.
- **Arrangement:** "good" = a deliberate energy curve with earned drops and clean transitions, not a static loop.
- **Mix/master:** "good" = clarity + space per element, hitting the streaming LUFS target with controlled tonal balance and stereo width.

---

## Genre-signature techniques the Skills must capture

Verified against producer/educator sources (see Sources). These are the concrete claims the knowledge layer must reliably distill.

### R&B (Sonder / Brent Faiyaz lane)
- **Stacked vocal harmonies** — often *triples* of each note (not just doubles), panned and EQ'd; pro stacks can run very deep. Center lead, doubles/harmonies spread L/R.
- **Octave stacking** — double the lead an octave up (brightness/energy, choruses) or down (weight).
- **Thirds** as the default harmony interval (natural, musical).
- **Rhythmic ad-libs + falsetto flourishes** — ad-libs typically recorded *once* (not stacked), filling space; airy harmonies layered over pad-driven beds.
- **Atmosphere** — intros built from a soft chorus of layered vocals into lush, pad-driven synths; slowed/pitch-shifted vocal sections as texture.
- **Mix glue** — short plate reverb to bind the stack; delay/reverb for space.

### Amapiano (mainstream + soulful)
- **Log drum** — the single defining sound: a hybrid between kick, 808, synth bass, and plucked marimba/kalimba. Commonly built on FL Studio FLEX (or layered samples — *a genuine consensus/conflict point to preserve*), shaped with distortion/soft-clipping and EQ for a melodic bounce. **Overlapping piano-roll notes** create the signature slide. Soft clipper for drive.
- **Tempo** — ~112-115 BPM mainstream.
- **Swing + ghost notes + velocity variation** — the bounce; without subtle timing/velocity humanization it sounds stiff and programmed.
- **Continuous shaker / hi-hat loop** — runs nearly unbroken, filling gaps between log-drum hits for rolling, hypnotic momentum.
- **Warm round basslines** — sine / low-passed sub complementing the log drum.

### Alternative-piano / private-school amapiano (jazzy, soulful, slower lane)
- A **refined, soulful, slower lane** foregrounding amapiano's deep-house and jazz roots; emerged from DJs adding live instruments.
- **Jazzy chord voicings + sustained, deep airy pads**; melody sets the mood.
- **Log drum still the foundation** but softer; **space left for each instrument and vocal** ("less nightclub, more sophisticated lounge").
- **Tempo** — soulful ~108-112 BPM (harder sgija/Bacardi push 116-122).
- *Under-tutorialized*: ground via parent-technique decomposition (amapiano groove + jazzy piano + deep-house space) **and** audio analysis of named artists' released tracks.

### Deep house
- **Groove + swing** — 5-15% swing on hats/percussion (16th-note or groove quantization).
- **Layered organic percussion** — claps, shakers, tambourines, congas for an organic feel; pan across the stereo field for space.
- **Atmospheric pads + deep basslines** as the bed.
- **Delay / dub effects** as the primary space-and-texture tool.
- **Mix emphasis on clarity and space** — every element well-defined, panned to carve room.

---

## Feature Dependencies

```
[Production-knowledge layer (KNOW)]
    └──grounds──> [AI composition agents (COMPOSE)]
                       └──requires──> [Audio feature pipeline (CLAP/librosa)]  ← also used by:
[Sparse-genre grounding]
    └──requires──> [Audio feature pipeline]   (analyze real released tracks)
    └──requires──> [Parent-technique skills already authored]

[Reference-track context (REF)]
    └──requires──> [Audio feature pipeline]   (CLAP + measurable targets)
    └──requires──> [Stem separation (Demucs)]  (shared with SAMPLE)
    └──enhances──> [AI composition agents]     (target sonics at generation/mix)

[Attribution sampling (SAMPLE)]
    └──requires──> [Stem separation (Demucs)]
    └──requires──> [Fragment provenance/lineage model]  (PRD graph + `sampled` enum)
    └──produces──> [Credits sheet on export]

[Transcript fetch] ──requires──> [Claim extraction] ──requires──> [Cross-ref + contradiction] ──requires──> [Taxonomy organization] ──produces──> [Authored Skills]

[Cloning a reference] ──CONFLICTS──> [REF non-cloning boundary]   (mutually exclusive by design)
```

### Dependency Notes
- **KNOW must precede COMPOSE quality:** the agents are only as good as the craft they're grounded in. Knowledge ingestion is an **M0 foundation**, parallel to the fragment-memory graph, not a later add-on.
- **Audio feature pipeline is the shared backbone:** COMPOSE (eval gate), REF (vibe + targets), SAMPLE-adjacent analysis, and sparse-genre grounding all depend on it. Build/stabilize it once in M0.
- **Stem separation is shared by REF and SAMPLE:** one Demucs capability serves both reference analysis and the sample library.
- **Sparse-genre grounding depends on parent skills existing first:** can't decompose alt-piano into amapiano-groove + jazzy-piano + deep-house-space until those parent Skills are authored.
- **`sampled` is additive, not a new subsystem:** it's a provenance enum value + attribution metadata on the existing graph.

---

## MVP Definition

### Launch With (M0 foundation)
- [ ] Transcript fetch + per-claim citation (video ID + timestamp) — traceability is non-negotiable
- [ ] Claim extraction into the stage × genre schema — raw transcript is unusable otherwise
- [ ] Cross-reference + contradiction handling (consensus/conflict preserved) — the trust contract
- [ ] Taxonomy organization → authored Skills for the **P1 cells** (R&B vocals/chords/adlibs/atmosphere; amapiano + alt-piano log-drum/groove/jazzy-piano; deep-house groove/space) — the north-star cluster
- [ ] Confidence tiering per claim/skill — agents and user must weight knowledge
- [ ] Audio feature pipeline (CLAP + librosa features) — shared backbone (PRD M0)
- [ ] Fragment capture + provenance model incl. `sampled` enum (PRD M0)

### Add After Validation (M1)
- [ ] Reference-track upload → vibe text + measurable non-melodic sonic targets — trigger: composition loop produces usable output and needs taste-steering
- [ ] Stem separation + persistent stem library + promote-to-sample + credits sheet — trigger: reference uploads exist, extend to sampling
- [ ] Sparse-genre grounding via parent decomposition + released-track analysis — trigger: P1 parent skills authored and validated
- [ ] Melody-conditioned generation + eval gate + mix/master (PRD M1)

### Future Consideration (v2+)
- [ ] Expand taxonomy to P2 cells (broader genre × stage coverage) — defer until P1 cluster proves the approach
- [ ] Non-tutorial source mining (interviews/breakdowns) — defer; only if tutorial coverage proves too thin
- [ ] Per-genre mastering presets / full console (PRD M3)
- [ ] Sample clearance/licensing flags — defer with commercialization (PRD §15)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Transcript fetch + citation | HIGH | LOW-MED | P1 |
| Claim extraction (schema) | HIGH | MEDIUM | P1 |
| Cross-ref + contradiction handling | HIGH | MEDIUM | P1 |
| Taxonomy → authored Skills (P1 cells) | HIGH | HIGH | P1 |
| Confidence tiering | MEDIUM | LOW | P1 |
| Genre-signature technique capture | HIGH | MEDIUM | P1 |
| Reference vibe + sonic targets | HIGH | MEDIUM | P2 |
| Non-cloning boundary enforcement | HIGH | MEDIUM | P2 |
| Stem library + promote-to-sample | MEDIUM | MEDIUM | P2 |
| Credits sheet on export | MEDIUM | LOW | P2 |
| Sparse-genre grounding (decompose + analyze) | MEDIUM-HIGH | MEDIUM | P2 |
| Expand to P2 taxonomy cells | MEDIUM | HIGH | P3 |
| Non-tutorial source mining | LOW | MEDIUM | P3 |

---

## Competitor Feature Analysis

| Feature | Suno / Udio | Tracklib | Splice | Our Approach |
|---------|-------------|----------|--------|--------------|
| Reference audio handling | Style/audio-influence weight 0-1 *and* a "cover" mode that extracts melody/structure | n/a | n/a | Vibe + measurable non-melodic targets ONLY; explicitly **no cover/clone mode** |
| Knowledge grounding | None (end-to-end model) | n/a | Sample-pack curation | Authored Skills distilled from 100+ tutorials with citations |
| Sampling provenance | n/a | Per-stem credits, royalty splits, clearance | Royalty-free packs | Provenance-by-construction + credits sheet (attribution, not clearance) |
| Composition control | Prompt + tags, one-shot | n/a | Manual in DAW | Fragment-by-fragment loop with hard eval gate |
| Confidence/traceability of craft | None | n/a | None | Layered: opinionated default + cited consensus/conflict |

**Key contrast:** Suno's "cover" mode is exactly the anti-feature we refuse — it extracts melody/harmony/structure and re-skins the song. Our reference layer deliberately stops at *sonic context* (the style-influence idea) and never crosses into content reproduction.

---

## Sources

- [InspiredByBeatz — Amapiano log drum creation](https://www.inspiredbybeatz.com/en/amapiano-production-how-the-log-drum-sound-is-created/)
- [RouteNote — How to make an Amapiano beat](https://create.routenote.com/blog/beatmakers-guide-how-to-make-an-amapiano-beat/)
- [Splice — What is Amapiano](https://splice.com/blog/what-is-amapiano-music/)
- [Roland Articles — Production hacks: Amapiano](https://articles.roland.com/production-hacks-creating-amapiano-tracks/)
- [Apple Music — Private-School 'Piano (subgenre framing)](https://music.apple.com/za/playlist/private-school-piano/pl.9e0d8bdae7284dbd9791f2f402e461de)
- [Melodigging — Underground / private-school amapiano](https://www.melodigging.com/genre/underground-amapiano)
- [Splice — Vocal layering techniques](https://splice.com/blog/vocal-layering-techniques/)
- [LANDR — Vocal layering: 7 ways to stack vocals](https://blog.landr.com/vocal-layering/)
- [Gearspace — Stacking R&B vocals / doubling (practitioner thread)](https://gearspace.com/board/rap-hip-hop-engineering-and-production/46479-stacking-r-amp-b-vocals-doubling.html)
- [Medium — Sonder Son: an analysis (Brent Faiyaz vocal approach)](https://medium.com/modern-music-analysis/sonder-son-an-analysis-a1ab5b16c367)
- [DeepHouseNetwork — Deep house production techniques](https://deephousenetwork.com/deep-house-music-production-techniques-software-and-tips-for-beginners/)
- [MusicRadar — 22 deep house production tips](https://www.musicradar.com/tuition/tech/22-deep-house-production-tips-153784)
- [Tracklib — Sample usage & clearance FAQ](https://support.tracklib.com/hc/en-us/articles/12416153374236-Sample-usage-and-clearance-FAQ)
- [Tracklib — How it works (per-stem credits)](https://www.tracklib.com/how-it-works)
- [Jack Righteous — Suno advanced sliders (style vs audio influence)](https://jackrighteous.com/en-us/blogs/guides-using-suno-ai-music-creation/how-to-use-suno-s-advanced-sliders-weirdness-style-audio-influence)
- [Suno API docs — Upload & cover audio (the cover/clone mode we reject)](https://docs.sunoapi.org/suno-api/upload-and-cover-audio)
- [arXiv 2511.16198 — SemanticCite: citation verification / claim-to-source binding](https://arxiv.org/html/2511.16198v1)
- [Buzzi.ai — RAG citation & confidence architecture](https://buzzi.ai/insights/ai-document-retrieval-rag-citation-architecture)
- [FINOS AI Governance — Source traceability for AI-generated information](https://air-governance-framework.finos.org/mitigations/mi-13_providing-citations-and-source-traceability-for-ai-generated-information.html)

---
*Feature research for: audio-native AI composition + tutorial-distilled production-knowledge layer (Nameless)*
*Researched: 2026-06-26*
