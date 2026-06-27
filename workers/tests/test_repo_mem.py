"""InMemoryFragmentRepo tests — retrieval ranking, filters, the persistence contract, advance guard.

These exercise the exact contract the Postgres adapter must satisfy, so they double as the spec for
``PgFragmentRepo`` (the only difference there is a live database, which is env-gated).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from nameless_workers.adapters import FakeFeatureExtractor, InMemoryFragmentRepo
from nameless_workers.domain.models import Embedding
from nameless_workers.domain.state import IllegalTransition, Transition
from nameless_workers.ports import SearchField, SearchQuery

from .conftest import make_record


def _emb(vec: list[float]) -> Embedding:
    return Embedding(model_name="test", dim=len(vec), vector=vec)


def _analyze_into(repo: InMemoryFragmentRepo, record, audio_vec: list[float], note_vec: list[float]):
    """Insert + persist a full analysis (features + both embeddings) for ranking tests."""
    repo.insert(record)
    features = FakeFeatureExtractor().extract(record.audio_uri.encode())
    repo.persist_features(record.id, features)
    repo.persist_embeddings(record.id, _emb(audio_vec), _emb(note_vec))
    return features


def test_search_ranks_by_cosine_and_joins_key_tempo():
    repo = InMemoryFragmentRepo()
    a = make_record(audio_uri="a1")
    b = make_record(audio_uri="b2")
    c = make_record(audio_uri="c3")
    fa = _analyze_into(repo, a, [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    _analyze_into(repo, b, [0.9, 0.1, 0.0], [0.0, 1.0, 0.0])
    _analyze_into(repo, c, [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])

    hits = repo.search(SearchQuery(vector=[1.0, 0.0, 0.0], field=SearchField.AUDIO, limit=10))
    assert [h.fragment_id for h in hits] == [a.id, b.id, c.id]
    assert hits[0].score == pytest.approx(1.0, abs=1e-9)
    # Hits carry the compact summary joined from fragment_features — and nothing else.
    assert hits[0].key == fa.key.name
    assert hits[0].tempo_bpm == fa.tempo_bpm


def test_search_excludes_the_query_fragment():
    repo = InMemoryFragmentRepo()
    a = make_record(audio_uri="a1")
    b = make_record(audio_uri="b2")
    _analyze_into(repo, a, [1.0, 0.0], [1.0, 0.0])
    _analyze_into(repo, b, [0.8, 0.2], [0.0, 1.0])

    hits = repo.search(
        SearchQuery(vector=[1.0, 0.0], field=SearchField.AUDIO, limit=10, exclude_fragment_id=a.id)
    )
    assert [h.fragment_id for h in hits] == [b.id]


def test_search_filters_by_project():
    repo = InMemoryFragmentRepo()
    proj = uuid4()
    a = make_record(audio_uri="a1", project_id=proj)
    b = make_record(audio_uri="b2", project_id=uuid4())
    _analyze_into(repo, a, [1.0, 0.0], [1.0, 0.0])
    _analyze_into(repo, b, [1.0, 0.0], [1.0, 0.0])

    hits = repo.search(SearchQuery(vector=[1.0, 0.0], field=SearchField.AUDIO, limit=10, project_id=proj))
    assert [h.fragment_id for h in hits] == [a.id]


def test_note_field_ranks_against_note_embeddings():
    repo = InMemoryFragmentRepo()
    a = make_record(audio_uri="a1")
    b = make_record(audio_uri="b2")
    _analyze_into(repo, a, [1.0, 0.0], [0.0, 1.0])  # note vec points "up"
    _analyze_into(repo, b, [1.0, 0.0], [1.0, 0.0])  # note vec points "right"

    # A note-field query for "up" should rank A first, even though both share an audio direction.
    hits = repo.search(SearchQuery(vector=[0.0, 1.0], field=SearchField.NOTE, limit=10))
    assert hits[0].fragment_id == a.id


def test_unanalyzed_fragments_are_absent_from_the_index():
    repo = InMemoryFragmentRepo()
    a = make_record(audio_uri="a1")
    repo.insert(a)  # inserted but never analyzed → no embedding
    hits = repo.search(SearchQuery(vector=[1.0, 0.0], field=SearchField.AUDIO, limit=10))
    assert hits == []
    assert repo.get_embedding(a.id, SearchField.AUDIO) is None


def test_advance_applies_the_guard_and_persists_state():
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured")
    repo.insert(rec)

    assert repo.advance(rec.id, Transition.ANALYZE) == "analyzing"
    assert repo.advance(rec.id, Transition.MARK_ANALYZED) == "analyzed"
    assert repo.get_fragment(rec.id).state == "analyzed"
    assert repo.advance(rec.id, Transition.PLACE) == "placed"


def test_advance_refuses_illegal_edges():
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured")
    repo.insert(rec)
    with pytest.raises(IllegalTransition):
        repo.advance(rec.id, Transition.PLACE)  # cannot place an unanalyzed fragment
    # State unchanged after the refusal.
    assert repo.get_fragment(rec.id).state == "captured"


def test_advance_missing_fragment_raises():
    repo = InMemoryFragmentRepo()
    with pytest.raises(KeyError):
        repo.advance(uuid4(), Transition.ANALYZE)
