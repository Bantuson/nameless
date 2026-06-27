"""``snapshot_record`` — pure construction of the immutable evidence fingerprint captured at ingest.

WHY SNAPSHOT-ON-INGEST (PITFALLS #2). Every distilled claim will cite ``video_id @ timestamp``. But
YouTube videos and whole channels get taken down, and auto-captions get silently re-generated. If the
only record of a claim's source is a live URL, the evidence trail rots and the project's core promise —
"every claim traceable to its source" — quietly breaks. So at ingest we compute a content hash + record
the retrieval date: the citation then references OUR immutable snapshot, with the YouTube URL as a
secondary, possibly-dead pointer. The hash also detects drift (someone re-captioned the video) and powers
idempotent re-runs (same hash ⇒ already snapshotted ⇒ skip).

Two purity disciplines, both load-bearing:
  * ``retrieval_date`` is INJECTED (``now``), never read from the wall clock inside the function — so a
    snapshot is reproducible in a test and the date means "when WE retrieved it", set by the caller.
  * the hash is over a CANONICAL serialization (video_id + source + language + each segment's start+text),
    so the same transcript always hashes the same regardless of object identity or field order.

The full timestamped segments are written to the snapshot FILE by the store; this record is the compact
metadata the registry holds (see ``domain/models.py`` SnapshotRecord).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json

from ..domain.models import RawTranscript, SnapshotRecord


def canonical_payload(transcript: RawTranscript) -> dict:
    """The canonical, hash-stable dict for a transcript. Pure.

    This is exactly what the snapshot FILE should serialize, and what :func:`content_hash` digests —
    one definition so the on-disk artifact and the fingerprint can never disagree.
    """
    return {
        "video_id": transcript.video_id,
        "caption_source": transcript.caption_source.value,
        "language": transcript.language,
        "fetched_via": transcript.fetched_via,
        "segments": [
            {
                "start_s": round(float(seg.start_s), 3),
                "duration_s": (None if seg.duration_s is None else round(float(seg.duration_s), 3)),
                "text": seg.text,
            }
            for seg in transcript.segments
        ],
    }


def content_hash(transcript: RawTranscript) -> str:
    """SHA-256 hex of the canonical payload. Deterministic; identical transcripts ⇒ identical hash.

    Note: ``fetched_via`` is intentionally EXCLUDED from the hash domain so the same captions fetched by
    two different code paths (youtube-transcript-api vs yt-dlp subs) snapshot to the same content hash —
    the evidence is the text+timestamps, not the tool that pulled it.
    """
    payload = canonical_payload(transcript)
    payload_for_hash = {k: v for k, v in payload.items() if k != "fetched_via"}
    blob = json.dumps(payload_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def snapshot_record(transcript: RawTranscript, now: _dt.datetime) -> SnapshotRecord:
    """Build the immutable :class:`SnapshotRecord` for a transcript at retrieval time ``now``. Pure.

    Args:
        transcript: the fetched transcript (captions or ASR).
        now: the retrieval timestamp — INJECTED by the caller (a clock port), never the wall clock here.

    Returns:
        A :class:`SnapshotRecord` carrying the content hash, the retrieval date, the caption source, and
        the span bounds (first/last segment start, in seconds) for quick citation-range checks.
    """
    digest = content_hash(transcript)
    text = transcript.full_text()
    segments = transcript.segments

    first_s = float(segments[0].start_s) if segments else None
    last_s = float(segments[-1].start_s) if segments else None

    return SnapshotRecord(
        video_id=transcript.video_id,
        content_sha256=digest,
        retrieval_date=now,
        caption_source=transcript.caption_source,
        language=transcript.language,
        segment_count=len(segments),
        char_count=len(text),
        first_segment_s=first_s,
        last_segment_s=last_s,
    )
