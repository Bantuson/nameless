"""InMemorySkillStore — the RAM-safe fake for :class:`~knowledge_pipeline.ports.SkillStore`.

Plain dicts; no sqlite, no filesystem. A FAITHFUL double for the filesystem store: same idempotent upsert
by skill id, same ``set_status`` promotion semantics, same filter on ``list_skills``, same ``stats``
roll-up — so a pipeline/audit test written against this fake proves the behaviour the real store
reproduces, with zero I/O. (It also flips the in-memory ``body_md`` frontmatter status on promotion, so a
promoted skill's stored body matches what the filesystem store would write to disk.)
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable, Optional

from ..domain.skills import AuthoredSkill, SkillStats, SkillStatus
from ..pure.layered_emitter import set_frontmatter_status


class InMemorySkillStore:
    """An in-memory authored-skill store."""

    def __init__(self, *, now: Optional[Callable[[], _dt.datetime]] = None) -> None:
        self._skills: dict[str, AuthoredSkill] = {}
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def init_schema(self) -> None:
        return None

    def upsert_skill(self, skill: AuthoredSkill) -> None:
        self._skills[skill.id] = skill

    def get_skill(self, skill_id: str) -> Optional[AuthoredSkill]:
        return self._skills.get(skill_id)

    def set_status(self, skill_id: str, status: SkillStatus) -> Optional[AuthoredSkill]:
        skill = self._skills.get(skill_id)
        if skill is None:
            return None
        updated = skill.model_copy(
            update={
                "status": status,
                "body_md": set_frontmatter_status(skill.body_md, status),
                "promoted_at": self._now() if status is SkillStatus.PROMOTED else None,
            }
        )
        self._skills[skill_id] = updated
        return updated

    def list_skills(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        status: Optional[SkillStatus] = None,
    ) -> list[AuthoredSkill]:
        rows = list(self._skills.values())
        if stage is not None:
            rows = [s for s in rows if s.stage == stage]
        if genre is not None:
            rows = [s for s in rows if s.genre == genre]
        if status is not None:
            rows = [s for s in rows if s.status is status]
        rows.sort(key=lambda s: (s.genre, s.stage))
        return rows

    def stats(self) -> SkillStats:
        by_stage: dict[str, int] = {}
        by_genre: dict[str, int] = {}
        by_conf: dict[str, int] = {}
        draft = promoted = 0
        for s in self._skills.values():
            by_stage[s.stage] = by_stage.get(s.stage, 0) + 1
            by_genre[s.genre] = by_genre.get(s.genre, 0) + 1
            tier = s.confidence_tier
            by_conf[tier] = by_conf.get(tier, 0) + 1
            if s.status is SkillStatus.PROMOTED:
                promoted += 1
            else:
                draft += 1
        return SkillStats(
            total_skills=len(self._skills),
            draft=draft,
            promoted=promoted,
            by_stage=by_stage,
            by_genre=by_genre,
            by_confidence=by_conf,
        )
