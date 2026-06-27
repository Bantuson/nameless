"""extraction_schema — the structured tool schema, output normalization, and rule-based fallback."""

from __future__ import annotations

from knowledge_pipeline.domain.models import CaptionSource, RawTranscript, TranscriptSegment
from knowledge_pipeline.pure.extraction_schema import (
    EXTRACTION_TOOL_NAME,
    EXTRACTION_TOOL_SCHEMA,
    parse_extractor_output,
    rule_based_extract,
)


def _transcript() -> RawTranscript:
    return RawTranscript(
        video_id="vid",
        caption_source=CaptionSource.MANUAL,
        segments=[
            TranscriptSegment(start_s=5.0, duration_s=5.0, text="Sidechain the bass to the kick so the sub breathes."),
            TranscriptSegment(start_s=20.0, duration_s=5.0, text="High-pass the log drum around 40 hz to clean the low end."),
        ],
    )


def test_tool_schema_is_a_closed_claims_array():
    schema = EXTRACTION_TOOL_SCHEMA
    assert EXTRACTION_TOOL_NAME == "emit_claims"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["claims"]["type"] == "array"
    item = schema["properties"]["claims"]["items"]
    assert item["additionalProperties"] is False          # model cannot smuggle synthesized fields
    assert set(item["required"]) == {"claim_text", "technique", "stage", "timestamp_ms", "quote", "confidence"}


def test_parse_binds_identity_from_transcript_not_model():
    raw = {
        "claims": [
            {
                "claim_text": "Sidechain the bass to the kick.",
                "technique": "sidechain", "stage": "mixing",
                "genre": [], "stance": None,
                "timestamp_ms": 999999,  # WRONG ts on purpose -> must be re-anchored to the real segment
                "quote": "Sidechain the bass to the kick so the sub breathes.",
                "confidence": 0.9,
            }
        ]
    }
    claims = parse_extractor_output(raw, _transcript(), genres=["amapiano"])
    assert len(claims) == 1
    c = claims[0]
    assert c.source_video_id == "vid"                     # identity from transcript, never the model
    assert c.caption_source is CaptionSource.MANUAL
    assert c.timestamp_ms == 5000                         # re-anchored to the segment the quote came from
    assert c.genre == ["amapiano"]                        # genre fallback to discovery context


def test_parse_skips_malformed_entries_without_fabricating():
    raw = {"claims": [{"technique": "x"}]}                # missing required fields
    assert parse_extractor_output(raw, _transcript()) == []


def test_rule_based_extract_is_deterministic_and_citation_grounded():
    claims = rule_based_extract(_transcript(), genres=["amapiano"])
    assert claims, "rule-based extractor should derive at least one claim"
    by_tech = {c.technique for c in claims}
    assert "sidechain" in by_tech                         # deterministic technique mapping
    # every rule-based claim is grounded: its quote is verbatim transcript text (never invented).
    seg_texts = {s.text for s in _transcript().segments}
    assert all(c.quote in seg_texts for c in claims)
    # deterministic: two runs produce identical claim ids in identical order
    again = rule_based_extract(_transcript(), genres=["amapiano"])
    assert [c.id for c in claims] == [c.id for c in again]
