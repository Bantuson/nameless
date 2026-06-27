"""InMemoryFragmentRepo — the RAM-safe fake for :class:`~nameless_workers.ports.FragmentRepo`.

Backed by plain dicts; no database. It is a *faithful* double for the Postgres adapter because:
  * :meth:`advance` applies the EXACT same guard as production — it calls the shared pure
    :func:`nameless_workers.domain.state.transition` (the Rust mirror), so an illegal edge raises here
    just as it would in Postgres; and
  * :meth:`search` ranks with cosine over unit-normalized vectors, which is mathematically identical to
    pgvector's ``1 - (a <=> b)`` cosine ordering — so a retrieval test written against this fake proves
    the ranking the real index will produce.

This is the object that makes the orchestration, persistence-contract, and retrieval-ranking tests run
with no Postgres at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from ..domain.models import AudioFeatures, Embedding, FragmentRecord, SearchHit
from ..domain.provenance import Provenance
from ..domain.state import FragmentState, transition
from ..ports import SearchField, SearchQuery
from ..pure.vectors import rank_by_cosine


@dataclass
class _Stored:
    """One fragment's mutable analysis state inside the fake."""

    record: FragmentRecord
    features: Optional[AudioFeatures] = None
    audio_embedding: Optional[list[float]] = None
    note_embedding: Optional[list[float]] = None


@dataclass
class InMemoryFragmentRepo:
    """An in-memory fragment repo + feature store + vector index."""

    _store: dict[UUID, _Stored] = field(default_factory=dict)

    # ---- test seam: register fragments the worker will read ----
    def insert(self, record: FragmentRecord) -> None:
        """Add (or replace) a fragment record (test helper; the control plane is the real writer)."""
        self._store[record.id] = _Stored(record=record)

    # ---- FragmentRepo: read ----
    def get_fragment(self, fragment_id: UUID) -> Optional[FragmentRecord]:
        stored = self._store.get(fragment_id)
        return stored.record if stored else None

    # ---- FragmentRepo: guarded state advance (mirror of the Rust state machine) ----
    def advance(self, fragment_id: UUID, t) -> str:  # t: Transition
        stored = self._store.get(fragment_id)
        if stored is None:
            raise KeyError(f"fragment {fragment_id} not found")
        provenance = Provenance.from_db_str(stored.record.provenance)
        current = FragmentState.from_db_str(stored.record.state)
        # transition() raises IllegalTransition on an illegal edge — no silent no-op.
        nxt = transition(provenance, current, t)
        stored.record = stored.record.model_copy(update={"state": nxt.value})
        return nxt.value

    # ---- FragmentRepo / FeatureStore: persist ----
    def persist_features(self, fragment_id: UUID, features: AudioFeatures) -> None:
        stored = self._require(fragment_id)
        stored.features = features

    def persist_embeddings(self, fragment_id: UUID, audio: Embedding, note: Embedding) -> None:
        stored = self._require(fragment_id)
        stored.audio_embedding = list(audio.vector)
        stored.note_embedding = list(note.vector)

    def get_embedding(self, fragment_id: UUID, field: SearchField) -> Optional[list[float]]:
        stored = self._store.get(fragment_id)
        if stored is None:
            return None
        return stored.audio_embedding if field is SearchField.AUDIO else stored.note_embedding

    # ---- FragmentRepo: retrieval (CAP-04) ----
    def search(self, query: SearchQuery) -> list[SearchHit]:
        candidates: list[tuple[UUID, list[float]]] = []
        for fid, stored in self._store.items():
            if query.exclude_fragment_id is not None and fid == query.exclude_fragment_id:
                continue
            if query.project_id is not None and stored.record.project_id != query.project_id:
                continue
            vec = (
                stored.audio_embedding
                if query.field is SearchField.AUDIO
                else stored.note_embedding
            )
            if vec is None:  # not-yet-analyzed fragments are absent from the index (as in pgvector)
                continue
            candidates.append((fid, vec))

        ranked = rank_by_cosine(query.vector, candidates, query.limit)
        hits: list[SearchHit] = []
        for fid, score in ranked:
            stored = self._store[fid]  # type: ignore[index]
            key = stored.features.key.name if stored.features else None
            tempo = stored.features.tempo_bpm if stored.features else None
            hits.append(
                SearchHit(fragment_id=fid, key=key, tempo_bpm=tempo, score=score)  # type: ignore[arg-type]
            )
        return hits

    # ---- helpers ----
    def _require(self, fragment_id: UUID) -> _Stored:
        stored = self._store.get(fragment_id)
        if stored is None:
            raise KeyError(f"fragment {fragment_id} not found")
        return stored
