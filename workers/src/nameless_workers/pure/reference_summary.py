"""Compact reference-summary formatting — pure, and structurally array-free.

The token strategy (PRD §12–13) holds across the language boundary: a reference's CLAP *style*
embedding is a large array addressed by ID, never surfaced. These pure helpers turn a
:class:`ReferenceContextSummary` into a one-line string or a compact dict for the worker CLI/logs —
and, because the summary type carries no vector and no melodic field, neither helper can leak one.
``embedding_dim`` (a single int) is the only trace of the embedding that ever appears.
"""

from __future__ import annotations

from ..domain.reference import ReferenceContextSummary


def summary_to_compact_dict(summary: ReferenceContextSummary) -> dict:
    """A compact JSON-able dict — scalars + the 5 tonal-balance ratios + vibe prose. No vector."""
    return {
        "reference_track_id": str(summary.reference_track_id),
        "genre": summary.genre,
        "tempo_bpm_min": round(summary.tempo_bpm_min, 1),
        "tempo_bpm_max": round(summary.tempo_bpm_max, 1),
        "lufs": round(summary.lufs, 1),
        "tonal_balance": [round(b, 3) for b in summary.tonal_balance.bands()],
        "stereo_width": round(summary.stereo_width, 3),
        "embedding_dim": summary.embedding_dim,  # a count, never the vector
        "vibe": summary.vibe_description,
        "analyzer_version": summary.analyzer_version,
    }


def format_summary_line(summary: ReferenceContextSummary) -> str:
    """A single compact human line: id, genre, tempo range, LUFS, width, vibe. Never the embedding."""
    genre = summary.genre or "-"
    return (
        f"{summary.reference_track_id}  {genre:<10}  "
        f"{summary.tempo_bpm_min:.0f}-{summary.tempo_bpm_max:.0f}bpm  "
        f"{summary.lufs:.1f}LUFS  width={summary.stereo_width:.2f}  "
        f'"{summary.vibe_description}"'
    )
