"""AnalyzeJobConsumer orchestration tests — the full Captured→Analyzed flow, over fakes only."""

from __future__ import annotations

import pytest

from nameless_workers.adapters import (
    FakeEmbedder,
    FakeFeatureExtractor,
    InMemoryAudioLoader,
    InMemoryFragmentRepo,
)
from nameless_workers.consumer import (
    AnalyzeError,
    AnalyzeJobConsumer,
    FragmentNotFound,
)
from nameless_workers.domain.models import Embedding, FeatureExtractJob
from nameless_workers.domain.state import IllegalTransition
from nameless_workers.ports import SearchField, SearchQuery

from .conftest import make_record

AUDIO = b"a captured hum, 4 bars"


def _seed(loader: InMemoryAudioLoader, repo: InMemoryFragmentRepo, record) -> None:
    loader.put(record.audio_uri, AUDIO)
    repo.insert(record)


def test_captured_fragment_reaches_analyzed(loader, repo, consumer):
    rec = make_record(state="captured", audio_uri="aa01")
    _seed(loader, repo, rec)

    outcome = consumer.handle(FeatureExtractJob(fragment_id=rec.id))

    assert outcome.from_state == "captured"
    assert outcome.to_state == "analyzed"
    assert outcome.skipped is False
    assert outcome.key is not None and outcome.tempo_bpm is not None
    assert outcome.audio_embedding_dim == outcome.note_embedding_dim
    # The persisted fragment is now analyzed (placement becomes legal downstream).
    assert repo.get_fragment(rec.id).state == "analyzed"


def test_features_and_embeddings_are_persisted_and_searchable(loader, repo, consumer):
    rec = make_record(state="captured", audio_uri="bb02")
    _seed(loader, repo, rec)
    outcome = consumer.handle(FeatureExtractJob(fragment_id=rec.id))

    # Both vector columns are populated …
    assert repo.get_embedding(rec.id, SearchField.AUDIO) is not None
    assert repo.get_embedding(rec.id, SearchField.NOTE) is not None

    # … and a search by the fragment's own audio vector returns it, joined to its key/tempo (proving
    # BOTH the features table and the embeddings were persisted and are queryable together).
    own_vec = repo.get_embedding(rec.id, SearchField.AUDIO)
    hits = repo.search(SearchQuery(vector=own_vec, field=SearchField.AUDIO, limit=5))
    assert hits[0].fragment_id == rec.id
    assert hits[0].score == pytest.approx(1.0, abs=1e-9)
    assert hits[0].key == outcome.key
    assert hits[0].tempo_bpm == outcome.tempo_bpm


def test_idempotent_when_already_analyzed(loader, repo, consumer):
    rec = make_record(state="analyzed", audio_uri="cc03")
    _seed(loader, repo, rec)
    outcome = consumer.handle(FeatureExtractJob(fragment_id=rec.id))
    assert outcome.skipped is True
    assert outcome.to_state == "analyzed"


def test_resumes_from_analyzing_after_a_crash(loader, repo, consumer):
    # A redelivery that finds the fragment mid-flight (crash after Captured→Analyzing) completes it
    # WITHOUT attempting the illegal Analyzing→Analyze edge.
    rec = make_record(state="analyzing", audio_uri="dd04")
    _seed(loader, repo, rec)
    outcome = consumer.handle(FeatureExtractJob(fragment_id=rec.id))
    assert outcome.to_state == "analyzed"
    assert repo.get_embedding(rec.id, SearchField.AUDIO) is not None


def test_missing_fragment_raises(consumer):
    from uuid import uuid4

    with pytest.raises(FragmentNotFound):
        consumer.handle(FeatureExtractJob(fragment_id=uuid4()))


def test_ai_provenance_is_structurally_refused(loader, repo, consumer):
    # An ai_generated fragment must never be analyzed; the guarded advance refuses Captured→Analyze.
    rec = make_record(state="captured", provenance="ai_generated", audio_uri="ee05")
    _seed(loader, repo, rec)
    with pytest.raises(IllegalTransition):
        consumer.handle(FeatureExtractJob(fragment_id=rec.id))
    # State unchanged — no partial advance.
    assert repo.get_fragment(rec.id).state == "captured"


def test_loader_failure_is_a_retryable_analyze_error_and_leaves_analyzing(loader, repo, consumer):
    rec = make_record(state="captured", audio_uri="ff06")
    repo.insert(rec)  # NOTE: bytes deliberately NOT registered in the loader
    with pytest.raises(AnalyzeError):
        consumer.handle(FeatureExtractJob(fragment_id=rec.id))
    # The fragment advanced to analyzing before the failure; a retry resumes from there (no revert).
    assert repo.get_fragment(rec.id).state == "analyzing"


class _MismatchEmbedder:
    """An embedder whose towers live in DIFFERENT-dimension spaces (a misconfiguration)."""

    def embed_audio(self, audio: bytes) -> Embedding:
        return Embedding(model_name="bad", dim=512, vector=[0.0] * 512)

    def embed_text(self, text: str) -> Embedding:
        return Embedding(model_name="bad", dim=256, vector=[0.0] * 256)


def test_embedding_dim_mismatch_is_rejected(loader, repo):
    rec = make_record(state="captured", audio_uri="aa07")
    loader.put(rec.audio_uri, AUDIO)
    repo.insert(rec)
    consumer = AnalyzeJobConsumer(
        loader=loader,
        extractor=FakeFeatureExtractor(),
        embedder=_MismatchEmbedder(),
        repo=repo,
    )
    with pytest.raises(AnalyzeError):
        consumer.handle(FeatureExtractJob(fragment_id=rec.id))


def test_distinct_audio_embeds_to_distinct_directions(loader, repo, consumer):
    # Two fragments with different audio must not collide in the index (ranking would be meaningless).
    embedder = FakeEmbedder()
    e1 = embedder.embed_audio(b"one")
    e2 = embedder.embed_audio(b"two")
    assert e1.vector != e2.vector
    assert e1.dim == e2.dim
