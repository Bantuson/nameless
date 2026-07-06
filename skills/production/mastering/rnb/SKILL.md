---
name: rnb-mastering
description: "Transparent loudness-focused mastering craft — chain order, M/S EQ, RMS compression, upward processing, and limiting — load when mastering an R&B track to a loudness target."
status: draft
stage: mastering
genre: rnb
confidence: LOW
prompt_version: file-draft-v1
---

# Rnb · Mastering — production skill

> Authored by the Nameless knowledge pipeline from 38 cited claim(s) across 1 source(s). Confidence: LOW. DRAFT — pending human spot-audit; not yet promoted to the arranger/mixer agents.
> Every assertion below is traceable to a source quote (see Citations). Synthesized strictly over the extracted claim set — no claim, number, or technique was invented.

## Default — act on this

Default approach: Balance the frequency response in a way that best represents the song — that is mastering's first job — and increase perceived loudness while preserving dynamics. Place an EQ first in the mastering chain to balance the frequency response before any processing, control the RMS (average) loudness with a compressor after the balancing EQ so less peak compression is needed later, then use an upward processor to bring up quieter details while retaining peaks, plus a versatile limiter — no more tools are needed. Use the limiter last to add the final bit of loudness while controlling peaks in a way that doesn't change the timbre, and measure loudness with a LUFS meter but, most importantly, reassess the sound by ear.

- M88T8jFL2uU @ 00:20 (clm_6ee27ba97edd4e9d) — "to balance the frequency response in a"
- M88T8jFL2uU @ 00:23 (clm_0930401011ce9e0a) — "perceived loudness while preserving dynamics,"
- M88T8jFL2uU @ 01:21 (clm_b42a16d568275fe7) — "First is an EQ to balance the"
- M88T8jFL2uU @ 01:26 (clm_65c179f5d68d73c0) — "Next, we’ll control the RMS or"
- M88T8jFL2uU @ 00:53 (clm_7a7e6ed9a10aebc5) — "peaks and a versatile limiter is all you need."
- M88T8jFL2uU @ 02:07 (clm_091597782d28f1f3) — "Then, the limiter will introduce the last bit of"
- M88T8jFL2uU @ 08:18 (clm_583532187a1cceb3) — "Measure the loudness with a LUFS meter, but"

## Consensus — corroborated across sources

### mastering-goals — 1 source(s) agree
Balance the frequency response in a way that best represents the song — that is mastering's first job.
- M88T8jFL2uU @ 00:20 (clm_6ee27ba97edd4e9d) — "to balance the frequency response in a"

### loudness-vs-dynamics — 1 source(s) agree
Increase perceived loudness while preserving dynamics.
- M88T8jFL2uU @ 00:23 (clm_0930401011ce9e0a) — "perceived loudness while preserving dynamics,"

### chain-order — 1 source(s) agree
Place an EQ first in the mastering chain to balance the frequency response before any processing. Control the RMS (average) loudness with a compressor after the balancing EQ so less peak compression is needed later.
- M88T8jFL2uU @ 01:21 (clm_b42a16d568275fe7) — "First is an EQ to balance the"
- M88T8jFL2uU @ 01:26 (clm_65c179f5d68d73c0) — "Next, we’ll control the RMS or"

### mastering-chain-tools — 1 source(s) agree
Use a fully parametric M/S EQ to control the frequency response and stereo image, a saturator and/or an RMS compressor to control dynamics and fill the frequency response, and an upward processor to bring up quieter details while retaining peaks, plus a versatile limiter — no more tools are needed.
- M88T8jFL2uU @ 00:41 (clm_7c9caca62e3d8570) — "A fully parametric M/S EQ to control the"
- M88T8jFL2uU @ 00:47 (clm_eea893a4b09410a9) — "and/or an RMS compressor to control dynamics and"
- M88T8jFL2uU @ 00:53 (clm_7a7e6ed9a10aebc5) — "peaks and a versatile limiter is all you need."

### minimal-chain — 1 source(s) agree
Avoid conflicting processors — each one forces another processor to undo it and makes the sound more processed and unpleasant.
- M88T8jFL2uU @ 01:06 (clm_3980a6f3f5749056) — "The more conflicting processing you have, the"

