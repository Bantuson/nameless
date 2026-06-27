"""PgFragmentRepo — the REAL :class:`~nameless_workers.ports.FragmentRepo` over Postgres + pgvector.

Backs the read / state-advance / persist / search contract with one connection. Mirrors the Phase-1
Rust ``PostgresFragmentRepo`` conventions exactly:
  * enum columns are mapped through their canonical snake_case labels — bind ``text`` and cast
    ``$n::text::fragment_state`` on write, project ``state::text`` on read — so the schema stays the
    single source of truth and SQL injection is structurally impossible (parameterized everywhere).
  * :meth:`advance` reproduces the state-machine guard: it reads ``(provenance, state) … FOR UPDATE``,
    computes the next state with the shared pure :func:`transition` (the Rust mirror), and writes it in
    one transaction — so the worker cannot drive an illegal edge even under concurrency.

Retrieval uses pgvector's cosine operator ``<=>``; ``1 - (a <=> b)`` is the similarity score. The
embedding column is chosen from a fixed enum (never user input), so composing it into the SQL text is
safe. ``psycopg`` + ``pgvector`` are imported lazily (env-gated); importing this module is free.
"""

from __future__ import annotations

import time
from typing import Optional
from uuid import UUID

import numpy as np

from ..domain.models import AudioFeatures, Embedding, FragmentRecord, SearchHit
from ..domain.provenance import Provenance
from ..domain.state import FragmentState, Transition, transition
from ..ports import SearchField, SearchQuery

_FIELD_TO_COLUMN = {
    SearchField.AUDIO: "audio_embedding",
    SearchField.NOTE: "note_embedding",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


class PgFragmentRepo:
    """Postgres-backed fragment repo + feature store + vector index."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None  # connected lazily

    # ---- connection (lazy; registers the pgvector type adapter) ----
    def _connection(self):
        if self._conn is None:
            import psycopg  # lazy
            from pgvector.psycopg import register_vector  # lazy

            conn = psycopg.connect(self._dsn, autocommit=True)
            register_vector(conn)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- read ----
    def get_fragment(self, fragment_id: UUID) -> Optional[FragmentRecord]:
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, project_id, kind, provenance::text, audio_uri,
                       duration_ms, sample_rate, note_text, state::text
                from fragments
                where id = %s
                """,
                (fragment_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return FragmentRecord(
            id=row[0],
            project_id=row[1],
            kind=row[2],
            provenance=row[3],
            audio_uri=row[4],
            duration_ms=row[5],
            sample_rate=row[6],
            note_text=row[7],
            state=row[8],
        )

    # ---- guarded state advance (mirror of the Rust state machine) ----
    def advance(self, fragment_id: UUID, t: Transition) -> str:
        conn = self._connection()
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    "select provenance::text, state::text from fragments where id = %s for update",
                    (fragment_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(f"fragment {fragment_id} not found")
                provenance = Provenance.from_db_str(row[0])
                current = FragmentState.from_db_str(row[1])
                # Raises IllegalTransition on an illegal edge — the transaction then rolls back.
                nxt = transition(provenance, current, t)
                cur.execute(
                    "update fragments set state = %s::text::fragment_state where id = %s",
                    (nxt.value, fragment_id),
                )
        return nxt.value

    # ---- persist features (upsert one fragment_features row) ----
    def persist_features(self, fragment_id: UUID, features: AudioFeatures) -> None:
        from psycopg.types.json import Json  # lazy

        conn = self._connection()
        f0 = {
            "times_s": features.f0_contour.times_s,
            "f0_hz": features.f0_contour.f0_hz,
            "confidence": features.f0_contour.confidence,
        }
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into fragment_features
                    (fragment_id, f0_contour, chroma, chroma_mean, onsets_s, beat_grid_s,
                     tempo_bpm, key, key_confidence, loudness_lufs,
                     sample_rate, duration_s, hop_length, analyzer_version, created_at_ms)
                values
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (fragment_id) do update set
                    f0_contour       = excluded.f0_contour,
                    chroma           = excluded.chroma,
                    chroma_mean      = excluded.chroma_mean,
                    onsets_s         = excluded.onsets_s,
                    beat_grid_s      = excluded.beat_grid_s,
                    tempo_bpm        = excluded.tempo_bpm,
                    key              = excluded.key,
                    key_confidence   = excluded.key_confidence,
                    loudness_lufs    = excluded.loudness_lufs,
                    sample_rate      = excluded.sample_rate,
                    duration_s       = excluded.duration_s,
                    hop_length       = excluded.hop_length,
                    analyzer_version = excluded.analyzer_version,
                    created_at_ms    = excluded.created_at_ms
                """,
                (
                    fragment_id,
                    Json(f0),
                    Json(features.chroma),
                    Json(features.chroma_mean),
                    Json(features.onsets_s),
                    Json(features.beat_grid_s),
                    features.tempo_bpm,
                    features.key.name,
                    features.key.correlation,
                    features.loudness_lufs,
                    features.sample_rate,
                    features.duration_s,
                    features.hop_length,
                    features.analyzer_version,
                    _now_ms(),
                ),
            )

    # ---- persist embeddings (the two joint-space vector columns) ----
    def persist_embeddings(self, fragment_id: UUID, audio: Embedding, note: Embedding) -> None:
        conn = self._connection()
        audio_vec = np.asarray(audio.vector, dtype=np.float32)
        note_vec = np.asarray(note.vector, dtype=np.float32)
        with conn.cursor() as cur:
            cur.execute(
                """
                update fragments
                set audio_embedding = %s,
                    note_embedding  = %s,
                    embedding_model = %s
                where id = %s
                """,
                (audio_vec, note_vec, audio.model_name, fragment_id),
            )

    # ---- fetch one stored vector (to seed --similar-to) ----
    def get_embedding(self, fragment_id: UUID, field: SearchField) -> Optional[list[float]]:
        column = _FIELD_TO_COLUMN[field]  # from a fixed enum — safe to interpolate
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(
                f"select {column} from fragments where id = %s",
                (fragment_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        # pgvector returns a numpy array; hand back a plain list (used only as a query vector).
        return np.asarray(row[0], dtype=np.float64).tolist()

    # ---- retrieval (CAP-04) ----
    def search(self, query: SearchQuery) -> list[SearchHit]:
        column = _FIELD_TO_COLUMN[query.field]  # from a fixed enum — safe to interpolate
        conn = self._connection()
        q_vec = np.asarray(query.vector, dtype=np.float32)
        sql = f"""
            select f.id, ff.key, ff.tempo_bpm, 1 - (f.{column} <=> %(q)s) as score
            from fragments f
            left join fragment_features ff on ff.fragment_id = f.id
            where f.{column} is not null
              and (%(project)s::uuid is null or f.project_id = %(project)s)
              and (%(exclude)s::uuid is null or f.id <> %(exclude)s)
            order by f.{column} <=> %(q)s asc
            limit %(limit)s
        """
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "q": q_vec,
                    "project": query.project_id,
                    "exclude": query.exclude_fragment_id,
                    "limit": query.limit,
                },
            )
            rows = cur.fetchall()
        return [
            SearchHit(
                fragment_id=row[0],
                key=row[1],
                tempo_bpm=row[2],
                score=float(row[3]),
            )
            for row in rows
        ]
