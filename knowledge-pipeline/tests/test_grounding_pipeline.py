"""GroundingPipeline — end-to-end decompose -> parents -> audio -> synthesize -> GATE -> emit (KNOW-10).

Proves the full Phase-6 flow on fakes/fixtures: alt-piano is authored as a LOW-confidence, grounded draft
behind the SAME hard citation gate; the default rests on measured audio yet is STILL low (the honesty
invariant); the reused parent conflict survives; and a synthesizer that asserts an audio number absent from
the records is REJECTED — the audio gets no special pass.
"""

from __future__ import annotations

from knowledge_pipeline.adapters import FakeTrackAnalyzer, InMemorySkillStore
from knowledge_pipeline.domain.skills import SkillStatus
from knowledge_pipeline.grounding_pipeline import GroundingPipeline
from knowledge_pipeline.pure.cross_reference import cross_reference
from knowledge_pipeline.pure.decompose import ALT_PIANO_TARGET
from knowledge_pipeline.pure.synthesis_template import template_synthesize

from .conftest import FIXED_NOW, mine_grounding_parent_layer


def test_grounds_alt_piano_as_a_low_confidence_grounded_draft(grounding_plane):
    pipeline, store, _claims, _fx = grounding_plane
    outcome = pipeline.ground()
    assert outcome.status == "authored"
    assert outcome.confidence == "LOW"
    assert outcome.target == ALT_PIANO_TARGET.slug

    skill = store.get_skill(outcome.skill_id)
    assert skill is not None
    assert skill.grounded is True
    assert skill.status is SkillStatus.DRAFT
    assert skill.confidence_tier == "LOW"
    assert skill.relpath == "skills/production/composite/alternative-piano/SKILL.md"


def test_default_rests_on_measured_audio_but_is_still_low_by_construction(grounding_plane):
    # The KNOW-10 point: the default is corroborated by 3 real tracks (would be HIGH for a normal skill),
    # yet a grounded skill is LOW — thin, indirect evidence is never dressed as settled craft.
    pipeline, store, _claims, _fx = grounding_plane
    outcome = pipeline.ground()
    skill = store.get_skill(outcome.skill_id)
    assert skill.default_source_count >= 3
    assert skill.confidence_tier == "LOW"
    assert outcome.tutorial_sources == 0   # no DIRECT alt-piano tutorials — that is the whole phase


def test_skill_cites_both_tutorial_and_audio_evidence(grounding_plane):
    pipeline, store, _claims, _fx = grounding_plane
    outcome = pipeline.ground()
    skill = store.get_skill(outcome.skill_id)
    body = skill.body_md
    # audio records (the analyzed tracks) AND tutorial videos (the parents) both appear as citations
    assert "audio:ben-produces-emoyeni" in body
    assert "jazzy_piano_tut" in body or "amapiano_groove_tut" in body or "deephouse_space_tut" in body
    # mixed evidence is clearly framed
    assert "NOT direct tutorials" in body
    assert "## Grounding" in body


def test_reused_parent_conflict_survives_into_the_grounded_skill(grounding_plane):
    # The bundled amapiano log-drum FLEX-vs-layered conflict is reused as parent evidence and preserved.
    pipeline, store, _claims, _fx = grounding_plane
    outcome = pipeline.ground()
    body = store.get_skill(outcome.skill_id).body_md
    assert "[flex-synth]" in body and "[layered-samples]" in body


def test_grounding_passes_the_same_gate_with_no_rejections(grounding_plane):
    pipeline, _store, _claims, _fx = grounding_plane
    outcome = pipeline.ground()
    assert outcome.status == "authored"
    assert outcome.reasons == []


def test_regrounding_is_idempotent(grounding_plane):
    pipeline, store, _claims, _fx = grounding_plane
    pipeline.ground()
    n1 = store.stats().total_skills
    pipeline.ground()
    assert store.stats().total_skills == n1  # upsert by cell id, no duplicate


def test_a_synthesizer_that_asserts_an_unmeasured_audio_number_is_rejected():
    # Wire a MALICIOUS synthesizer that injects a tempo the records never measured. The gate must REJECT it
    # exactly like a fabricated tutorial number — audio evidence gets no special pass.
    claim_store, corpus, fx = mine_grounding_parent_layer()

    class InventingSynth:
        def synthesize(self, cell, cluster_seq):
            draft = template_synthesize(cell, list(cluster_seq))
            poisoned = draft.default.model_copy(
                update={"body": draft.default.body + " The measured tempo is actually 200 bpm."}
            )
            return draft.model_copy(update={"default": poisoned})

    store = InMemorySkillStore()
    pipeline = GroundingPipeline(
        InventingSynth(), store, claim_store, FakeTrackAnalyzer(fx.records), fx.tracks,
        corpus=corpus, now=lambda: FIXED_NOW,
    )
    outcome = pipeline.ground()
    assert outcome.status == "rejected"
    assert any("invented_number" in r for r in outcome.reasons)
    assert store.stats().total_skills == 0  # nothing untraceable shipped


def test_audio_claims_corroborate_across_tracks(grounding_plane):
    # PITFALLS #5: a signature from MANY tracks where features converge is signal, not noise.
    _pipeline, _store, _claims, fx = grounding_plane
    from knowledge_pipeline.pure.audio_claims import audio_derived_claims

    audio_claims = [
        adc.to_claim() for rec in fx.records.values() for adc in audio_derived_claims(rec)
    ]
    clusters = {c.topic: c for c in cross_reference(audio_claims)}
    tempo = clusters["drums/groove-tempo"]
    # the 3 tracks corroborate the tempo band as one consensus cluster (3 distinct audio sources)
    assert tempo.distinct_consensus_sources == 3
    assert not tempo.is_contested


def test_analyzer_was_called_for_every_track(grounding_plane):
    pipeline, _store, _claims, fx = grounding_plane
    pipeline.ground()
    analyzer = pipeline._analyzer
    assert set(analyzer.calls) == {t.track_id for t in fx.tracks}


def test_no_decomposition_target_is_a_hard_failure(grounding_plane):
    import pytest

    from knowledge_pipeline.domain.skills import ProductionCell

    pipeline, _store, _claims, _fx = grounding_plane
    with pytest.raises(KeyError):
        pipeline.ground(ProductionCell(stage="drums", genre="gqom"))
