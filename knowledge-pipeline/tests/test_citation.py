"""verify_citation — the pure precursor to Phase 5's hard citation gate (KNOW-05 #2).

Covers the four outcomes that matter: verified, drift (the dangerous case), not_found (hallucination),
and empty.
"""

from __future__ import annotations

from knowledge_pipeline.domain.models import CaptionSource, RawTranscript, TranscriptSegment
from knowledge_pipeline.pure.citation import verify_citation

from .conftest import make_claim


def _transcript() -> RawTranscript:
    return RawTranscript(
        video_id="vid",
        caption_source=CaptionSource.MANUAL,
        segments=[
            TranscriptSegment(start_s=5.0, duration_s=5.0, text="Cut around 300 Hz on the log drum to remove mud."),
            TranscriptSegment(start_s=30.0, duration_s=5.0, text="High-pass the sub bass around 30 hz to keep it tight."),
        ],
    )


def test_positive_verification():
    snap = _transcript()
    claim = make_claim(
        claim_text="Cut 300 Hz on the log drum.",
        quote="Cut around 300 Hz on the log drum to remove mud.",
        video="vid", ts_ms=5000,
    )
    chk = verify_citation(claim, snap)
    assert chk.ok is True
    assert chk.reason == "verified"
    assert chk.coverage == 1.0
    assert chk.matched_start_ms == 5000


def test_drift_is_detected_not_silently_accepted():
    # The quote IS in the transcript, but at 30s — the claim cites 5s. That is citation drift, the most
    # corrosive GIGO failure; it must be flagged, not accepted.
    snap = _transcript()
    claim = make_claim(
        quote="High-pass the sub bass around 30 hz to keep it tight.",
        video="vid", ts_ms=5000,
    )
    chk = verify_citation(claim, snap)
    assert chk.ok is False
    assert chk.reason == "drift"
    assert chk.matched_start_ms == 30000


def test_hallucinated_quote_not_found():
    snap = _transcript()
    claim = make_claim(quote="add a purple gradient and make it slap with vibes", video="vid", ts_ms=5000)
    chk = verify_citation(claim, snap)
    assert chk.ok is False
    assert chk.reason == "not_found"


def test_empty_quote():
    snap = _transcript()
    claim = make_claim(quote="   ", video="vid", ts_ms=5000)
    chk = verify_citation(claim, snap)
    assert chk.ok is False
    assert chk.reason == "empty"


def test_partial_coverage_within_tolerance_passes():
    # A slightly truncated caption still verifies via token coverage (>= min_coverage), same timestamp.
    snap = _transcript()
    claim = make_claim(quote="cut around 300 hz on the log drum", video="vid", ts_ms=5000)
    chk = verify_citation(claim, snap, min_coverage=0.8)
    assert chk.ok is True
