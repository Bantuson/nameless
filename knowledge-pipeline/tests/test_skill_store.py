"""SkillStore — InMemory (fake) and Filesystem (REAL, sqlite+files) round-trip + promotion (KNOW-09/11).

The REAL FilesystemSkillStore uses only stdlib (sqlite3 + pathlib), so its contract test runs on the base
env: it verifies the ACTUAL persistence path (a real registry.sqlite + a real SKILL.md on disk), then the
human-gated draft -> promoted transition rewrites only the frontmatter banner.
"""

from __future__ import annotations

from pathlib import Path

from knowledge_pipeline.adapters import FilesystemSkillStore, InMemorySkillStore
from knowledge_pipeline.domain.skills import ProductionCell, SkillStatus
from knowledge_pipeline.pure.cell_selection import clusters_for_cell
from knowledge_pipeline.pure.synthesis_template import template_synthesize
from knowledge_pipeline.synthesis_pipeline import build_authored_skill

from .conftest import FIXED_NOW, mine_fixture_claim_layer


def _skill(stage="drums", genre="amapiano"):
    store, _corpus, _snaps = mine_fixture_claim_layer()
    cc = clusters_for_cell(store.list_clusters(), ProductionCell(stage=stage, genre=genre))
    draft = template_synthesize(ProductionCell(stage=stage, genre=genre), cc)
    return build_authored_skill(draft, status=SkillStatus.DRAFT, now=FIXED_NOW)


# ---- in-memory fake ----------------------------------------------------------------------------


def test_mem_store_upsert_and_get():
    store = InMemorySkillStore(now=lambda: FIXED_NOW)
    skill = _skill()
    store.upsert_skill(skill)
    got = store.get_skill(skill.id)
    assert got is not None and got.id == skill.id
    assert got.status is SkillStatus.DRAFT
    assert got.body_md == skill.body_md


def test_mem_store_promote_flips_status_and_body_banner():
    store = InMemorySkillStore(now=lambda: FIXED_NOW)
    skill = _skill()
    store.upsert_skill(skill)
    updated = store.set_status(skill.id, SkillStatus.PROMOTED)
    assert updated is not None
    assert updated.status is SkillStatus.PROMOTED
    assert "\nstatus: promoted\n" in updated.body_md
    assert updated.promoted_at is not None


def test_mem_store_upsert_is_idempotent_by_cell_id():
    store = InMemorySkillStore()
    a, b = _skill(), _skill()
    assert a.id == b.id  # same cell -> same id
    store.upsert_skill(a)
    store.upsert_skill(b)
    assert store.stats().total_skills == 1


# ---- real filesystem store ---------------------------------------------------------------------


def test_fs_store_writes_a_real_skill_md_file(tmp_path):
    store = FilesystemSkillStore(tmp_path / "registry.sqlite", tmp_path, now=lambda: FIXED_NOW)
    store.init_schema()
    skill = _skill()
    store.upsert_skill(skill)
    on_disk = Path(tmp_path) / skill.relpath
    assert on_disk.exists()
    text = on_disk.read_text(encoding="utf-8")
    assert "name: amapiano-drums" in text
    assert "## Default — act on this" in text


def test_fs_store_round_trips_metadata_and_claim_ids(tmp_path):
    store = FilesystemSkillStore(tmp_path / "registry.sqlite", tmp_path, now=lambda: FIXED_NOW)
    store.init_schema()
    skill = _skill()
    store.upsert_skill(skill)
    got = store.get_skill(skill.id)
    assert got is not None
    assert got.citation_count == skill.citation_count
    assert got.distinct_sources == skill.distinct_sources
    assert got.default_contested == skill.default_contested
    assert set(got.claim_ids) == set(skill.claim_ids)
    assert got.body_md == skill.body_md  # body read back from the file


def test_fs_store_promote_rewrites_file_and_row(tmp_path):
    store = FilesystemSkillStore(tmp_path / "registry.sqlite", tmp_path, now=lambda: FIXED_NOW)
    store.init_schema()
    skill = _skill()
    store.upsert_skill(skill)
    store.set_status(skill.id, SkillStatus.PROMOTED)

    got = store.get_skill(skill.id)
    assert got.status is SkillStatus.PROMOTED
    assert got.promoted_at is not None
    on_disk = (Path(tmp_path) / skill.relpath).read_text(encoding="utf-8")
    assert "\nstatus: promoted\n" in on_disk
    assert "PROMOTED" in on_disk  # the body banner flipped too


def test_fs_store_list_and_filter(tmp_path):
    store = FilesystemSkillStore(tmp_path / "registry.sqlite", tmp_path, now=lambda: FIXED_NOW)
    store.init_schema()
    store.upsert_skill(_skill("drums", "amapiano"))
    store.upsert_skill(_skill("bassline", "deep-house"))
    assert len(store.list_skills()) == 2
    assert len(store.list_skills(genre="amapiano")) == 1
    assert len(store.list_skills(status=SkillStatus.PROMOTED)) == 0


def test_fs_store_stats(tmp_path):
    store = FilesystemSkillStore(tmp_path / "registry.sqlite", tmp_path, now=lambda: FIXED_NOW)
    store.init_schema()
    store.upsert_skill(_skill("drums", "amapiano"))       # contested -> LOW
    store.upsert_skill(_skill("bassline", "deep-house"))  # 3-source -> HIGH
    stats = store.stats()
    assert stats.total_skills == 2
    assert stats.draft == 2 and stats.promoted == 0
    assert stats.by_confidence.get("HIGH") == 1
