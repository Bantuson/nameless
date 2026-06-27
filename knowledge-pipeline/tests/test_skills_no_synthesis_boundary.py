"""The Phase-5 trust boundary, as a TESTED invariant (KNOW-07/08).

Two guarantees pinned here so a future change that breaks them fails CI:
  1. the env-gated heavy leaf (``anthropic``) is NEVER imported on the fakes-only synthesis path — the
     whole suite runs on the base env;
  2. the authored-skill domain carries NO field that could smuggle ungrounded content, and the synthesis
     path is structurally bounded to the claim set (a skill cites nothing the claim layer did not extract).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import knowledge_pipeline
from knowledge_pipeline.domain.skills import AuthoredSkill, SkillSection

_SRC_DIR = str(Path(knowledge_pipeline.__file__).resolve().parents[1])


def test_anthropic_is_not_imported_on_the_fake_synthesis_path():
    probe = (
        "import sys\n"
        "import knowledge_pipeline.skills_cli, knowledge_pipeline.synthesis_pipeline\n"
        "from knowledge_pipeline.adapters import FakeSkillSynthesizer, InMemorySkillStore, FilesystemSkillStore\n"
        "assert 'anthropic' not in sys.modules, 'anthropic leaked into the fake path'\n"
        "print('clean')\n"
    )
    env = dict(os.environ, PYTHONPATH=_SRC_DIR)
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_authored_skill_has_no_field_that_hides_ungrounded_content():
    # the skill carries citations + provenance, never a free-floating "advice"/"tip" blob outside a cited
    # section. Every assertable surface (body) lives on a SkillSection that the gate can check.
    forbidden = {"advice", "tip", "tips", "extra", "notes", "freeform", "summary"}
    assert not (forbidden & {f.lower() for f in AuthoredSkill.model_fields})
    # a section's assertable content is its body, and it always travels with its citations
    assert {"body", "citations"} <= set(SkillSection.model_fields)


def test_synthesis_path_cites_only_claims_the_layer_extracted(synthesis_plane):
    # End-to-end: every claim id a skill cites must exist in the Phase-4 claim store. The synthesizer
    # cannot reference evidence that was never extracted — the extract->synthesize boundary holds.
    pipeline, store, claim_store, _corpus = synthesis_plane
    pipeline.synthesize()
    extracted = {c.id for c in claim_store.list_claims()}
    for skill in store.list_skills():
        assert set(skill.claim_ids) <= extracted, f"{skill.slug} cites a non-extracted claim"
        assert skill.claim_ids  # and it is actually grounded
