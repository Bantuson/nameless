"""SeparationJobConsumer — the Phase-8 stem-separation orchestration, pure over injected ports.

Like the Phase-2 :class:`~nameless_workers.consumer.AnalyzeJobConsumer`, this contains NO demucs, NO
torch, NO SQL. It wires the ports in the one correct order and drives the separation:

    consume SeparateTrack{reference_track_id}
        → load track bytes        (TrackLoader)
        → separate into stems      (StemSeparator)    ← SAMP-01
        → content-hash each stem + build records  (pure/separation.py)
        → retain stem bytes        (StemBlobStore, write-if-absent)
        → persist stem records     (StemRecordStore, idempotent)

Because every dependency is a port, the entire flow is exercised in tests with deterministic fakes —
stem naming, the retention record (model+version provenance), and idempotency are all genuinely tested
with no ML or object store. The real Demucs adapter swaps in unchanged (ports-and-adapters law).

Idempotency / at-least-once delivery: the durable queue may deliver a job more than once, and a
producer may ask to re-separate the same track. Separation is content-addressed (a deterministic
separator yields the same stem bytes → the same hash → the same key), and both retention and record
persistence are write-if-absent / dedup-on-content — so a redeliver retains nothing new and inserts no
duplicate rows. :meth:`handle` is therefore safe to call repeatedly.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from .domain.models import SeparateTrackJob
from .pure.separation import build_stem_records
from .separation_ports import StemBlobStore, StemRecordStore, StemSeparator, TrackLoader

logger = logging.getLogger("nameless_workers.separation")


class SeparationError(Exception):
    """A non-recoverable separation failure for one track (load / separate / retain / persist).

    Raised so the caller (the run loop / Rust job runner) records a failed attempt and lets the
    queue's retry/dead-letter policy apply. Separation is idempotent, so a retry re-enters cleanly.
    """


class TrackNotFound(SeparationError):
    """The job referenced a reference-track id the loader does not know."""


class SeparationOutcome(BaseModel):
    """The compact result of separating one track — safe to log/print (no audio, no arrays)."""

    model_config = ConfigDict(frozen=True)

    reference_track_id: str
    separator_model: str
    separator_version: str
    stem_types: list[str]
    stem_uris: list[str]
    n_stems: int
    skipped: bool = False  # True when every stem was already retained (idempotent redelivery)


class SeparationJobConsumer:
    """Orchestrates one uploaded track into its retained stem library. Stateless; safe to reuse."""

    def __init__(
        self,
        track_loader: TrackLoader,
        separator: StemSeparator,
        blob_store: StemBlobStore,
        record_store: StemRecordStore,
    ) -> None:
        self._track_loader = track_loader
        self._separator = separator
        self._blob_store = blob_store
        self._record_store = record_store

    def handle(self, job: SeparateTrackJob) -> SeparationOutcome:
        """Process one ``SeparateTrack`` job end-to-end. Idempotent under redelivery / re-separation."""
        reference_track_id = job.reference_track_id

        # ---- load the uploaded track's bytes (shared with the Phase-7 reference upload) ----
        try:
            audio = self._track_loader.load(reference_track_id)
        except KeyError as exc:
            raise TrackNotFound(f"reference track {reference_track_id} not found") from exc

        # ---- separate (the heavy leaf, behind the port) ----
        try:
            result = self._separator.separate(audio)
        except Exception as exc:  # noqa: BLE001 - normalize any leaf failure into a retryable error
            raise SeparationError(
                f"separation failed for track {reference_track_id}: {exc}"
            ) from exc

        # ---- content-hash + build the retained records (pure) ----
        records = build_stem_records(reference_track_id, result)

        # ---- retain each stem's bytes (write-if-absent) + persist its record (idempotent) ----
        already = {r.audio_uri for r in self._record_store.list_stems(reference_track_id)}
        newly_retained = 0
        for record, separated in zip(records, result.stems):
            if record.audio_uri not in already:
                newly_retained += 1
            self._blob_store.put(record.audio_uri, separated.audio)
            self._record_store.insert_stem(record)

        skipped = newly_retained == 0 and len(records) > 0
        if skipped:
            logger.info(
                "track %s already separated by %s; retained nothing new (idempotent)",
                reference_track_id,
                result.separator_model,
            )
        else:
            logger.info(
                "separated track %s into %d stems with %s@%s",
                reference_track_id,
                len(records),
                result.separator_model,
                result.separator_version,
            )

        return SeparationOutcome(
            reference_track_id=str(reference_track_id),
            separator_model=result.separator_model,
            separator_version=result.separator_version,
            stem_types=[r.stem_type.value for r in records],
            stem_uris=[r.audio_uri for r in records],
            n_stems=len(records),
            skipped=skipped,
        )
