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


def test_truncated_caption_still_verifies_via_contiguous_run():
    # A near-contiguous suffix-truncated quote (missing the trailing word) keeps a high contiguous run
    # and clears min_coverage — the legitimate token-fallback case the gate must still admit.
    snap = RawTranscript(
        video_id="vid", caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=5.0, duration_s=5.0,
                                    text="High pass the sub bass around 30")],
    )
    claim = make_claim(quote="high pass the sub bass around 30 hz", video="vid", ts_ms=5000)
    chk = verify_citation(claim, snap, min_coverage=0.8)
    assert chk.ok is True
    assert chk.reason == "verified"
    assert chk.coverage < 1.0          # not an exact substring, but a high contiguous run


def test_scattered_token_fake_is_rejected_not_verified():
    # WR-02 (the dangerous under-rejection): every quote token APPEARS in the nearby segment, but
    # scattered / out of order. It is NOT a real quotation and must be rejected, not marked verified.
    snap = RawTranscript(
        video_id="vid", caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=5.0, duration_s=5.0,
                                    text="Cut around 300 Hz on the log drum to remove mud.")],
    )
    # tokens cut / 300 / mud / drum all present in the segment, but never contiguous.
    fake = make_claim(quote="cut 300 mud drum", video="vid", ts_ms=5000)
    chk = verify_citation(fake, snap, min_coverage=0.8)
    assert chk.ok is False
    assert chk.reason == "not_found"
    assert chk.coverage < 0.8


def test_recurring_quote_prefers_in_tolerance_occurrence_not_first():
    # WR-01 (false DRIFT): the SAME phrase appears twice. The claim cites the LATER occurrence; the gate
    # must anchor there and verify, not freeze on the first occurrence and report drift.
    snap = RawTranscript(
        video_id="vid", caption_source=CaptionSource.MANUAL,
        segments=[
            TranscriptSegment(start_s=5.0, duration_s=5.0, text="drop the low end"),    # filler occurrence
            TranscriptSegment(start_s=60.0, duration_s=5.0, text="drop the low end"),   # the cited one
        ],
    )
    claim = make_claim(quote="drop the low end", video="vid", ts_ms=60000)
    chk = verify_citation(claim, snap)
    assert chk.ok is True
    assert chk.reason == "verified"
    assert chk.matched_start_ms == 60000          # not frozen on the 5000 ms first occurrence
