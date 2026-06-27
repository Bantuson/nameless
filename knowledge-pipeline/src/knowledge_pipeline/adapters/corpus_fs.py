"""FilesystemCorpusStore — the REAL :class:`~knowledge_pipeline.ports.CorpusStore`.

Materializes the corpus exactly as research ARCHITECTURE.md specifies: immutable snapshot FILES (full
timestamped transcripts, the durable evidence) + a local ``registry.sqlite`` of compact rows, indexed by
``video_id``. Deliberately OFF the runtime Postgres — the knowledge layer and the fragment graph share no
storage (see :mod:`knowledge_pipeline.registry_sql`).

NOTE — runnable on the build box: ``sqlite3`` and ``json`` are PYTHON STDLIB, so unlike the workers' real
Postgres/ML adapters, this real store needs NO extra install and its contract tests run on the base env.
That is honest verification of the actual persistence path, not just a fake.

Layout (``registry_sql.SNAPSHOT_LAYOUT``)::

    <root>/registry.sqlite
    <root>/snapshots/<video_id>.json   # {video_id, caption_source, language, fetched_via,
                                        #  content_sha256, retrieval_date, segments:[...]}
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..domain.models import (
    CaptionSource,
    CorpusEntry,
    CorpusStats,
    ExtractabilityResult,
    RawTranscript,
    SnapshotRecord,
    TranscriptSegment,
    Verdict,
    VideoRef,
)
from ..pure.snapshot import canonical_payload
from ..registry_sql import CONNECT_PRAGMAS, DDL, SCHEMA_VERSION


def _iso(dt: _dt.datetime) -> str:
    return dt.isoformat()


def _parse_dt(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s)


class FilesystemCorpusStore:
    """Filesystem snapshots + registry.sqlite. One instance owns one corpus root."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._snapshots_dir = self._root / "snapshots"
        self._db_path = self._root / "registry.sqlite"
        self._conn: Optional[sqlite3.Connection] = None

    # ---- connection (lazy) ----
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._root.mkdir(parents=True, exist_ok=True)
            self._snapshots_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            for pragma in CONNECT_PRAGMAS:
                conn.execute(pragma)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- schema ----
    def init_schema(self) -> None:
        conn = self._connection()
        conn.executescript(DDL)
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    # ---- idempotency ----
    def has(self, video_id: str) -> bool:
        conn = self._connection()
        row = conn.execute("SELECT 1 FROM sources WHERE video_id = ?", (video_id,)).fetchone()
        return row is not None

    def known_ids(self) -> set[str]:
        conn = self._connection()
        rows = conn.execute("SELECT video_id FROM sources").fetchall()
        return {r["video_id"] for r in rows}

    # ---- snapshot (immutable evidence file) ----
    def write_snapshot(self, transcript: RawTranscript, record: SnapshotRecord) -> str:
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        payload = canonical_payload(transcript)
        payload["content_sha256"] = record.content_sha256
        payload["retrieval_date"] = _iso(record.retrieval_date)
        rel_path = f"snapshots/{transcript.video_id}.json"
        abs_path = self._root / rel_path
        abs_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return rel_path

    def load_snapshot(self, video_id: str) -> Optional[RawTranscript]:
        abs_path = self._snapshots_dir / f"{video_id}.json"
        if not abs_path.exists():
            return None
        payload = json.loads(abs_path.read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment(
                start_s=seg["start_s"],
                duration_s=seg.get("duration_s"),
                text=seg["text"],
            )
            for seg in payload.get("segments", [])
        ]
        return RawTranscript(
            video_id=payload["video_id"],
            caption_source=CaptionSource(payload["caption_source"]),
            language=payload.get("language", "en"),
            fetched_via=payload.get("fetched_via", "unknown"),
            segments=segments,
        )

    # ---- registry upsert (one transaction across the three tables) ----
    def register(self, entry: CorpusEntry) -> None:
        conn = self._connection()
        v = entry.video
        s = entry.snapshot
        x = entry.extractability
        rel_path = f"snapshots/{v.video_id}.json"
        with conn:  # transaction
            conn.execute(
                """
                INSERT INTO sources
                    (video_id, title, channel, url, duration_s, query_origin, genre, stage,
                     artist_anchor, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    title=excluded.title, channel=excluded.channel, url=excluded.url,
                    duration_s=excluded.duration_s, query_origin=excluded.query_origin,
                    genre=excluded.genre, stage=excluded.stage, artist_anchor=excluded.artist_anchor,
                    ingested_at=excluded.ingested_at
                """,
                (
                    v.video_id, v.title, v.channel, v.url, v.duration_s, v.query_origin,
                    v.genre, v.stage, v.artist_anchor, _iso(entry.ingested_at),
                ),
            )
            conn.execute(
                """
                INSERT INTO snapshots
                    (video_id, content_sha256, retrieval_date, caption_source, language,
                     segment_count, char_count, first_segment_s, last_segment_s, snapshot_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    content_sha256=excluded.content_sha256, retrieval_date=excluded.retrieval_date,
                    caption_source=excluded.caption_source, language=excluded.language,
                    segment_count=excluded.segment_count, char_count=excluded.char_count,
                    first_segment_s=excluded.first_segment_s, last_segment_s=excluded.last_segment_s,
                    snapshot_path=excluded.snapshot_path
                """,
                (
                    s.video_id, s.content_sha256, _iso(s.retrieval_date), s.caption_source.value,
                    s.language, s.segment_count, s.char_count, s.first_segment_s, s.last_segment_s,
                    rel_path,
                ),
            )
            conn.execute(
                """
                INSERT INTO extractability
                    (video_id, score, verdict, caption_source_weight, word_density, vocab_presence,
                     actionable_ratio, visual_only_penalty, word_count, vocab_hits, flags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    score=excluded.score, verdict=excluded.verdict,
                    caption_source_weight=excluded.caption_source_weight,
                    word_density=excluded.word_density, vocab_presence=excluded.vocab_presence,
                    actionable_ratio=excluded.actionable_ratio,
                    visual_only_penalty=excluded.visual_only_penalty,
                    word_count=excluded.word_count, vocab_hits=excluded.vocab_hits,
                    flags_json=excluded.flags_json
                """,
                (
                    x.video_id, x.score, x.verdict.value, x.caption_source_weight, x.word_density,
                    x.vocab_presence, x.actionable_ratio, x.visual_only_penalty, x.word_count,
                    x.vocab_hits, json.dumps(x.flags),
                ),
            )

    # ---- read ----
    def get(self, video_id: str) -> Optional[CorpusEntry]:
        conn = self._connection()
        row = conn.execute(
            """
            SELECT s.*, sn.content_sha256, sn.retrieval_date, sn.caption_source, sn.language,
                   sn.segment_count, sn.char_count, sn.first_segment_s, sn.last_segment_s,
                   x.score, x.verdict, x.caption_source_weight, x.word_density, x.vocab_presence,
                   x.actionable_ratio, x.visual_only_penalty, x.word_count, x.vocab_hits, x.flags_json
            FROM sources s
            JOIN snapshots sn ON sn.video_id = s.video_id
            JOIN extractability x ON x.video_id = s.video_id
            WHERE s.video_id = ?
            """,
            (video_id,),
        ).fetchone()
        return _row_to_entry(row) if row is not None else None

    def list_entries(
        self,
        *,
        genre: Optional[str] = None,
        verdict: Optional[Verdict] = None,
        min_score: Optional[float] = None,
        order_by_score: bool = False,
    ) -> list[CorpusEntry]:
        conn = self._connection()
        clauses: list[str] = []
        params: list[object] = []
        if genre is not None:
            clauses.append("s.genre = ?")
            params.append(genre)
        if verdict is not None:
            clauses.append("x.verdict = ?")
            params.append(verdict.value)
        if min_score is not None:
            clauses.append("x.score >= ?")
            params.append(min_score)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order = "x.score DESC" if order_by_score else "s.ingested_at ASC"
        sql = f"""
            SELECT s.*, sn.content_sha256, sn.retrieval_date, sn.caption_source, sn.language,
                   sn.segment_count, sn.char_count, sn.first_segment_s, sn.last_segment_s,
                   x.score, x.verdict, x.caption_source_weight, x.word_density, x.vocab_presence,
                   x.actionable_ratio, x.visual_only_penalty, x.word_count, x.vocab_hits, x.flags_json
            FROM sources s
            JOIN snapshots sn ON sn.video_id = s.video_id
            JOIN extractability x ON x.video_id = s.video_id
            {where}
            ORDER BY {order}
        """
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def stats(self) -> CorpusStats:
        conn = self._connection()
        total = conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"]

        def _group(sql: str) -> dict[str, int]:
            return {r[0]: r[1] for r in conn.execute(sql).fetchall()}

        by_verdict = _group("SELECT verdict, COUNT(*) FROM extractability GROUP BY verdict")
        by_genre = _group(
            "SELECT COALESCE(genre, 'unknown'), COUNT(*) FROM sources GROUP BY genre"
        )
        by_caption = _group(
            "SELECT caption_source, COUNT(*) FROM snapshots GROUP BY caption_source"
        )
        return CorpusStats(
            total=total,
            by_verdict=by_verdict,
            by_genre=by_genre,
            by_caption_source=by_caption,
        )


