"""AnalyzeJobConsumer — the Phase-2 orchestration, pure over injected ports.

This is the heart of the worker, and it deliberately contains NO librosa, NO torch, NO SQL. It wires
the ports in the one correct order and drives the lifecycle:

    consume FeatureExtract{fragment_id}
        → load raw bytes        (AudioLoader)
        → extract features      (FeatureExtractor)   ← CAP-03
        → embed audio + note    (Embedder)           ← CAP-04
        → persist both          (FragmentRepo)
        → advance state         Captured → Analyzing → Analyzed   (guarded mirror of Rust rules)

Because every dependency is a port, the entire flow is exercised in tests with deterministic fakes —
the orchestration, the persistence contract, and the state-machine mirror are all genuinely tested
without any ML or database. The real adapters swap in unchanged (ports-and-adapters law).

Idempotency / at-least-once delivery: the durable queue delivers a job *at least* once, so a redeliver
can arrive after the fragment is already analyzed (ack lost) or mid-flight (crash after ``Analyzing``).
:meth:`handle` is therefore idempotent — it inspects current state and resumes or skips rather than
driving an illegal transition.
"""

from __future__ import annotations

import logging

from . import CLAP_DIM
from .domain.models import AnalyzeOutcome, FeatureExtractJob
from .domain.provenance import Provenance
from .domain.state import FragmentState, IllegalTransition, Transition
from .ports import AudioLoader, Embedder, FeatureExtractor, FragmentRepo

logger = logging.getLogger("nameless_workers.consumer")


class AnalyzeError(Exception):
    """A non-recoverable analysis failure for one fragment (load/extract/embed/persist).

    Raised so the caller (the run loop / the Rust job runner) records a failed attempt and lets the
    queue's :class:`RetryPolicy` (≈5 attempts, exponential backoff — mirrored from Phase 1) retry or
    dead-letter. On failure the fragment is left in ``Analyzing`` (not reverted): the Rust lifecycle
    has no "analysis failed" state, and a retry re-enters cleanly via the idempotency path.
    """


class FragmentNotFound(AnalyzeError):
    """The job referenced a fragment id the repo does not know."""


class AnalyzeJobConsumer:
    """Orchestrates one fragment from ``captured`` to ``analyzed``. Stateless; safe to reuse."""

    def __init__(
        self,
        loader: AudioLoader,
        extractor: FeatureExtractor,
        embedder: Embedder,
        repo: FragmentRepo,
    ) -> None:
        self._loader = loader
        self._extractor = extractor
        self._embedder = embedder
        self._repo = repo

    def handle(self, job: FeatureExtractJob) -> AnalyzeOutcome:
        """Process one ``FeatureExtract`` job end-to-end. Idempotent under redelivery."""
        fragment_id = job.fragment_id

        record = self._repo.get_fragment(fragment_id)
        if record is None:
            raise FragmentNotFound(f"fragment {fragment_id} not found")

        provenance = Provenance.from_db_str(record.provenance)
        current = FragmentState.from_db_str(record.state)

        # ---- idempotency: a redelivered job for an already-analyzed fragment is a no-op success ----
        if current is FragmentState.ANALYZED:
            logger.info("fragment %s already analyzed; skipping (idempotent)", fragment_id)
            return AnalyzeOutcome(
                fragment_id=fragment_id,
                from_state=current.value,
                to_state=current.value,
                skipped=True,
            )

        # ---- resume point: drive Captured → Analyzing (skip if a crash left us mid-flight) ----
        if current is FragmentState.CAPTURED:
            # advance() applies the SAME guard as Rust; for an ai_generated fragment (which should
            # never receive a FeatureExtract job) this raises IllegalTransition — a structural refusal.
            self._repo.advance(fragment_id, Transition.ANALYZE)
        elif current is FragmentState.ANALYZING:
            logger.info("fragment %s resuming from analyzing (prior attempt crashed)", fragment_id)
        else:
            # Any other state (placed/mixed/ai-path/…) is not analyzable; name the offending pair.
            raise IllegalTransition(from_state=current, transition=Transition.ANALYZE)

        # ---- the heavy work, all behind ports (no ML/DB types leak in here) ----
        try:
            audio = self._loader.load(record.audio_uri)
            features = self._extractor.extract(audio)
            audio_embedding = self._embedder.embed_audio(audio)
            note_embedding = self._embedder.embed_text(record.note_text)
        except Exception as exc:  # noqa: BLE001 - normalize any leaf failure into a retryable error
            raise AnalyzeError(f"analysis failed for fragment {fragment_id}: {exc}") from exc

        # Embeddings must share one joint space, or retrieval-by-note vs -by-audio would be incoherent.
        if audio_embedding.dim != note_embedding.dim:
            raise AnalyzeError(
                f"embedding dim mismatch for {fragment_id}: "
                f"audio={audio_embedding.dim} note={note_embedding.dim} (not one joint space)"
            )
        # ...and that joint width must be CLAP_DIM (512), the `vector(512)` column width. A consistent
        # but wrong-width embedder (e.g. a swapped 1024-d checkpoint) passes the check above and would
        # otherwise fail later as an opaque DB insert error; name it here instead. See P2 review IN-02.
        if audio_embedding.dim != CLAP_DIM:
            raise AnalyzeError(
                f"embedding width mismatch for {fragment_id}: "
                f"embedder produced {audio_embedding.dim}-d vectors, expected CLAP_DIM={CLAP_DIM} "
                f"(the vector({CLAP_DIM}) joint-space column width)"
            )

        # ---- persist (features table + the two vector columns) ----
        self._repo.persist_features(fragment_id, features)
        self._repo.persist_embeddings(fragment_id, audio_embedding, note_embedding)

        # ---- close the gate: Analyzing → Analyzed (now placement becomes legal, per the FSM) ----
        new_state = self._repo.advance(fragment_id, Transition.MARK_ANALYZED)

        logger.info(
            "analyzed fragment %s: key=%s tempo=%.1f lufs=%.1f",
            fragment_id,
            features.key.name,
            features.tempo_bpm,
            features.loudness_lufs,
        )
        return AnalyzeOutcome(
            fragment_id=fragment_id,
            from_state=current.value,
            to_state=new_state,
            key=features.key.name,
            tempo_bpm=features.tempo_bpm,
            loudness_lufs=features.loudness_lufs,
            audio_embedding_dim=audio_embedding.dim,
            note_embedding_dim=note_embedding.dim,
        )
