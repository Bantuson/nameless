"""``extractability_score`` — the pure gate that decides whether a transcript is teachable craft.

THIS IS THE HEART OF THE PHASE (PITFALLS #1, the user's "quality in, quality out" thesis made concrete).
The knowledge layer is built from "100+ tutorials", but a count of videos is not a count of *extractable
claims*. A transcript can be present and still teach nothing: a producer drags a filter, A/Bs two presets,
and says "and then you just do that and boom". The caption captured words; it captured no craft. If that
flows into distillation unweighted, the LLM will invent specificity to fill the void — confident wrong
craft, propagated into every generation. So extractability is a GATE BEFORE distillation, not a metric
after it.

The score is a weighted blend of four *positive* signals, then ATTENUATED by a visual-only penalty:

    base  = w_caption * caption_source_weight     # manual > asr > auto > none      (PITFALLS: caption trust)
          + w_density * word_density              # is anyone actually talking?
          + w_vocab   * vocab_presence            # producer jargon ⇒ teaching, not vibing
          + w_action  * actionable_ratio          # imperative/parameterized sentences ⇒ instructions
    score = base * (1 - visual_only_penalty)      # "as you can see…" with no numbers ⇒ crush it

Every term is in [0, 1]; the weights sum to 1, so ``base`` is in [0, 1] and the multiplicative penalty
keeps ``score`` in [0, 1]. The penalty is *multiplicative* on purpose: a transcript that is mostly
screen-pointing should be crushed even if it name-drops a few plugins — pointing at the screen is exactly
the failure mode we refuse to launder into a SKILL.md.

Pure: ``RawTranscript`` in, ``ExtractabilityResult`` out. No I/O, no model — so the weights and thresholds
are exhaustively testable against crafted transcripts (a rich manual one KEEPs; a deixis-only one is
flagged ``visual_only`` and does NOT keep).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import (
    CaptionSource,
    ExtractabilityResult,
    RawTranscript,
    Verdict,
)
from .vocab import (
    ACTIONABLE_VERBS,
    PRODUCTION_VOCAB,
    count_param_mentions,
    count_visual_deixis,
    sentences,
    words,
)

# Caption-source trust (PITFALLS #1): manual is gold; faster-whisper ASR beats YouTube auto-captions on
# producer jargon + code-switching; auto-captions are noisy; none means no spoken text recovered.
CAPTION_SOURCE_WEIGHT: dict[CaptionSource, float] = {
    CaptionSource.MANUAL: 1.0,
    CaptionSource.ASR: 0.85,
    CaptionSource.AUTO: 0.5,
    CaptionSource.NONE: 0.0,
}


@dataclass(frozen=True)
class ScoringConfig:
    """Tunable weights + thresholds for the extractability gate (kept out of the logic, defaulted sanely).

    The defaults are a starting calibration, not a law — PITFALLS says calibrate against real material.
    They live in a frozen dataclass so a caller (or a future per-genre calibration) can pass an override
    without editing the function.
    """

    # weights (must sum to ~1.0 — asserted at construction)
    w_caption: float = 0.30
    w_density: float = 0.15
    w_vocab: float = 0.25
    w_actionable: float = 0.30

    # word-density normalization: a healthy tutorial speaks ~120 words/min of meaningful content.
    target_words_per_min: float = 120.0
    # vocab-presence normalization: this many DISTINCT producer terms ⇒ full marks.
    target_distinct_vocab: int = 8
    # visual-only penalty shape
    visual_phrase_floor: int = 2          # need at least this many deixis phrases before any penalty
    visual_penalty_per_phrase: float = 0.12  # each deixis phrase (beyond a paired param) adds this much
    max_visual_penalty: float = 0.85      # cap so a transcript is never zeroed purely on deixis

    # verdict thresholds
    keep_threshold: float = 0.55
    reject_threshold: float = 0.30

    def __post_init__(self) -> None:
        total = self.w_caption + self.w_density + self.w_vocab + self.w_actionable
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")


DEFAULT_CONFIG = ScoringConfig()


def _word_density(word_count: int, duration_s: float, target_wpm: float) -> float:
    """Words-per-minute mapped into [0, 1] against a healthy target.

    A long video with almost no words (the visual-only tell) lands near 0; a normally-paced tutorial
    saturates at 1. Guard the degenerate cases (no duration / no words) so the function is total.
    """
    if word_count <= 0:
        return 0.0
    if duration_s <= 0:
        # No timing info (some caption sources omit it). Fall back to a coarse "enough words at all"
        # proxy so we neither reward nor unfairly punish: 200+ words ⇒ full marks.
        return min(1.0, word_count / 200.0)
    wpm = word_count / (duration_s / 60.0)
    return max(0.0, min(1.0, wpm / target_wpm))


def _vocab_presence(tokens: list[str], target_distinct: int) -> tuple[float, int]:
    """Distinct producer-jargon terms present, normalized to [0, 1]. Returns (score, distinct_hits).

    Matches both single-word terms and multi-word phrases ("log drum", "high pass") by scanning unigrams
    and bigrams against :data:`PRODUCTION_VOCAB`.
    """
    present: set[str] = set()
    token_set = set(tokens)
    # unigrams
    for term in PRODUCTION_VOCAB:
        if " " not in term and "-" not in term:
            if term in token_set:
                present.add(term)
    # multi-word / hyphenated phrases — check against the reconstructed text windows
    joined = " ".join(tokens)
    for term in PRODUCTION_VOCAB:
        if " " in term or "-" in term:
            if term in joined:
                present.add(term)
    hits = len(present)
    score = min(1.0, hits / float(target_distinct)) if target_distinct > 0 else 0.0
    return score, hits


def _actionable_ratio(sents: list[str]) -> float:
    """Fraction of sentences that are actual instructions — an imperative verb OR a numeric parameter.

    "cut around 300 hz" and "layer the second vocal" count; "this beat is so clean" does not. This is the
    signal that separates a lesson from commentary.
    """
    if not sents:
        return 0.0
    actionable = 0
    for sent in sents:
        low = sent.lower()
        toks = set(words(low))
        has_verb = bool(toks & ACTIONABLE_VERBS)
        has_param = count_param_mentions(low) > 0
        if has_verb or has_param:
            actionable += 1
    return actionable / len(sents)


def _visual_only_penalty(text: str, cfg: ScoringConfig) -> float:
    """How much to attenuate the score for screen-pointing deixis unsupported by spoken values.

    The key nuance: "pull it down to around 300 Hz" is fine — the deixis is *paired with a real value*.
    "and you just do that, boom" is not. So we count deixis phrases, subtract the number of numeric
    parameters present (each param "pays for" one deixis), and only penalize the unpaid remainder beyond
    a small floor. A transcript that is mostly unpaid pointing gets crushed (up to ``max_visual_penalty``).
    """
    low = text.lower()
    # WR-01: word-boundaried + non-overlapping deixis count (no "boomy" false positive, no double-count
    # of overlapping phrases like "just like that").
    deixis = count_visual_deixis(low)
    params = count_param_mentions(low)
    unpaid = deixis - params
    if unpaid < cfg.visual_phrase_floor:
        return 0.0
    penalty = (unpaid - cfg.visual_phrase_floor + 1) * cfg.visual_penalty_per_phrase
    return max(0.0, min(cfg.max_visual_penalty, penalty))


def _verdict(score: float, source: CaptionSource, cfg: ScoringConfig) -> Verdict:
    """Map score + signals to KEEP / LOW_SIGNAL / REJECT.

    The visual-only penalty is already folded into ``score`` (see ``extractability_score``), so the
    verdict is purely score+source driven — no separate ``visual_penalty`` argument is needed (IN-01).
    """
    if source is CaptionSource.NONE:
        # No spoken text recovered at all (and ASR did not run / produced nothing). Nothing to distil.
        return Verdict.REJECT
    if score >= cfg.keep_threshold:
        return Verdict.KEEP
    if score < cfg.reject_threshold:
        return Verdict.REJECT
    return Verdict.LOW_SIGNAL


def extractability_score(
    transcript: RawTranscript,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> ExtractabilityResult:
    """Score one transcript's extractability in [0, 1] with explainable components, flags, and a verdict.

    Deterministic and pure. See module docstring for the formula.
    """
    cfg = config
    text = transcript.full_text()
    tokens = words(text)
    word_count = len(tokens)
    duration_s = transcript.duration_s()
    sents = sentences(text)

    caption_weight = CAPTION_SOURCE_WEIGHT.get(transcript.caption_source, 0.0)
    density = _word_density(word_count, duration_s, cfg.target_words_per_min)
    vocab_score, vocab_hits = _vocab_presence(tokens, cfg.target_distinct_vocab)
    actionable = _actionable_ratio(sents)
    visual_penalty = _visual_only_penalty(text, cfg)

    base = (
        cfg.w_caption * caption_weight
        + cfg.w_density * density
        + cfg.w_vocab * vocab_score
        + cfg.w_actionable * actionable
    )
    score = max(0.0, min(1.0, base * (1.0 - visual_penalty)))

    verdict = _verdict(score, transcript.caption_source, cfg)

    # ---- flags: machine-actionable reasons (what the CLI and Phase-4 weighting key on) ----
    flags: list[str] = []
    if transcript.caption_source is CaptionSource.NONE:
        flags.append("no_captions")
    if transcript.caption_source is CaptionSource.AUTO:
        flags.append("auto_caption_noise")
    if density < 0.34:
        flags.append("low_word_density")
    if vocab_hits < 3:
        flags.append("sparse_vocab")
    if actionable < 0.15:
        flags.append("low_actionable")
    if visual_penalty > 0.0:
        flags.append("visual_only")
    if verdict is Verdict.LOW_SIGNAL:
        flags.append("low_signal")

    return ExtractabilityResult(
        video_id=transcript.video_id,
        score=round(score, 4),
        verdict=verdict,
        caption_source_weight=round(caption_weight, 4),
        word_density=round(density, 4),
        vocab_presence=round(vocab_score, 4),
        actionable_ratio=round(actionable, 4),
        visual_only_penalty=round(visual_penalty, 4),
        word_count=word_count,
        vocab_hits=vocab_hits,
        flags=flags,
    )