def _row_to_entry(row: sqlite3.Row) -> CorpusEntry:
    """Reconstruct a CorpusEntry from a joined sources+snapshots+extractability row."""
    video = VideoRef(
        video_id=row["video_id"],
        title=row["title"] or "",
        channel=row["channel"],
        duration_s=row["duration_s"],
        query_origin=row["query_origin"],
        genre=row["genre"],
        stage=row["stage"],
        artist_anchor=row["artist_anchor"],
    )
    snapshot = SnapshotRecord(
        video_id=row["video_id"],
        content_sha256=row["content_sha256"],
        retrieval_date=_parse_dt(row["retrieval_date"]),
        caption_source=CaptionSource(row["caption_source"]),
        language=row["language"],
        segment_count=row["segment_count"],
        char_count=row["char_count"],
        first_segment_s=row["first_segment_s"],
        last_segment_s=row["last_segment_s"],
    )
    extractability = ExtractabilityResult(
        video_id=row["video_id"],
        score=row["score"],
        verdict=Verdict(row["verdict"]),
        caption_source_weight=row["caption_source_weight"],
        word_density=row["word_density"],
        vocab_presence=row["vocab_presence"],
        actionable_ratio=row["actionable_ratio"],
        visual_only_penalty=row["visual_only_penalty"],
        word_count=row["word_count"],
        vocab_hits=row["vocab_hits"],
        flags=json.loads(row["flags_json"]),
    )
    return CorpusEntry(
        video=video,
        snapshot=snapshot,
        extractability=extractability,
        ingested_at=_parse_dt(row["ingested_at"]),
    )
