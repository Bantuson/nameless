"""Nameless audio-ML worker plane.

Phase 2 (Fragment Analysis) capability: take a captured fragment to ``analyzed`` by computing audio
features (f0, chroma, onsets/beat-grid/tempo, key, LUFS) and joint CLAP embeddings, persisting them,
and driving the typed ``Captured → Analyzing → Analyzed`` lifecycle — then make fragments retrievable
by note text or audio similarity (pgvector).

Design law (see ``.planning/ENGINEERING-PRINCIPLES.md``): every heavy/external dependency sits behind
a ``typing.Protocol`` port with a REAL adapter and a deterministic FAKE. The orchestration
(:class:`~nameless_workers.consumer.AnalyzeJobConsumer`) is pure over those ports, so the entire
control flow is testable with no torch / librosa / CLAP / Postgres installed.

IMPORTANT: importing this package pulls in only ``pydantic`` + ``numpy``. The real adapters import
their heavy libraries lazily (inside methods) so the fakes and tests run on the light base install.
"""

__version__ = "0.2.0"

# Joint CLAP embedding width (LAION-CLAP `larger_clap_music` / HTSAT-base music CLAP). Mirrored by the
# `vector(512)` columns in migrations/0002_fragment_features.sql. Single source of truth.
CLAP_DIM = 512
