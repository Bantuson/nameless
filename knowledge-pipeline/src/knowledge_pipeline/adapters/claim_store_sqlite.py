"""SqliteClaimStore — the REAL :class:`~knowledge_pipeline.ports.ClaimStore`, extending ``registry.sqlite``.

Writes the Phase-4 ``claims`` / ``clusters`` / ``cluster_members`` tables into the SAME local SQLite the
Phase-3 corpus stage produced (or a fresh DB for the offline ``--fixtures`` path). ``sqlite3`` + ``json``
are PYTHON STDLIB, so — like the Phase-3 ``FilesystemCorpusStore`` — this REAL adapter needs no extra
install and its contract tests run on the base env. That is honest verification of the actual persistence
path, not a stand-in.

Clusters are reconstructed from ``clusters`` + ``cluster_members`` joined to ``claims``, partitioned by
``side`` — so the two camps of a contested topic survive a round-trip exactly as
:func:`knowledge_pipeline.pure.cross_reference.cross_reference` produced them.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Callable, Iterable, Optional

from ..claims_sql import CLAIMS_DDL, CLAIMS_SCHEMA_VERSION
from ..domain.claims import Claim, ClaimCluster, ClaimStats
from ..domain.models import CaptionSource
from ..registry_sql import CONNECT_PRAGMAS


class SqliteClaimStore:
    """SQLite-backed claim + cluster store. One instance owns one DB file (the corpus ``registry.sqlite``)."""

    def __init__(self, db_path: str | Path, *, now: Optional[Callable[[], _dt.datetime]] = None) -> None:
        self._db_path = Path(db_path)
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))
        self._conn: Optional[sqlite3.Connection] = None

    # ---- connection ----
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def init_schema(self) -> None:
        conn = self._connection()
        conn.executescript(CLAIMS_DDL)
        conn.execute(
            "INSERT INTO claim_schema_meta(key, value) VALUES('claim_schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(CLAIMS_SCHEMA_VERSION),),
        )
        conn.commit()

    # ---- claims ----
    def upsert_claims(self, claims: Iterable[Claim], *, verified: Optional[dict[str, bool]] = None) -> int:
        verified = verified or {}
        conn = self._connection()
        mined_at = self._now().isoformat()
        n = 0
        with conn:
            for c in claims:
                conn.execute(
                    """
                    INSERT INTO claims
                        (id, claim_text, technique, stage, genre_json, stance, confidence,
                         source_video_id, timestamp_ms, quote, caption_source, topic,
                         citation_verified, mined_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        claim_text=excluded.claim_text, technique=excluded.technique, stage=excluded.stage,
                        genre_json=excluded.genre_json, stance=excluded.stance, confidence=excluded.confidence,
                        source_video_id=excluded.source_video_id, timestamp_ms=excluded.timestamp_ms,
                        quote=excluded.quote, caption_source=excluded.caption_source, topic=excluded.topic,
                        citation_verified=excluded.citation_verified, mined_at=excluded.mined_at
                    """,
                    (
                        c.id, c.claim_text, c.technique, c.stage, json.dumps(c.genre), c.stance,
                        c.confidence, c.source_video_id, c.timestamp_ms, c.quote,
                        c.caption_source.value, c.topic, 1 if verified.get(c.id) else 0, mined_at,
                    ),
                )
                n += 1
        return n

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        conn = self._connection()
        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return _row_to_claim(row) if row is not None else None

    def list_claims(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        technique: Optional[str] = None,
        source_video_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> list[Claim]:
        conn = self._connection()
        clauses: list[str] = []
        params: list[object] = []
        if stage is not None:
            clauses.append("stage = ?"); params.append(stage)
        if technique is not None:
            clauses.append("technique = ?"); params.append(technique)
        if source_video_id is not None:
            clauses.append("source_video_id = ?"); params.append(source_video_id)
        if min_confidence is not None:
            clauses.append("confidence >= ?"); params.append(min_confidence)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM claims{where} ORDER BY topic, source_video_id, timestamp_ms"
        rows = [_row_to_claim(r) for r in conn.execute(sql, params).fetchall()]
        if genre is not None:
            rows = [c for c in rows if genre in c.genre]
        return rows

    # ---- clusters (global; replaced wholesale) ----
    def replace_clusters(self, clusters: Iterable[ClaimCluster]) -> int:
        conn = self._connection()
        clusters = list(clusters)
        with conn:
            conn.execute("DELETE FROM cluster_members")
            conn.execute("DELETE FROM clusters")
            for cl in clusters:
                conn.execute(
                    """
                    INSERT INTO clusters
                        (topic, stage, technique, genre_json, is_contested,
                         consensus_count, conflict_count, distinct_consensus_sources)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cl.topic, cl.stage, cl.technique, json.dumps(cl.genre),
                        1 if cl.is_contested else 0, len(cl.consensus), len(cl.conflicts),
                        cl.distinct_consensus_sources,
                    ),
                )
                for c in cl.consensus:
                    conn.execute(
                        "INSERT OR REPLACE INTO cluster_members(topic, claim_id, side, stance) VALUES (?, ?, 'consensus', ?)",
                        (cl.topic, c.id, c.stance),
                    )
                for c in cl.conflicts:
                    conn.execute(
                        "INSERT OR REPLACE INTO cluster_members(topic, claim_id, side, stance) VALUES (?, ?, 'conflict', ?)",
                        (cl.topic, c.id, c.stance),
                    )
        return len(clusters)

    def get_cluster(self, topic: str) -> Optional[ClaimCluster]:
        conn = self._connection()
        head = conn.execute("SELECT * FROM clusters WHERE topic = ?", (topic,)).fetchone()
        if head is None:
            return None
        return self._build_cluster(head)

    def list_clusters(
        self,
        *,
        contested_only: bool = False,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
    ) -> list[ClaimCluster]:
        conn = self._connection()
        clauses: list[str] = []
        params: list[object] = []
        if contested_only:
            clauses.append("is_contested = 1")
        if stage is not None:
            clauses.append("stage = ?"); params.append(stage)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        heads = conn.execute(f"SELECT * FROM clusters{where} ORDER BY topic", params).fetchall()
        clusters = [self._build_cluster(h) for h in heads]
        if genre is not None:
            clusters = [cl for cl in clusters if genre in cl.genre]
        return clusters

    def _build_cluster(self, head: sqlite3.Row) -> ClaimCluster:
        conn = self._connection()
        rows = conn.execute(
            """
            SELECT m.side AS side, c.*
            FROM cluster_members m JOIN claims c ON c.id = m.claim_id
            WHERE m.topic = ?
            ORDER BY c.source_video_id, c.timestamp_ms
            """,
            (head["topic"],),
        ).fetchall()
        consensus = [_row_to_claim(r) for r in rows if r["side"] == "consensus"]
        conflicts = [_row_to_claim(r) for r in rows if r["side"] == "conflict"]
        return ClaimCluster(
            topic=head["topic"],
            stage=head["stage"],
            technique=head["technique"],
            genre=json.loads(head["genre_json"]),
            consensus=consensus,
            conflicts=conflicts,
        )

    # ---- stats ----
    def stats(self) -> ClaimStats:
        conn = self._connection()
        total_claims = conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()["c"]
        total_clusters = conn.execute("SELECT COUNT(*) AS c FROM clusters").fetchone()["c"]
        contested = conn.execute("SELECT COUNT(*) AS c FROM clusters WHERE is_contested = 1").fetchone()["c"]
        verified = conn.execute("SELECT COUNT(*) AS c FROM claims WHERE citation_verified = 1").fetchone()["c"]
        by_stage = {r[0]: r[1] for r in conn.execute("SELECT stage, COUNT(*) FROM claims GROUP BY stage").fetchall()}
        by_caption = {
            r[0]: r[1] for r in conn.execute("SELECT caption_source, COUNT(*) FROM claims GROUP BY caption_source").fetchall()
        }
        by_genre: dict[str, int] = {}
        for (genre_json,) in conn.execute("SELECT genre_json FROM claims").fetchall():
            genres = json.loads(genre_json) or ["unknown"]
            for g in genres:
                by_genre[g] = by_genre.get(g, 0) + 1
        return ClaimStats(
            total_claims=total_claims,
            total_clusters=total_clusters,
            contested_clusters=contested,
            citation_verified=verified,
            by_stage=by_stage,
            by_genre=by_genre,
            by_caption_source=by_caption,
        )


def _row_to_claim(row: sqlite3.Row) -> Claim:
    """Reconstruct a Claim from a ``claims`` row (id/topic recompute identically from stored fields)."""
    return Claim(
        claim_text=row["claim_text"],
        technique=row["technique"],
        stage=row["stage"],
        genre=json.loads(row["genre_json"]),
        stance=row["stance"],
        confidence=row["confidence"],
        source_video_id=row["source_video_id"],
        timestamp_ms=row["timestamp_ms"],
        quote=row["quote"],
        caption_source=CaptionSource(row["caption_source"]),
    )