### linear-phase-eq — 1 source(s) agree
Use a linear-phase EQ when mastering. Keep the linear-phase EQ at a low-latency setting so pre-ringing distortion stays minimal and affects transients less than a zero-latency EQ.
- M88T8jFL2uU @ 02:57 (clm_08fbafcd463352d4) — "When mastering, a linear phase EQ is a good"
- M88T8jFL2uU @ 03:02 (clm_a410b894cb9808fd) — "the pre-ringing distortion is very minimal and"

### balancing-eq — 1 source(s) agree
Treat these balancing filters as near-universal starting moves, varying the exact settings per song.
- M88T8jFL2uU @ 03:50 (clm_091e3eeaa2e6a0a7) — "but these filters are almost always useful when"

### side-lows-highpass — 1 source(s) agree
High-pass the side-image lows on the first mastering EQ. Because the EQ is linear phase, use an 18dB or 24dB per octave high-pass filter without messing up the phase rotation, and raise the side high-pass filter to between the fundamental range and the second-order harmonic range so everything below it is identical in both channels. Add a second side-image high-pass at the tone-shaping stage because earlier processing reintroduces information into the side image of the lows.
- M88T8jFL2uU @ 03:08 (clm_b9c4ba9848b24295) — "attenuate the side image lows with"
- M88T8jFL2uU @ 03:13 (clm_1c4a59f6b28b1fa8) — "phase we can use an 18dB or 24dB per octave"
- M88T8jFL2uU @ 03:19 (clm_b99357a63aca789b) — "to somewhere between the fundamental"
- M88T8jFL2uU @ 06:54 (clm_d1f9b9c3d2bc5358) — "Also, I’ll use another side-image"

### low-mid-dip — 1 source(s) agree
Dip the low mids slightly around 250Hz to reduce masking of higher frequencies and reduce muddiness.
- M88T8jFL2uU @ 03:31 (clm_b7d397582d6efb08) — "A small dip in the low mids around 250Hz will"

### high-mid-resonance-dip — 1 source(s) agree
Find high-mid resonances — vocal nasal resonances and busy instruments — and apply a small dip there.
- M88T8jFL2uU @ 03:43 (clm_0c76187ed5af733f) — "this area too busy, so a small dip helps."

### mid-side-balance — 1 source(s) agree
Establish a balance between differing (side) and identical (mid) information in the left and right channels.
- M88T8jFL2uU @ 00:28 (clm_76ac3d7a81558a87) — "differing info in the left and"

### mid-side-eq — 1 source(s) agree
Boost a mid-range side-image bell to make the stereo image more impressive without unbalancing the frequency response.
- M88T8jFL2uU @ 07:14 (clm_0a28ae4b248b7860) — "bell makes the stereo image more"

### air-band — 1 source(s) agree
Boost the air frequencies on the side alone to expand them, in the mid to focus them, or identically in mid and side.
- M88T8jFL2uU @ 07:21 (clm_cd0b14c1b5385d5e) — "The air frequencies can be boosted on the"

### master-compression — 1 source(s) agree
Compress the master so transparently that you cannot hear the compression — aim for about 1 to 2 dB of compressor attenuation using a mix of peak and RMS compression.
- M88T8jFL2uU @ 03:59 (clm_db68c1c2a837839a) — "goal is to not be able to hear"
- M88T8jFL2uU @ 04:02 (clm_c522880991f73c8f) — "it. I want to achieve about a dB to 2 of"

### rms-compression — 1 source(s) agree
Set the compressor to almost complete RMS compression while controlling a small amount of the peaks.
- M88T8jFL2uU @ 04:13 (clm_6e6d59a342dfe2ad) — "it to almost complete RMS compression, but then"

### saturation — 1 source(s) agree
If you want more distortion, introduce the saturator first and then the upward processor.
- M88T8jFL2uU @ 01:43 (clm_84c75578c7fbcddd) — "If you want more distortion, then introduce the"

