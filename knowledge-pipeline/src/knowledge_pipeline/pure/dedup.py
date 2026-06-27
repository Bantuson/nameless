"""``dedup`` — pure de-duplication of discovery results (KNOW-01/KNOW-02 idempotency support).

The grid fans many overlapping queries at YouTube ("amapiano drums tutorial" and "Lowbass Djy log drum"
will surface the same video), so discovery returns the same ``video_id`` many times. Distillation cost
and the 100-video count must be measured on UNIQUE videos, so we dedup by ``video_id`` — keeping the
first occurrence but MERGING the discovery provenance (every query/genre/stage/anchor that surfaced it),
because "this video showed up under 5 north-star queries" is itself signal about its relevance.

Separately, :func:`dedup_already_ingested` removes videos the corpus already holds (the store is the
authority), so a re-run only touches NEW sources — the idempotent, incremental ingest PITFALLS #2 wants.

All pure: lists in, lists out, no I/O. The "already ingested" check takes the known-id SET as an
argument (the store fetches it), keeping this function pure and testable.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ..domain.models import VideoRef


def dedup_video_refs(refs: Sequence[VideoRef]) -> tuple[list[VideoRef], int]:
    """De-duplicate candidate videos by ``video_id``, merging discovery provenance. Pure.

    The kept ref's ``query_origin`` becomes a comma-joined union of every query that surfaced the video;
    ``genre`` / ``stage`` / ``artist_anchor`` keep the first non-null seen (stable, deterministic).

    Returns:
        (unique_refs_in_first-seen_order, number_of_duplicate_hits_removed)
    """
    by_id: dict[str, dict] = {}
    order: list[str] = []
    duplicates = 0

    for ref in refs:
        vid = ref.video_id
        origin = ref.query_origin or ""
        if vid not in by_id:
            order.append(vid)
            by_id[vid] = {
                "ref": ref,
                "origins": [origin] if origin else [],
            }
        else:
            duplicates += 1
            agg = by_id[vid]
            if origin and origin not in agg["origins"]:
                agg["origins"].append(origin)
            # backfill provenance fields if the first occurrence lacked them
            first: VideoRef = agg["ref"]
            agg["ref"] = first.model_copy(
                update={
                    "title": first.title or ref.title,
                    "channel": first.channel or ref.channel,
                    "duration_s": first.duration_s if first.duration_s is not None else ref.duration_s,
                    "genre": first.genre or ref.genre,
                    "stage": first.stage or ref.stage,
                    "artist_anchor": first.artist_anchor or ref.artist_anchor,
                }
            )

    unique: list[VideoRef] = []
    for vid in order:
        agg = by_id[vid]
        ref: VideoRef = agg["ref"]
        merged_origin = ", ".join(agg["origins"]) if agg["origins"] else ref.query_origin
        unique.append(ref.model_copy(update={"query_origin": merged_origin}))
    return unique, duplicates


def dedup_already_ingested(
    refs: Sequence[VideoRef],
    known_ids: Iterable[str],
) -> tuple[list[VideoRef], int]:
    """Drop videos already present in the corpus (idempotent, incremental ingest). Pure.

    Args:
        refs: candidate videos (ideally already passed through :func:`dedup_video_refs`).
        known_ids: the set of ``video_id`` the corpus store already holds.

    Returns:
        (refs_not_yet_ingested, number_skipped_as_already_present)
    """
    known = set(known_ids)
    fresh = [r for r in refs if r.video_id not in known]
    return fresh, len(refs) - len(fresh)
