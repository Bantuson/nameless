"""extractability_score tests (KNOW-03) — the visual-only gate that refuses to fake craft.

These are the most important tests in the phase: they pin the behaviour that a rich, parameterized
tutorial KEEPs while a screen-pointing "as you can see... boom" transcript is flagged and does NOT.
"""

from __future__ import annotations

from knowledge_pipeline.domain.models import CaptionSource, Verdict
from knowledge_pipeline.pure.extractability import (
    DEFAULT_CONFIG,
    ScoringConfig,
    extractability_score,
)

from .conftest import make_transcript

RICH = [
    (0.0, 6.0, "Let's high-pass the log drum around 40 hz to clean the low end."),
    (6.0, 6.0, "Sidechain the bass to the kick and set the compressor release to 120 ms."),
    (12.0, 6.0, "Layer a shaker on the off-beats, pan it left, and boost 3 khz on the snare."),
    (18.0, 6.0, "Compress the drum bus with a 4 to 1 ratio and roll off below 200 hz."),
]

VISUAL_ONLY = [
    (0.0, 6.0, "Okay so we're just gonna do this, you see."),
    (6.0, 6.0, "As you can see I drag this guy up here like that."),
    (12.0, 6.0, "And then you just do that and boom, there you go."),
    (18.0, 6.0, "Right here, just like that, something like this."),
]


def test_rich_manual_transcript_keeps_with_high_score():
    t = make_transcript(caption_source=CaptionSource.MANUAL, segments=RICH)
    result = extractability_score(t)
    assert result.verdict is Verdict.KEEP
    assert result.score >= 0.6
    assert "visual_only" not in result.flags
    assert result.vocab_hits >= 6
    assert result.actionable_ratio > 0.5


def test_visual_only_transcript_is_flagged_and_not_kept():
    t = make_transcript(caption_source=CaptionSource.MANUAL, segments=VISUAL_ONLY)
    result = extractability_score(t)
    assert "visual_only" in result.flags
    assert result.visual_only_penalty > 0.0
    assert result.verdict is not Verdict.KEEP   # the whole point: do NOT fake this into the corpus
    assert result.score < 0.55


def test_numbers_pay_for_deixis_so_real_instructions_survive():
    # "pull it to like this, around 300 hz" — deixis PAIRED with a real value must not be penalized away.
    paired = [
        (0.0, 5.0, "pull the cutoff down like this to around 300 hz"),
        (5.0, 5.0, "then boost like that at 3 khz and cut 200 hz"),
        (10.0, 5.0, "set the ratio like this to 4 to 1 and the attack to 10 ms"),
    ]
    t = make_transcript(caption_source=CaptionSource.MANUAL, segments=paired)
    result = extractability_score(t)
    # each deixis is "paid for" by a numeric parameter ⇒ no/low visual penalty
    assert result.visual_only_penalty == 0.0


def test_boomy_lowend_is_not_penalized_as_visual_deixis():
    # WR-01: bare "boom" must not substring-match "boomy" — a bass tutorial saying "tighten the boomy low
    # end" is real craft, not screen-pointing. It must carry no visual penalty / no visual_only flag.
    craft = [
        (0.0, 6.0, "tighten the boomy low end and high-pass the log drum around 40 hz"),
        (6.0, 6.0, "the bass gets boomier below 80 hz so cut 60 hz and sidechain the kick"),
        (12.0, 6.0, "add a boombap kick and compress the bus at 4 to 1 with 120 ms release"),
    ]
    t = make_transcript(caption_source=CaptionSource.MANUAL, segments=craft)
    result = extractability_score(t)
    assert result.visual_only_penalty == 0.0
    assert "visual_only" not in result.flags


def test_overlapping_deixis_phrases_are_counted_once_not_doubled():
    # WR-01: "just like that" must count as ONE deixis phrase (not also "like that"); "and boom" as one
    # (not also "boom"). Verify the pure counter de-overlaps and word-bounds.
    from knowledge_pipeline.pure.vocab import count_visual_deixis

    assert count_visual_deixis("just like that") == 1          # not 2 (was: "like that" + "just like that")
    assert count_visual_deixis("and boom") == 1                # not 2 (was: "boom" + "and boom")
    assert count_visual_deixis("something like this") == 1     # not 2 (was: "like this" + "something like this")
    assert count_visual_deixis("the boomy boombap boomier kick") == 0  # no bare-token substring hits
    assert count_visual_deixis("boom, like that, you see") == 3        # three distinct genuine phrases


def test_caption_source_weighting_orders_manual_asr_auto_none():
    segs = RICH
    manual = extractability_score(make_transcript(caption_source=CaptionSource.MANUAL, segments=segs))
    asr = extractability_score(make_transcript(caption_source=CaptionSource.ASR, segments=segs))
    auto = extractability_score(make_transcript(caption_source=CaptionSource.AUTO, segments=segs))
    assert manual.caption_source_weight > asr.caption_source_weight > auto.caption_source_weight
    assert manual.score >= asr.score >= auto.score


def test_empty_none_transcript_rejects():
    t = make_transcript(caption_source=CaptionSource.NONE, segments=[])
    result = extractability_score(t)
    assert result.verdict is Verdict.REJECT
    assert "no_captions" in result.flags
    assert result.score == 0.0


def test_sparse_chitchat_is_low_signal_or_reject():
    chit = [
        (0.0, 8.0, "yeah man this beat is so clean i love this vibe"),
        (40.0, 8.0, "shout out to everyone watching appreciate the support"),
        (200.0, 8.0, "it is a sunday the weather is nice lets enjoy the music"),
    ]
    result = extractability_score(make_transcript(caption_source=CaptionSource.MANUAL, segments=chit))
    assert result.verdict in (Verdict.LOW_SIGNAL, Verdict.REJECT)
    assert "sparse_vocab" in result.flags


def test_score_is_bounded_and_components_in_unit_range():
    for src in CaptionSource:
        r = extractability_score(make_transcript(caption_source=src, segments=RICH))
        assert 0.0 <= r.score <= 1.0
        for comp in (r.caption_source_weight, r.word_density, r.vocab_presence, r.actionable_ratio, r.visual_only_penalty):
            assert 0.0 <= comp <= 1.0


def test_weights_must_sum_to_one():
    import pytest

    with pytest.raises(ValueError):
        ScoringConfig(w_caption=0.5, w_density=0.5, w_vocab=0.5, w_actionable=0.5)


def test_default_config_is_valid():
    assert abs(
        DEFAULT_CONFIG.w_caption + DEFAULT_CONFIG.w_density
        + DEFAULT_CONFIG.w_vocab + DEFAULT_CONFIG.w_actionable - 1.0
    ) < 1e-9