### upward-processing — 1 source(s) agree
Prefer upward processing for loudness — reshaping the wave from the quieter points up retains the timbre and the impact of transients. For a cleaner master, use the upward processor alone — it already adds mild saturation; combine upward processing with saturation and limiting to bring up detail and get a loud sound without heavy limiting. Audition multiple upward processors — each shapes differently and introduces unique harmonics — and pick the one that complements the track.
- M88T8jFL2uU @ 05:42 (clm_a4a8085e393fa9d9) — "which typically retains the timbre, and the impact"
- M88T8jFL2uU @ 01:38 (clm_b182aaa4e5afcbb2) — "work since it adds mild saturation."
- M88T8jFL2uU @ 05:24 (clm_3014f9e0b31a1b86) — "it helps bring up detail and create a loud"
- M88T8jFL2uU @ 05:51 (clm_5dc7fbe3f0974a65) — "unique harmonics. Let’s listen to the"

### limiting — 1 source(s) agree
Use the limiter last to add the final bit of loudness while controlling peaks in a way that doesn't change the timbre. Keep pre-limiter peak and RMS control subtle so the final limiter attenuates no more than a few dB; if hitting the target LUFS needs more limiting than that, use the earlier processors to make the signal louder and more controlled before the limiter.
- M88T8jFL2uU @ 02:07 (clm_091597782d28f1f3) — "Then, the limiter will introduce the last bit of"
- M88T8jFL2uU @ 04:26 (clm_09ebcac28dd26b29) — "have to attenuate more than a few dB."
- M88T8jFL2uU @ 08:01 (clm_e90f0bcbb3abf356) — "If you have to attenuate more than that to"

### tone-shaping-eq — 1 source(s) agree
Once dynamics are controlled and quiet details brought up, control the tonal balance with broad EQ filters — dip the low mids if needed, then boost the lows and the high mids. If the limited master no longer sounds the way you want, rebalance it at the tone-shaping EQ.
- M88T8jFL2uU @ 02:03 (clm_4b6f2b862adfd97a) — "balance with broad EQ filters."
- M88T8jFL2uU @ 07:05 (clm_28a19d33f758e90c) — "but a dip in the low mids if needed,"
- M88T8jFL2uU @ 08:28 (clm_9be73b8aea899d96) — "If not, check the tone-shaping EQ - this is where"

### loudness-metering — 1 source(s) agree
Measure loudness with a LUFS meter but, most importantly, reassess the sound by ear.
- M88T8jFL2uU @ 08:18 (clm_583532187a1cceb3) — "Measure the loudness with a LUFS meter, but"

## Contested — both camps preserved

### limiter-settings — contested (3 camps)
**[release-above-100ms]** (1 source(s)) Set the limiter release time above 100ms.
  - M88T8jFL2uU @ 07:51 (clm_b8e3528daed0ea82) — "recommend a release time above 100ms,"
**[channel-linking-60-80]** (1 source(s)) Set limiter channel linking around 60-80.
  - M88T8jFL2uU @ 07:56 (clm_ecb0b37208529cab) — "channel linking around 60-80&, and"
**[attenuation-max-3db]** (1 source(s)) Allow at most 3dB of limiter attenuation.
  - M88T8jFL2uU @ 07:56 (clm_ed207bdfbac08c4f) — "only 3dB of attenuation at most."
_The opinionated default above takes a side; this block preserves the disagreement so the agent (and you) can reason about the trade-off rather than inherit a laundered consensus._

## Citations

