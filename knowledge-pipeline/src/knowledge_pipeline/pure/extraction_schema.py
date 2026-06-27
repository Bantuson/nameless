"""Extraction schema + normalization — the structured boundary between the LLM and the typed ``Claim``.

"Reliable LLM output comes from structure, not clever prose." This module is that structure, kept PURE
(no ``anthropic`` import, no I/O) so both the real extractor and the tests share one definition:

  * :data:`EXTRACTION_TOOL_SCHEMA` — the JSON Schema for the ``emit_claims`` tool. Forcing the model
    to fill THIS schema (``tool_choice`` = the tool) is what makes extraction reliable: the model returns
    a typed object, not free-form prose to be regex-scraped.
  * :func:`parse_extractor_output` — validates the tool's raw input dict and NORMALIZES it into bound,
    citation-anchored :class:`Claim` objects. This is where "extract only" is enforced structurally:
    the ``source_video_id`` and ``caption_source`` come from the transcript (never the model), the quote
    is re-anchored to the segment it actually came from, and the cited ``timestamp_ms`` is snapped to
    that segment's start — so a model that mis-states a timestamp cannot poison the citation.
  * :func:`rule_based_extract` — a deterministic, LLM-free extractor over the producer-jargon lexicon,
    used as the fixture/offline fallback. It proves the whole pipeline end-to-end with no API, and it is
    the reference "fake" the contract tests run against.

Normalization here is the *anti-GIGO* seam: the model proposes, this code disposes — re-grounding every
claim against the real transcript before it is allowed to become a typed ``Claim``.
"""

from __future__ import annotations

from typing import Optional, Sequence

from pydantic import BaseModel, Field, ValidationError

from ..domain.claims import Claim
from ..domain.keys import normalize_key, normalize_text
from ..domain.models import CaptionSource, RawTranscript, TranscriptSegment
from .vocab import PARAM_PATTERN, PRODUCTION_VOCAB, sentences

# ============================================================================================
# The tool-use schema — what the model is FORCED to emit (structured output, not prose).
# ============================================================================================

EXTRACTION_TOOL_NAME = "emit_claims"

# One object with a "claims" array. Each claim is atomic + individually cited. additionalProperties is
# false so the model cannot smuggle in synthesized fields (no "recommended_default", no "summary").
EXTRACTION_TOOL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "description": "Every atomic, single-technique claim the transcript actually states. Empty if none.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "description": "ONE atomic technique as a single imperative sentence. No conjunction of two techniques.",
                    },
                    "technique": {
                        "type": "string",
                        "description": "The specific technique/question key, e.g. 'log-drum-sound-source', 'sidechain', 'vocal-stacking'.",
                    },
                    "stage": {
                        "type": "string",
                        "description": "Production stage: one of beats, drums, bassline, chords, melody, vocals, vocal-layering, arrangement, mixing, mastering, atmosphere.",
                    },
                    "genre": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Genres the claim is evidenced for (rnb, amapiano, deep-house, alt-piano). Omit if the source does not tie it to a genre.",
                    },
                    "stance": {
                        "type": ["string", "null"],
                        "description": "The position taken WHEN the technique has competing answers (e.g. 'flex-synth' vs 'layered-samples'). null otherwise.",
                    },
                    "timestamp_ms": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Start time (ms) of the transcript line the quote is copied from.",
                    },
                    "quote": {
                        "type": "string",
                        "description": "VERBATIM text copied from that single transcript line. Never paraphrased, never invented.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "0.9 explicit+parameterized; 0.7 explicit; 0.5 implied; <0.4 vague. Calibrate honestly.",
                    },
                },
                "required": ["claim_text", "technique", "stage", "timestamp_ms", "quote", "confidence"],
            },
        }
    },
    "required": ["claims"],
}


# ============================================================================================
# Parsing + normalization — model output -> bound, citation-anchored Claim objects.
# ============================================================================================


class _RawClaimIn(BaseModel):
    """A single claim as the model emits it (lenient parse of the tool input, before re-anchoring)."""

    claim_text: str
    technique: str
    stage: str
    genre: list[str] = Field(default_factory=list)
    stance: Optional[str] = None
    timestamp_ms: int = Field(ge=0)
    quote: str
    confidence: float = 0.5


