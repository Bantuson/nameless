"""Pure functions — deterministic, no I/O, output depends only on input.

The interesting, testable logic of Phase 2 lives here so it can be unit-tested with no audio, no
models, and no database:
  * :mod:`nameless_workers.pure.key`     — Krumhansl-Schmuckler key estimation from a chroma vector.
  * :mod:`nameless_workers.pure.vectors` — L2 normalization, cosine similarity, top-k ranking.
"""
