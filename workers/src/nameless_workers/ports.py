"""Ports — the ``typing.Protocol`` seam between the worker's orchestration and the outside world.

Every heavy/external dependency sits behind one of these structural interfaces, each with a REAL
adapter (``adapters/*_*.py``) and a deterministic FAKE. The orchestration
(:class:`~nameless_workers.consumer.AnalyzeJobConsumer`) depends only on these protocols, never on a
concrete adapter — so the whole control flow runs in tests with no torch / librosa / CLAP / Postgres.

Ports (mirrors the Phase-2 CONTEXT decisions):
  * :class:`AudioLoader`     — raw bytes by content-hash id (object store).
  * :class:`FeatureExtractor`— bytes → :class:`AudioFeatures` (librosa/torchcrepe/pyloudnorm).
  * :class:`Embedder`        — audio→vector and text→vector in ONE joint space (LAION-CLAP).
  * :class:`FragmentRepo`    — read a fragment, advance its state, persist features+embeddings, search.
                               (The persistence half is the "FeatureStore" role — same object.)
  * :class:`JobSource`       — claim/ack/retry feature-extract jobs (the queue-consumption seam).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel

from .domain.models import (
    AudioFeatures,
    Embedding,
    FragmentRecord,
    JobEnvelope,
    SearchHit,
)
from .domain.state import Transition


@runtime_checkable
class AudioLoader(Protocol):
    """Load immutable raw audio bytes by their content-hash id (the ``audio_uri``).

    The id is the SHA-256 hex the control plane stored the bytes under (Phase 1
    ``FilesystemObjectStore`` / ``S3ObjectStore``). Implementors must never mutate; they only read.
    """

    def load(self, audio_uri: str) -> bytes: ...


@runtime_checkable
class FeatureExtractor(Protocol):
    """Turn raw audio bytes into typed :class:`AudioFeatures` (CAP-03). Pure w.r.t. external state."""

    def extract(self, audio: bytes) -> AudioFeatures: ...


@runtime_checkable
class Embedder(Protocol):
    """Embed audio and text into ONE joint space (CAP-04).

    The audio tower and the text tower of the SAME CLAP model produce vectors of equal dimension that
    are directly comparable — that is what lets retrieval-by-note and retrieval-by-audio-similarity use
    one index. Both methods must return unit-normalized vectors of identical ``dim``.
    """

    def embed_audio(self, audio: bytes) -> Embedding: ...

    def embed_text(self, text: str) -> Embedding: ...


class SearchField(str, Enum):
    """Which embedding column a search ranks against (both live in the same joint CLAP space)."""

    AUDIO = "audio"  # rank against fragments.audio_embedding (cross-modal for a text query)
    NOTE = "note"  # rank against fragments.note_embedding


class SearchQuery(BaseModel):
    """A retrieval request: a query vector + which field to rank against + limits/filters."""

    vector: list[float]
    field: SearchField = SearchField.AUDIO
    limit: int = 10
    project_id: Optional[UUID] = None
    exclude_fragment_id: Optional[UUID] = None  # used by --similar-to to drop the query itself


@runtime_checkable
class FragmentRepo(Protocol):
    """Read fragments, advance lifecycle state, persist features+embeddings, and search.

    The persistence methods (:meth:`persist_features`, :meth:`persist_embeddings`) are the
    "FeatureStore" role; :meth:`search` is the retrieval role. They live on one object because the
    Postgres implementation backs all three with the same connection/transaction.

    CONTRACT on :meth:`advance`: it MUST apply the same *mutation*-layer rule as Rust's
    ``Fragment::apply`` (via :func:`nameless_workers.domain.state.apply_guarded`, NOT bare
    :func:`~nameless_workers.domain.state.transition`) — read the fragment's
    ``(provenance, current_state)``, compute the next state, persist it, and raise
    :class:`~nameless_workers.domain.state.IllegalTransition` on an illegal edge. Crucially this
    refuses ``(Sampled, PLACE)`` outright (SAMP-03): a ``sampled`` fragment can only reach ``placed``
    through an attribution-checked path, never bare ``advance``. The worker is thus structurally unable
    to drive a fragment — including a sample — down an ungated path. (Rust remains canonical; this is
    the documented mirror — see ``domain/state.py``.)
    """

    def get_fragment(self, fragment_id: UUID) -> Optional[FragmentRecord]: ...

    def advance(self, fragment_id: UUID, t: Transition) -> str:
        """Apply a guarded transition; return the new state's canonical label."""
        ...

    def persist_features(self, fragment_id: UUID, features: AudioFeatures) -> None: ...

    def persist_embeddings(
        self,
        fragment_id: UUID,
        audio: Embedding,
        note: Embedding,
    ) -> None: ...

    def get_embedding(
        self,
        fragment_id: UUID,
        field: "SearchField",
    ) -> Optional[list[float]]:
        """Fetch one fragment's stored vector for a given field — used to seed ``--similar-to``.

        The vector is used internally as a search query only; it is NEVER returned to the agent/CLI
        surface (the compact-output contract holds). Returns ``None`` if the fragment is unanalyzed.
        """
        ...

    def search(self, query: SearchQuery) -> list[SearchHit]: ...


class JobLease(BaseModel):
    """A claimed job: the envelope to process + an opaque handle to ack/retry it."""

    handle: str  # opaque (queue row id / message id); the source interprets it
    envelope: JobEnvelope


@runtime_checkable
class JobSource(Protocol):
    """Claim feature-extract jobs and ack/retry them — the queue-consumption seam.

    Mirrors the consume/ack/retry half of the Rust ``JobQueue`` trait (Phase 1 implemented enqueue;
    Phase 2 consumes). The production binding is discussed in workers/README.md: either the Rust
    sqlxmq ``JobRunner`` invokes the Python ``analyze`` entrypoint per job, or a thin Python poller
    claims rows with ``SELECT … FOR UPDATE SKIP LOCKED``. Both satisfy this port.
    """

    def poll(self) -> Optional[JobLease]: ...

    def ack(self, lease: JobLease) -> None: ...

    def retry(self, lease: JobLease) -> None: ...