- `clm_6ee27ba97edd4e9d`  M88T8jFL2uU @ 00:20  "to balance the frequency response in a"
- `clm_0930401011ce9e0a`  M88T8jFL2uU @ 00:23  "perceived loudness while preserving dynamics,"
- `clm_b42a16d568275fe7`  M88T8jFL2uU @ 01:21  "First is an EQ to balance the"
- `clm_65c179f5d68d73c0`  M88T8jFL2uU @ 01:26  "Next, we’ll control the RMS or"
- `clm_7a7e6ed9a10aebc5`  M88T8jFL2uU @ 00:53  "peaks and a versatile limiter is all you need."
- `clm_091597782d28f1f3`  M88T8jFL2uU @ 02:07  "Then, the limiter will introduce the last bit of"
- `clm_583532187a1cceb3`  M88T8jFL2uU @ 08:18  "Measure the loudness with a LUFS meter, but"
- `clm_7c9caca62e3d8570`  M88T8jFL2uU @ 00:41  "A fully parametric M/S EQ to control the"
- `clm_eea893a4b09410a9`  M88T8jFL2uU @ 00:47  "and/or an RMS compressor to control dynamics and"
- `clm_3980a6f3f5749056`  M88T8jFL2uU @ 01:06  "The more conflicting processing you have, the"
- `clm_08fbafcd463352d4`  M88T8jFL2uU @ 02:57  "When mastering, a linear phase EQ is a good"
- `clm_a410b894cb9808fd`  M88T8jFL2uU @ 03:02  "the pre-ringing distortion is very minimal and"
- `clm_091e3eeaa2e6a0a7`  M88T8jFL2uU @ 03:50  "but these filters are almost always useful when"
- `clm_b9c4ba9848b24295`  M88T8jFL2uU @ 03:08  "attenuate the side image lows with"
- `clm_1c4a59f6b28b1fa8`  M88T8jFL2uU @ 03:13  "phase we can use an 18dB or 24dB per octave"
- `clm_b99357a63aca789b`  M88T8jFL2uU @ 03:19  "to somewhere between the fundamental"
- `clm_d1f9b9c3d2bc5358`  M88T8jFL2uU @ 06:54  "Also, I’ll use another side-image"
- `clm_b7d397582d6efb08`  M88T8jFL2uU @ 03:31  "A small dip in the low mids around 250Hz will"
- `clm_0c76187ed5af733f`  M88T8jFL2uU @ 03:43  "this area too busy, so a small dip helps."
- `clm_76ac3d7a81558a87`  M88T8jFL2uU @ 00:28  "differing info in the left and"
- `clm_0a28ae4b248b7860`  M88T8jFL2uU @ 07:14  "bell makes the stereo image more"
- `clm_cd0b14c1b5385d5e`  M88T8jFL2uU @ 07:21  "The air frequencies can be boosted on the"
- `clm_db68c1c2a837839a`  M88T8jFL2uU @ 03:59  "goal is to not be able to hear"
- `clm_c522880991f73c8f`  M88T8jFL2uU @ 04:02  "it. I want to achieve about a dB to 2 of"
- `clm_6e6d59a342dfe2ad`  M88T8jFL2uU @ 04:13  "it to almost complete RMS compression, but then"
- `clm_84c75578c7fbcddd`  M88T8jFL2uU @ 01:43  "If you want more distortion, then introduce the"
- `clm_a4a8085e393fa9d9`  M88T8jFL2uU @ 05:42  "which typically retains the timbre, and the impact"
- `clm_b182aaa4e5afcbb2`  M88T8jFL2uU @ 01:38  "work since it adds mild saturation."
- `clm_3014f9e0b31a1b86`  M88T8jFL2uU @ 05:24  "it helps bring up detail and create a loud"
- `clm_5dc7fbe3f0974a65`  M88T8jFL2uU @ 05:51  "unique harmonics. Let’s listen to the"
- `clm_09ebcac28dd26b29`  M88T8jFL2uU @ 04:26  "have to attenuate more than a few dB."
- `clm_e90f0bcbb3abf356`  M88T8jFL2uU @ 08:01  "If you have to attenuate more than that to"
- `clm_4b6f2b862adfd97a`  M88T8jFL2uU @ 02:03  "balance with broad EQ filters."
- `clm_28a19d33f758e90c`  M88T8jFL2uU @ 07:05  "but a dip in the low mids if needed,"
- `clm_9be73b8aea899d96`  M88T8jFL2uU @ 08:28  "If not, check the tone-shaping EQ - this is where"
- `clm_b8e3528daed0ea82`  M88T8jFL2uU @ 07:51  "recommend a release time above 100ms,"
- `clm_ecb0b37208529cab`  M88T8jFL2uU @ 07:56  "channel linking around 60-80&, and"
- `clm_ed207bdfbac08c4f`  M88T8jFL2uU @ 07:56  "only 3dB of attenuation at most."
