"""Shared test fixtures + helpers. Everything here runs against the FAKES (numpy + pydantic only)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from nameless_workers.adapters import (
    FakeEmbedder,
    FakeFeatureExtractor,
    InMemoryAudioLoader,
    InMemoryFragmentRepo,
)
from nameless_workers.consumer import AnalyzeJobConsumer
from nameless_workers.domain.models import FragmentRecord


def make_record(
    *,
    fragment_id: UUID | None = None,
    project_id: UUID | None = None,
    provenance: str = "human_recorded",
    state: str = "captured",
    audio_uri: str = "deadbeef",
    note_text: str = "chorus hook, sits over the second drop",
) -> FragmentRecord:
    """Build a compact FragmentRecord the worker can read."""
    return FragmentRecord(
        id=fragment_id or uuid4(),
        project_id=project_id or uuid4(),
        kind="hook",
        provenance=provenance,
        state=state,
        audio_uri=audio_uri,
        note_text=note_text,
    )


@pytest.fixture
def loader() -> InMemoryAudioLoader:
    return InMemoryAudioLoader()


@pytest.fixture
def extractor() -> FakeFeatureExtractor:
    return FakeFeatureExtractor()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def repo() -> InMemoryFragmentRepo:
    return InMemoryFragmentRepo()


@pytest.fixture
def consumer(loader, extractor, embedder, repo) -> AnalyzeJobConsumer:
    return AnalyzeJobConsumer(loader=loader, extractor=extractor, embedder=embedder, repo=repo)
