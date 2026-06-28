"""Lexicons + patterns the extractability scorer reasons over — DATA, kept separate from the logic.

Four vocabularies, each a deliberate, reviewable list (not a model):
  * :data:`PRODUCTION_VOCAB`   — producer jargon. Its presence is evidence the transcript is teaching
                                 craft, not vibing ("sidechain", "log drum", "high-pass", "bus").
  * :data:`ACTIONABLE_VERBS`   — imperative craft verbs. A sentence with one is an *instruction*
                                 ("cut 300 hz", "layer the vocal"), not commentary.
  * :data:`VISUAL_ONLY_PHRASES`— deixis that points at the SCREEN, not the audio. "as you can see",
                                 "like this", "just like that", "boom" — the tell that the real lesson
                                 was visual and the transcript captured nothing teachable (PITFALLS #1).
  * :data:`PARAM_PATTERN`      — numeric parameters with units (Hz, dB, BPM, ms, %). A real value the
                                 LLM must EXTRACT, never invent. Their presence rescues a "like this"
                                 from the visual-only penalty ("pull it to like this, around 300 Hz").

These are intentionally lowercase, substring/word-matched on the lowercased transcript. The point is a
robust, explainable signal — not NLP perfection. The lists are easy to extend per genre as the corpus
teaches us which terms matter (amapiano/SA producer slang especially).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------------------------
# Producer jargon — domain-term density. Matched as whole words / phrases on the lowercased text.
# ---------------------------------------------------------------------------------------------
PRODUCTION_VOCAB: frozenset[str] = frozenset(
    {
        # signal processing
        "eq", "equalizer", "high-pass", "highpass", "low-pass", "lowpass", "high pass", "low pass",
        "shelf", "bell", "notch", "filter", "cutoff", "resonance",
        "compress", "compression", "compressor", "ratio", "threshold", "attack", "release", "knee",
        "sidechain", "side-chain", "side chain", "ducking",
        "reverb", "delay", "echo", "saturation", "saturate", "distortion", "limiter", "limiting",
        "transient", "transients", "stereo", "mono", "width", "pan", "panning", "mid-side", "mid/side",
        "automation", "automate", "lfo", "envelope", "adsr", "modulation",
        # mixing / structure
        "mixdown", "mix bus", "bus", "send", "return", "gain", "gain staging", "headroom",
        "master", "mastering", "loudness", "lufs", "true peak", "dynamics",
        "arrangement", "groove", "swing", "quantize", "quantise", "velocity", "humanize",
        # instruments / amapiano + r&b specifics
        "log drum", "logdrum", "shaker", "shakers", "hi-hat", "hihat", "hi hat", "kick", "snare", "clap",
        "808", "sub", "sub-bass", "subbass", "sub bass", "bassline", "pad", "pads", "chord", "chords",
        "voicing", "voicings", "inversion", "progression", "melody", "topline", "adlib", "ad-lib",
        "harmony", "harmonies", "stack", "stacking", "double", "doubling", "formant", "pitch",
        # tools
        "serato", "serum", "vital", "ableton", "fl studio", "fl-studio", "logic", "pro tools",
        "vst", "plugin", "preset", "sample", "midi", "daw", "otp", "ott", "rx",
    }
)

# ---------------------------------------------------------------------------------------------
# Actionable / imperative craft verbs — turns a sentence into an instruction.
# ---------------------------------------------------------------------------------------------
ACTIONABLE_VERBS: frozenset[str] = frozenset(
    {
        "cut", "boost", "add", "remove", "roll", "high-pass", "highpass", "low-pass", "lowpass",
        "filter", "compress", "sidechain", "duck", "pan", "automate", "layer", "stack", "double",
        "tune", "pitch", "quantize", "quantise", "saturate", "distort", "widen", "narrow",
        "increase", "decrease", "raise", "lower", "pull", "push", "set", "turn", "bring",
        "route", "send", "bounce", "render", "freeze", "group", "bus", "gain", "normalize",
        "reverse", "chop", "slice", "stretch", "warp", "sample", "record", "play", "program",
        "mute", "solo", "trim", "fade", "duplicate", "copy", "paste", "drag",
    }
)

# ---------------------------------------------------------------------------------------------
# Visual-only deixis — the "I'm pointing at the screen, not telling you" tell.
# ---------------------------------------------------------------------------------------------
VISUAL_ONLY_PHRASES: tuple[str, ...] = (
    "as you can see",
    "like this",
    "like that",
    "just like that",
    "right here",
    "over here",
    "do that",
    "do this",
    "you just",
    "and boom",
    "there you go",
    "there we go",
    "you see",
    "watch this",
    "look at that",
    "look at this",
    "something like this",
    "this guy",       # "drag this guy up here"
    "right there",
    "boom",
)

# WR-01: the deixis tally must be word-boundaried and non-overlapping, or the gate mis-calibrates:
#   * substring matching penalizes legitimate craft — bare "boom" matched inside "boomy"/"boombap"
#     (common in bass/drum tutorials, the target genre), wrongly attenuating real lessons;
#   * overlapping phrases double-counted — "just like that" hit BOTH "like that" AND "just like that",
#     and "and boom" hit BOTH "boom" AND "and boom", inflating the penalty past the per-phrase model.
# One alternation regex with ``\b`` boundaries, phrases ordered LONGEST-FIRST, scanned non-overlappingly
# (``finditer`` consumes each matched span) fixes both: "boom" never matches "boomy", and at any position
# the longest applicable phrase wins exactly once.
_VISUAL_DEIXIS_RE: re.Pattern[str] = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in sorted(VISUAL_ONLY_PHRASES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def count_visual_deixis(text: str) -> int:
    """Count screen-pointing deixis phrases, word-boundaried and non-overlapping (WR-01). Pure.

    Each matched span is consumed once, and phrases are tried longest-first, so overlapping entries
    ("like that" vs "just like that") count as a single phrase and bare tokens ("boom") never match
    inside a longer word ("boomy"). Returns the number of deixis phrase occurrences.
    """
    return len(_VISUAL_DEIXIS_RE.findall(text))

# ---------------------------------------------------------------------------------------------
# Numeric parameters with units — real values to EXTRACT (never invent). Rescues a "like this".
# ---------------------------------------------------------------------------------------------
# Matches e.g. "300 hz", "300hz", "-6 db", "120 bpm", "30ms", "50 %". Unit-anchored so bare numbers
# ("the 2nd one") do not count as a parameter.
PARAM_PATTERN: re.Pattern[str] = re.compile(
    r"""
    (?<![a-z0-9])              # not mid-word
    -?\d+(?:\.\d+)?            # an integer or decimal, optionally negative
    \s*
    (?:hz|khz|db|dbfs|lufs|bpm|ms|%|cents?|semitones?|st)   # an audio-relevant unit
    (?![a-z])                  # unit not part of a longer word
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Sentence splitter (captions rarely have clean punctuation — split on .?! AND on segment-ish gaps).
_SENTENCE_SPLIT: re.Pattern[str] = re.compile(r"[.!?]+|\n+")
# Word tokenizer (keep hyphenated terms like "high-pass" / "sub-bass" intact).
_WORD: re.Pattern[str] = re.compile(r"[a-z0-9][a-z0-9'\-]*")


def words(text: str) -> list[str]:
    """Lowercased word tokens (hyphenated craft terms preserved). Pure."""
    return _WORD.findall(text.lower())


def sentences(text: str) -> list[str]:
    """Rough sentence/clause split tolerant of caption text with no punctuation. Pure."""
    parts = (_SENTENCE_SPLIT.split(text) if text else [])
    return [p.strip() for p in parts if p and p.strip()]


def count_param_mentions(text: str) -> int:
    """How many unit-anchored numeric parameters appear (e.g. '300 Hz', '-6 dB'). Pure."""
    return len(PARAM_PATTERN.findall(text))