def _reanchor(quote: str, claimed_ts_ms: int, transcript: RawTranscript) -> Optional[int]:
    """Find the segment the quote actually came from; return its start_ms. None if not present. Pure.

    Anti-drift: prefer the in-tolerance occurrence; otherwise the first segment that contains the quote.
    If the quote is nowhere in the transcript we return None and the caller keeps the model's claimed
    timestamp (the pipeline's ``verify_citation`` will then flag it as not_found — the honest outcome).
    """
    quote_norm = normalize_text(quote)
    if not quote_norm:
        return None
    candidates: list[int] = []
    for seg in transcript.segments:
        if quote_norm in normalize_text(seg.text):
            candidates.append(int(round(seg.start_s * 1000)))
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs(s - claimed_ts_ms))


def parse_extractor_output(
    raw: dict,
    transcript: RawTranscript,
    *,
    genres: Sequence[str] = (),
) -> list[Claim]:
    """Validate + normalize the ``emit_claims`` tool input into bound :class:`Claim` objects. Pure.

    The model owns only the *content* fields; the *identity/citation* fields are taken from the
    transcript so they cannot be hallucinated:
      * ``source_video_id`` <- transcript (never the model),
      * ``caption_source``  <- transcript (the provenance/trust of the underlying text),
      * ``timestamp_ms``    <- re-anchored to the segment the quote is in (model's ts is only a hint),
      * ``genre``           <- the claim's evidenced genres, else the discovery-provenance ``genres``.

    Malformed claim entries are skipped (not fabricated into something valid).
    """
    items = raw.get("claims", []) if isinstance(raw, dict) else []
    out: list[Claim] = []
    for entry in items:
        try:
            rc = _RawClaimIn.model_validate(entry)
        except ValidationError:
            continue
        anchored_ts = _reanchor(rc.quote, rc.timestamp_ms, transcript)
        ts_ms = anchored_ts if anchored_ts is not None else rc.timestamp_ms
        genre = rc.genre or list(genres)
        out.append(
            Claim(
                claim_text=rc.claim_text.strip(),
                technique=rc.technique.strip(),
                stage=rc.stage.strip(),
                genre=genre,
                stance=(rc.stance.strip() if rc.stance and rc.stance.strip() else None),
                confidence=max(0.0, min(1.0, float(rc.confidence))),
                source_video_id=transcript.video_id,
                timestamp_ms=max(0, int(ts_ms)),
                quote=rc.quote.strip(),
                caption_source=transcript.caption_source,
            )
        )
    return out


# ============================================================================================
# Rule-based fallback extractor — deterministic, LLM-free (the fixture/offline path).
# ============================================================================================

# vocab term -> (stage, technique). A small, reviewable map; default falls back to the normalized term.
_TECHNIQUE_HINTS: dict[str, tuple[str, str]] = {
    "log drum": ("drums", "log-drum"),
    "logdrum": ("drums", "log-drum"),
    "sidechain": ("mixing", "sidechain"),
    "side-chain": ("mixing", "sidechain"),
    "high-pass": ("mixing", "high-pass"),
    "highpass": ("mixing", "high-pass"),
    "high pass": ("mixing", "high-pass"),
    "low-pass": ("mixing", "low-pass"),
    "sub": ("bassline", "sub-bass"),
    "sub bass": ("bassline", "sub-bass"),
    "sub-bass": ("bassline", "sub-bass"),
    "bassline": ("bassline", "bassline"),
    "reverb": ("atmosphere", "reverb"),
    "delay": ("atmosphere", "delay"),
    "compress": ("mixing", "compression"),
    "compressor": ("mixing", "compression"),
    "shaker": ("drums", "shaker"),
    "hi-hat": ("drums", "hi-hat"),
    "swing": ("drums", "swing"),
    "quantize": ("drums", "swing"),
    "harmonies": ("vocal-layering", "vocal-stacking"),
    "stack": ("vocal-layering", "vocal-stacking"),
    "stacking": ("vocal-layering", "vocal-stacking"),
    "adlib": ("vocals", "adlibs"),
    "ad-lib": ("vocals", "adlibs"),
    "chord": ("chords", "chord-voicing"),
    "voicing": ("chords", "chord-voicing"),
    "pad": ("atmosphere", "pads"),
    "master": ("mastering", "loudness"),
    "lufs": ("mastering", "loudness"),
}

