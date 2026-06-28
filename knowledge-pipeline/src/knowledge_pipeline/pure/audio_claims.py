"""``audio_derived_claims`` + ``features_to_record`` — PURE audio-grounding core (KNOW-10, PITFALLS #5).

The second grounding leg: turn the MEASURED signatures of real tracks into cited claims. Two pure pieces,
no torch / librosa / CLAP anywhere (the real measuring is the env-gated
:class:`~knowledge_pipeline.ports.TrackAnalyzer`; this module only shapes its numbers into evidence):

  * :func:`features_to_record` — the thin DTO mapping the real ``WorkerTrackAnalyzer`` calls: primitive
    measured values (tempo, swing, key, tonal balance, stereo width, LUFS, coarse CLAP tags) ->
    :class:`AudioAnalysisRecord`. Pure, so it is tested with canned numbers (no ML on the test path).
  * :func:`audio_derived_claims` — a record -> the atomic, self-citing :class:`AudioDerivedClaim`s, each a
    *measured* statement cited back to the record. The discipline (PITFALLS #5) is encoded in WHAT it will
    emit: tempo, swing, key tendency, tonal balance, stereo width, and COARSE CLAP vibe tags — surface the
    DSP/CLAP pipeline genuinely measures — and **nothing about melody, chords, structure, or "intent"**.
    Where audio measures a number, the statement carries that number verbatim, so the Phase-5 gate can
    prove it against the record; where audio only knows a coarse label (CLAP), the statement says so.

Why integer percents for swing / tonal balance / width: the gate compares numeric MAGNITUDES present in a
claim's prose against its cited quote. Rendering ratios as clean integer percents (0.16 -> "16 percent")
keeps the asserted numbers unambiguous and the unit ("percent") in the prose where the gate expects it —
the same convention the tutorial claims use for "300 Hz" / "-6 dB".
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional, Sequence

from ..domain.grounding import (
    AudioAnalysisRecord,
    AudioDerivedClaim,
    ClapTag,
    TrackRef,
)

# Each audio MEASURE maps to a (stage, technique) topic so the same measure across MANY tracks clusters
# into one corroborated topic (PITFALLS #5: "a signature from many tracks where features converge is
# signal"; a single track is noise). The stage is where that surface informs production.
_MEASURE_TOPICS: dict[str, tuple[str, str]] = {
    "tempo": ("drums", "groove-tempo"),
    "swing": ("drums", "groove-swing"),
    "key-tendency": ("chords", "key-tendency"),
    "tonal-balance": ("mixing", "tonal-balance"),
    "stereo-width": ("mixing", "stereo-width"),
    "clap-vibe": ("atmosphere", "clap-vibe"),
}

# A modest per-claim confidence: one track's measurement is a noisy point estimate. CLAP is the weakest
# (coarse for fine-grained genre, PITFALLS #5), so its tag claim is the least confident.
_MEASURE_CONFIDENCE: dict[str, float] = {
    "tempo": 0.7,
    "swing": 0.55,
    "key-tendency": 0.5,
    "tonal-balance": 0.55,
    "stereo-width": 0.5,
    "clap-vibe": 0.4,
}


def _fmt_num(x: float) -> str:
    """Render a measured value with a clean magnitude: 110.0 -> '110', 110.5 -> '110.5'. Pure."""
    r = round(float(x), 1)
    return str(int(r)) if r == int(r) else str(r)


def _pct(x: float) -> int:
    """A 0..1 ratio as an integer percent (0.16 -> 16). Pure."""
    return int(round(float(x) * 100))


def features_to_record(
    track: TrackRef,
    *,
    tempo_bpm: float,
    swing_ratio: float,
    key_name: str,
    key_confidence: float,
    tonal_balance: dict[str, float],
    stereo_width: float,
    loudness_lufs: float,
    clap_tags: Sequence[ClapTag],
    analyzer_version: str,
    embed_model: str,
    separator_model: Optional[str] = None,
    region_ms: tuple[int, int] = (0, 0),
    analyzed_at: Optional[_dt.datetime] = None,
) -> AudioAnalysisRecord:
    """Assemble an :class:`AudioAnalysisRecord` from primitive measured values + the track identity. Pure.

    This is the seam the real :class:`~knowledge_pipeline.adapters.track_analyzer_worker.WorkerTrackAnalyzer`
    calls after it runs the (env-gated) Phase-2 feature extractor + CLAP embedder — so the mapping logic is
    tested here with canned numbers and the real adapter only has to compute the primitives.
    """
    return AudioAnalysisRecord(
        track_id=track.track_id,
        artist=track.artist,
        title=track.title,
        genre=track.genre,
        source_track_id=track.source_track_id,
        region_ms=region_ms,
        tempo_bpm=round(float(tempo_bpm), 3),
        swing_ratio=round(float(swing_ratio), 4),
        key_name=key_name,
        key_confidence=round(float(key_confidence), 4),
        tonal_balance={k: round(float(v), 4) for k, v in tonal_balance.items()},
        stereo_width=round(float(stereo_width), 4),
        loudness_lufs=round(float(loudness_lufs), 2),
        clap_tags=list(clap_tags),
        analyzer_version=analyzer_version,
        embed_model=embed_model,
        separator_model=separator_model,
        analyzed_at=analyzed_at,
    )


def _claim(
    record: AudioAnalysisRecord, measure: str, statement: str, genre: list[str]
) -> AudioDerivedClaim:
    stage, technique = _MEASURE_TOPICS[measure]
    return AudioDerivedClaim(
        record_id=record.citation_id,
        track_id=record.track_id,
        artist=record.artist,
        measure=measure,
        stage=stage,
        technique=technique,
        genre=genre,
        statement=statement,
        region_ms=record.region_ms,
        confidence=_MEASURE_CONFIDENCE[measure],
    )


def audio_derived_claims(record: AudioAnalysisRecord) -> list[AudioDerivedClaim]:
    """Derive the atomic, self-citing MEASURED claims from one analysis record. Pure (PITFALLS #5).

    Emits ONLY what audio measures well — tempo, swing, key tendency, tonal balance, stereo width, coarse
    CLAP vibe — each as a verbatim statement carrying its own numbers, cited to ``record``. Emits nothing
    about melody / chords / structure / intent: the measured-not-interpreted boundary, enforced here by
    construction. A measure whose value is absent/empty is simply skipped (never asserted as 0).
    """
    genre = [record.genre]
    artist = record.artist
    out: list[AudioDerivedClaim] = []

    # tempo — the groove band (what the records actually sit at)
    if record.tempo_bpm > 0:
        out.append(
            _claim(
                record, "tempo",
                f"Measured groove tempo on {artist}'s track is {_fmt_num(record.tempo_bpm)} bpm.",
                genre,
            )
        )

    # swing — the bounce, as an integer percent
    if record.swing_ratio > 0:
        out.append(
            _claim(
                record, "swing",
                f"Measured groove swing is about {_pct(record.swing_ratio)} percent off the straight grid.",
                genre,
            )
        )

    # key tendency — the tonal CENTRE only (never the melodic line), no numeric pitch classes asserted
    if record.key_name:
        out.append(
            _claim(
                record, "key-tendency",
                f"Measured key centre is {record.key_name} — a {_mode_word(record.key_name)} tonality.",
                genre,
            )
        )

    # tonal balance — band-energy split as integer percents
    tb = record.tonal_balance
    if tb and all(k in tb for k in ("low", "mid", "high")):
        out.append(
            _claim(
                record, "tonal-balance",
                f"Measured tonal balance is low {_pct(tb['low'])} percent, mid {_pct(tb['mid'])} percent, "
                f"high {_pct(tb['high'])} percent of band energy.",
                genre,
            )
        )

    # stereo width — mid/side energy ratio as an integer percent
    if record.stereo_width > 0:
        out.append(
            _claim(
                record, "stereo-width",
                f"Measured stereo width is about {_pct(record.stereo_width)} percent side energy.",
                genre,
            )
        )

    # coarse CLAP vibe — labels ONLY, explicitly flagged coarse (no scores asserted as craft numbers)
    tags = record.top_tags(3)
    if tags:
        out.append(
            _claim(
                record, "clap-vibe",
                f"Coarse CLAP nearest tags (genre-level only, not fine-grained): {', '.join(tags)}.",
                genre,
            )
        )

    return out


def _mode_word(key_name: str) -> str:
    """'minor'/'major'/'modal' from a 'F:min'/'C:maj' label — prose only, asserts no number. Pure."""
    low = key_name.lower()
    if "min" in low:
        return "minor"
    if "maj" in low:
        return "major"
    return "modal"
