"""FakeEmbedder — deterministic, hash-seeded :class:`~nameless_workers.ports.Embedder`.

Produces unit-normalized vectors of the configured dimension (default :data:`CLAP_DIM` = 512) seeded by
the hash of the input, so:
  * the same audio/text always embeds to the same vector (deterministic retrieval tests), and
  * different inputs embed to different directions (so cosine ranking is meaningful).

To make cross-modal tests realistic, ``embed_text`` and ``embed_audio`` derive from a *shared* seed
namespace, and the fake exposes :meth:`embed_seeded` so a test can plant a known direction for a known
string and assert that a query for that string ranks the matching fragment first. No torch, no CLAP.
"""

from __future__ import annotations

import hashlib

import numpy as np

from .. import CLAP_DIM
from ..domain.models import Embedding
from ..pure.vectors import l2_normalize

FAKE_EMBED_MODEL = "fake-clap-0"


def _unit_vector_from(seed_material: bytes, dim: int) -> list[float]:
    """A deterministic unit vector in ``dim`` dimensions, seeded by ``seed_material``."""
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    vec = rng.normal(0.0, 1.0, size=dim)
    return l2_normalize(vec).tolist()


class FakeEmbedder:
    """A deterministic stand-in for the real CLAP embedder. Audio and text share one joint space."""

    def __init__(self, dim: int = CLAP_DIM) -> None:
        self._dim = dim

    def embed_audio(self, audio: bytes) -> Embedding:
        vec = _unit_vector_from(b"audio:" + hashlib.sha256(audio).digest(), self._dim)
        return Embedding(model_name=FAKE_EMBED_MODEL, dim=self._dim, vector=vec)

    def embed_text(self, text: str) -> Embedding:
        vec = _unit_vector_from(b"text:" + text.encode("utf-8"), self._dim)
        return Embedding(model_name=FAKE_EMBED_MODEL, dim=self._dim, vector=vec)

    def embed_seeded(self, seed_material: bytes) -> Embedding:
        """Embed an arbitrary seed directly (test helper to plant matching audio/text directions)."""
        vec = _unit_vector_from(seed_material, self._dim)
        return Embedding(model_name=FAKE_EMBED_MODEL, dim=self._dim, vector=vec)
