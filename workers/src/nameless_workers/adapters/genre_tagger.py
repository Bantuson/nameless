"""Genre taggers — CLAP zero-shot (real, pluggable) + a deterministic fake.

Zero-shot genre tagging: embed a fixed vocabulary of genre PROMPTS with the joint space's TEXT tower,
then rank a track's audio embedding against them by cosine similarity — the nearest prompt is the
tag. No supervised classifier, no labels needed at train time; the join is the CLAP space itself.

The real tagger reuses the Phase-2 :class:`~nameless_workers.ports.Embedder` (CLAP), so its *logic*
is fully testable with the deterministic ``FakeEmbedder`` — the ranking math is the pure
``cosine_similarity`` from ``pure/vectors.py``, identical to what the real CLAP space would rank.

CAVEAT (PITFALLS.md Pitfall 5): CLAP zero-shot is verified WEAK for fine-grained genre. This is used
for COARSE tags only; ``min_margin`` lets an implementation return ``top=None`` when no candidate is
confidently ahead, rather than asserting a shaky fine distinction.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Sequence

from ..domain.models import Embedding
from ..ports import Embedder
from ..pure.vectors import cosine_similarity, l2_normalize
from ..reference_ports import GenreTag

# The north-star vocabulary (PROJECT.md): R&B × amapiano × deep house × alt-piano, plus neighbours.
DEFAULT_GENRES: tuple[str, ...] = (
    "amapiano",
    "deep house",
    "r&b",
    "alternative piano",
    "afrobeats",
    "hip hop",
    "soul",
    "jazz",
    "pop",
    "ambient",
)
DEFAULT_PROMPT_TEMPLATE = "a {genre} song"


class ClapZeroShotGenreTagger:
    """Rank an audio embedding against text-embedded genre prompts (reuses the CLAP Embedder)."""

    def __init__(
        self,
        embedder: Embedder,
        genres: Sequence[str] = DEFAULT_GENRES,
        *,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        min_margin: float = 0.0,
    ) -> None:
        self._embedder = embedder
        self._genres = list(genres)
        self._template = prompt_template
        self._min_margin = min_margin
        self._prompt_vecs: Optional[list[tuple[str, list[float]]]] = None  # cached

    def prompt(self, genre: str) -> str:
        """The text prompt embedded for a genre (exposed so callers/tests can reproduce it)."""
        return self._template.format(genre=genre)

    def _prompt_embeddings(self) -> list[tuple[str, list[float]]]:
        if self._prompt_vecs is None:
            self._prompt_vecs = [
                (g, self._embedder.embed_text(self.prompt(g)).vector) for g in self._genres
            ]
        return self._prompt_vecs

    def tag(self, audio_embedding: Embedding) -> GenreTag:
        scored = [
            (genre, cosine_similarity(audio_embedding.vector, vec))
            for genre, vec in self._prompt_embeddings()
        ]
        scored.sort(key=lambda gs: gs[1], reverse=True)
        if not scored:
            return GenreTag(top=None, scores=[])
        # Pick the leader only if it is ahead of the runner-up by the margin (coarse-tag honesty).
        best_genre, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else float("-inf")
        top = best_genre if (best_score - second_score) >= self._min_margin else None
        return GenreTag(top=top, scores=scored)


class FakeGenreTagger:
    """Deterministic genre tagger — picks a label by hashing the embedding. No CLAP."""

    def __init__(self, genres: Sequence[str] = DEFAULT_GENRES) -> None:
        self._genres = list(genres)

    def tag(self, audio_embedding: Embedding) -> GenreTag:
        if not self._genres:
            return GenreTag(top=None, scores=[])
        # Seed a stable choice from the embedding's bytes so the same vector → the same tag.
        seed_src = ",".join(f"{v:.6f}" for v in audio_embedding.vector).encode("utf-8")
        idx = int.from_bytes(hashlib.sha256(seed_src).digest()[:4], "big") % len(self._genres)
        # Build descending pseudo-scores so the chosen genre leads (deterministic, ranking-shaped).
        ordered = [self._genres[idx]] + [g for i, g in enumerate(self._genres) if i != idx]
        scores = [(g, round(1.0 - 0.05 * rank, 4)) for rank, g in enumerate(ordered)]
        # Keep the vectors unit-norm-consistent with the real path (no-op on already-unit input).
        _ = l2_normalize(audio_embedding.vector)
        return GenreTag(top=ordered[0], scores=scores)
