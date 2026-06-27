"""FilesystemSkillStore — the REAL :class:`~knowledge_pipeline.ports.SkillStore` (KNOW-09/11).

Writes the authored skill TWO ways, because each serves a different reader:
  * the **SKILL.md file** under ``<skills_root>/skills/production/<stage>/<genre>/SKILL.md`` — the durable,
    human-/agent-readable artifact (the thing the M1 arranger/mixer actually loads), version-controlled;
  * a **registry row** in the SAME ``registry.sqlite`` (``skills`` + ``skill_citations`` tables) — the
    lean, queryable index for ``skills list | show | audit | stats`` and the citation trail.

``sqlite3`` + ``json`` + ``pathlib`` are PYTHON STDLIB, so — like the Phase-3 ``FilesystemCorpusStore`` and
the Phase-4 ``SqliteClaimStore`` — this REAL adapter needs no extra install and its contract tests run on
the base env: honest verification of the actual persistence path, not a stand-in. Promotion rewrites only
the file's frontmatter ``status`` banner (the body is byte-stable) and the row's status/promoted_at.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import sqlite3
from pathlib import Path
from typing import Callable, Optional

from ..domain.skills import AuthoredSkill, SkillStats, SkillStatus
from ..pure.layered_emitter import set_frontmatter_status
from ..registry_sql import CONNECT_PRAGMAS
from ..skills_sql import SKILLS_DDL, SKILLS_SCHEMA_VERSION


class FilesystemSkillStore:
    """SQLite registry (``registry.sqlite``) + on-disk SKILL.md files under ``skills_root``."""

    def __init__(
        self,
        db_path: str | Path,
        skills_root: str | Path,
        *,
        now: Optional[Callable[[], _dt.datetime]] = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._root = Path(skills_root)
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
        conn.executescript(SKILLS_DDL)
        conn.execute(
            "INSERT INTO skill_schema_meta(key, value) VALUES('skill_schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SKILLS_SCHEMA_VERSION),),
        )
        conn.commit()

    def _abspath(self, relpath: str) -> Path:
        return self._root / relpath

    # ---- write ----
    def upsert_skill(self, skill: AuthoredSkill) -> None:
        # 1. the durable artifact: the SKILL.md file
        path = self._abspath(skill.relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(skill.body_md, encoding="utf-8")
        body_sha = hashlib.sha256(skill.body_md.encode("utf-8")).hexdigest()

        # 2. the lean registry index
        conn = self._connection()
        with conn:
            conn.execute(
                """
                INSERT INTO skills
                    (id, name, description, stage, genre, status, relpath, prompt_version,
                     citation_count, distinct_sources, default_source_count, default_contested,
                     consensus_topics, conflict_topics, body_sha256, authored_at, promoted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, description=excluded.description, stage=excluded.stage,
                    genre=excluded.genre, status=excluded.status, relpath=excluded.relpath,
                    prompt_version=excluded.prompt_version, citation_count=excluded.citation_count,
                    distinct_sources=excluded.distinct_sources, default_source_count=excluded.default_source_count,
                    default_contested=excluded.default_contested, consensus_topics=excluded.consensus_topics,
                    conflict_topics=excluded.conflict_topics, body_sha256=excluded.body_sha256,
                    authored_at=excluded.authored_at, promoted_at=excluded.promoted_at
                """,
                (
                    skill.id, skill.name, skill.description, skill.stage, skill.genre, skill.status.value,
                    skill.relpath, skill.prompt_version, skill.citation_count, skill.distinct_sources,
                    skill.default_source_count, 1 if skill.default_contested else 0, skill.consensus_topics,
                    skill.conflict_topics, body_sha, skill.authored_at.isoformat(),
                    skill.promoted_at.isoformat() if skill.promoted_at else None,
                ),
            )
            conn.execute("DELETE FROM skill_citations WHERE skill_id = ?", (skill.id,))
            for cid in dict.fromkeys(skill.claim_ids):  # dedupe, preserve order
                conn.execute(
                    "INSERT OR REPLACE INTO skill_citations(skill_id, claim_id, kind, stance, topic) "
                    "VALUES (?, ?, 'cited', NULL, '')",
                    (skill.id, cid),
                )

    # ---- read ----
    def get_skill(self, skill_id: str) -> Optional[AuthoredSkill]:
        conn = self._connection()
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_skill(row, with_body=True)

    def set_status(self, skill_id: str, status: SkillStatus) -> Optional[AuthoredSkill]:
        conn = self._connection()
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if row is None:
            return None
        # rewrite ONLY the file frontmatter banner (body otherwise byte-stable)
        path = self._abspath(row["relpath"])
        promoted_at = self._now() if status is SkillStatus.PROMOTED else None
        if path.exists():
            new_body = set_frontmatter_status(path.read_text(encoding="utf-8"), status)
            path.write_text(new_body, encoding="utf-8")
            body_sha = hashlib.sha256(new_body.encode("utf-8")).hexdigest()
        else:
            body_sha = row["body_sha256"]
        with conn:
            conn.execute(
                "UPDATE skills SET status = ?, promoted_at = ?, body_sha256 = ? WHERE id = ?",
                (status.value, promoted_at.isoformat() if promoted_at else None, body_sha, skill_id),
            )
        return self.get_skill(skill_id)

    def list_skills(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        status: Optional[SkillStatus] = None,
    ) -> list[AuthoredSkill]:
        conn = self._connection()
        clauses: list[str] = []
        params: list[object] = []
        if stage is not None:
            clauses.append("stage = ?"); params.append(stage)
        if genre is not None:
            clauses.append("genre = ?"); params.append(genre)
        if status is not None:
            clauses.append("status = ?"); params.append(status.value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM skills{where} ORDER BY genre, stage"
        return [self._row_to_skill(r, with_body=False) for r in conn.execute(sql, params).fetchall()]

    def stats(self) -> SkillStats:
        conn = self._connection()
        rows = conn.execute("SELECT * FROM skills").fetchall()
        by_stage: dict[str, int] = {}
        by_genre: dict[str, int] = {}
        by_conf: dict[str, int] = {}
        draft = promoted = 0
        for r in rows:
            by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + 1
            by_genre[r["genre"]] = by_genre.get(r["genre"], 0) + 1
            tier = self._row_to_skill(r, with_body=False).confidence_tier
            by_conf[tier] = by_conf.get(tier, 0) + 1
            if r["status"] == SkillStatus.PROMOTED.value:
                promoted += 1
            else:
                draft += 1
        return SkillStats(
            total_skills=len(rows),
            draft=draft,
            promoted=promoted,
            by_stage=by_stage,
            by_genre=by_genre,
            by_confidence=by_conf,
        )

    # ---- reconstruction ----
    def _claim_ids(self, skill_id: str) -> list[str]:
        conn = self._connection()
        rows = conn.execute(
            "SELECT claim_id FROM skill_citations WHERE skill_id = ? ORDER BY claim_id", (skill_id,)
        ).fetchall()
        return [r["claim_id"] for r in rows]

    def _row_to_skill(self, row: sqlite3.Row, *, with_body: bool) -> AuthoredSkill:
        body_md = ""
        if with_body:
            path = self._abspath(row["relpath"])
            if path.exists():
                body_md = path.read_text(encoding="utf-8")
        promoted_at = row["promoted_at"]
        return AuthoredSkill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            stage=row["stage"],
            genre=row["genre"],
            status=SkillStatus(row["status"]),
            relpath=row["relpath"],
            prompt_version=row["prompt_version"],
            claim_ids=self._claim_ids(row["id"]),
            citation_count=row["citation_count"],
            distinct_sources=row["distinct_sources"],
            default_source_count=row["default_source_count"],
            default_contested=bool(row["default_contested"]),
            consensus_topics=row["consensus_topics"],
            conflict_topics=row["conflict_topics"],
            body_sha256=row["body_sha256"],
            body_md=body_md,
            authored_at=_dt.datetime.fromisoformat(row["authored_at"]),
            promoted_at=_dt.datetime.fromisoformat(promoted_at) if promoted_at else None,
        )
