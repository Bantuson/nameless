"""The no-synthesis boundary, as a TESTED invariant — the defining discipline of Phase 4 (KNOW-05/06).

Phase 4 extracts and groups; it must NOT synthesize (no opinionated default, no merged "best way", no
SKILL.md — that is Phase 5). These tests pin that boundary so a future change that crosses it fails CI.
They also prove the heavy/external leaves (anthropic, sentence-transformers) are NEVER imported on the
fakes-only path — the whole suite runs on the base env.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import knowledge_pipeline
from knowledge_pipeline.adapters import FakeClaimExtractor
from knowledge_pipeline.domain.claims import Claim, ClaimCluster
from knowledge_pipeline.domain.models import CaptionSource, RawTranscript, TranscriptSegment
from knowledge_pipeline.pure.cross_reference import cross_reference

_SRC_DIR = str(Path(knowledge_pipeline.__file__).resolve().parents[1])  # the `src` dir on sys.path


def test_anthropic_and_embeddings_are_not_imported_on_the_fake_path():
    # Importing the package + using the fakes must not pull the env-gated heavy leaves (anthropic,
    # sentence_transformers) into the process. Run in a CLEAN subprocess so the assertion is isolated
    # from anything other tests / plugins may have loaded into this shared pytest process.
    probe = (
        "import sys\n"
        "import knowledge_pipeline.claims_cli, knowledge_pipeline.mining_pipeline\n"
        "from knowledge_pipeline.adapters import FakeClaimExtractor, InMemoryClaimStore, KeywordSimilarityIndex\n"
        "assert 'anthropic' not in sys.modules, 'anthropic leaked into the fake path'\n"
        "assert 'sentence_transformers' not in sys.modules, 'sentence_transformers leaked into the fake path'\n"
        "print('clean')\n"
    )
    env = dict(os.environ, PYTHONPATH=_SRC_DIR)
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_schema_carries_no_synthesized_fields():
    # Claim is extraction+citation only; ClaimCluster preserves evidence and never holds a chosen default.
    claim_fields = set(Claim.model_fields.keys())
    cluster_fields = set(ClaimCluster.model_fields.keys())
    forbidden = {"default", "recommended", "recommendation", "best_way", "best", "summary",
                 "synthesis", "synthesized", "verdict", "winner", "chosen"}
    assert not (forbidden & {f.lower() for f in claim_fields})
    assert not (forbidden & {f.lower() for f in cluster_fields})
    # the cluster keeps BOTH evidence lists as first-class data
    assert {"consensus", "conflicts"} <= cluster_fields


def test_cross_reference_never_collapses_a_conflict():
    from .conftest import make_claim

    claims = [
        make_claim(video="a", technique="log-drum-source", stage="drums", stance="flex-synth"),
        make_claim(video="b", technique="log-drum-source", stage="drums", stance="layered-samples"),
    ]
    cl = cross_reference(claims)[0]
    # the disagreement is preserved as data, never averaged into one "answer".
    assert cl.is_contested and len(cl.conflicts) == 2 and cl.consensus == []


def test_fake_extractor_emits_only_grounded_atoms_never_a_cluster():
    transcript = RawTranscript(
        video_id="v",
        caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=5.0, duration_s=5.0, text="Sidechain the bass to the kick.")],
    )
    out = FakeClaimExtractor().extract(transcript)
    assert all(isinstance(c, Claim) for c in out)             # atoms only — no ClaimCluster, no default
    seg_texts = {s.text for s in transcript.segments}
    assert all(c.quote in seg_texts for c in out)             # grounded: quotes are verbatim, not invented