# stance cues — only fire on genuinely competing approaches (keeps non-contested techniques un-staged).
_STANCE_CUES: tuple[tuple[str, str], ...] = (
    ("flex", "flex-synth"),
    ("sample", "layered-samples"),
    ("layer the", "layered-samples"),
)


def _stance_of(low: str) -> Optional[str]:
    for cue, label in _STANCE_CUES:
        if cue in low:
            return label
    return None


def _classify(sentence: str) -> Optional[tuple[str, str, Optional[str]]]:
    """(stage, technique, stance) for a sentence, or None if it teaches no recognizable technique. Pure.

    Iterates ``_TECHNIQUE_HINTS`` in INSERTION ORDER (a deterministic priority), then falls back to a
    sorted scan of the raw vocab — never iterating an unordered ``frozenset``, so the rule-based extractor
    is reproducible.
    """
    low = sentence.lower()
    for term, (stage, technique) in _TECHNIQUE_HINTS.items():
        if term in low:
            return stage, technique, _stance_of(low)
    for term in sorted(PRODUCTION_VOCAB):
        if term in low:
            return "unknown", normalize_key(term), _stance_of(low)
    return None


def rule_based_extract(transcript: RawTranscript, *, genres: Sequence[str] = ()) -> list[Claim]:
    """Deterministic, LLM-free extraction over the producer-jargon lexicon. Pure.

    For each segment, split into sentences; emit one grounded claim per sentence that names a recognized
    technique. ``claim_text`` is the atomic sentence; ``quote`` is the VERBATIM segment line it came from
    (the citation substrate is a real transcript line, never a re-cut fragment) — confidence rises with a
    stated numeric parameter and the caption source's trust. This is the fixture/offline workhorse and the
    reference fake the contract tests run against.
    """
    out: list[Claim] = []
    cap_weight = {
        CaptionSource.MANUAL: 0.2,
        CaptionSource.ASR: 0.15,
        CaptionSource.AUTO: 0.05,
        CaptionSource.NONE: 0.0,
    }.get(transcript.caption_source, 0.0)

    for seg in transcript.segments:
        ts_ms = int(round(seg.start_s * 1000))
        line = seg.text.strip()
        for sentence in sentences(seg.text):
            classified = _classify(sentence)
            if classified is None:
                continue
            stage, technique, stance = classified
            has_param = bool(PARAM_PATTERN.search(sentence))
            confidence = min(1.0, 0.5 + (0.2 if has_param else 0.0) + cap_weight)
            out.append(
                Claim(
                    claim_text=sentence.strip(),
                    technique=technique,
                    stage=stage,
                    genre=list(genres),
                    stance=stance,
                    confidence=round(confidence, 3),
                    source_video_id=transcript.video_id,
                    timestamp_ms=ts_ms,
                    quote=line,  # verbatim transcript LINE (citation anchor)
                    caption_source=transcript.caption_source,
                )
            )
    return out


def format_transcript_for_extraction(transcript: RawTranscript) -> str:
    """Render the transcript as ``[mm:ss | tms] line`` rows — the user content the real extractor sends.

    Each row carries the exact ``timestamp_ms`` so the model can cite it directly (and so the quote it
    copies is anchored to a real line). Pure / deterministic.
    """
    lines = [f"video_id: {transcript.video_id}  caption_source: {transcript.caption_source.value}", ""]
    for seg in transcript.segments:
        ts_ms = int(round(seg.start_s * 1000))
        mm, ss = divmod(int(seg.start_s), 60)
        lines.append(f"[{mm:02d}:{ss:02d} | {ts_ms}] {seg.text.strip()}")
    return "\n".join(lines)
