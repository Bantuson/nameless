"""Genre taggers — CLAP zero-shot ranking logic (via FakeEmbedder) + the deterministic fake."""

from __future__ import annotations

from nameless_workers.adapters.embed_fake import FakeEmbedder
from nameless_workers.adapters.genre_tagger import (
    ClapZeroShotGenreTagger,
    FakeGenreTagger,
)

GENRES = ["amapiano", "deep house", "r&b", "jazz"]


def test_zero_shot_ranks_the_matching_genre_first():
    embedder = FakeEmbedder()
    tagger = ClapZeroShotGenreTagger(embedder, genres=GENRES)
    # Build an audio embedding IDENTICAL to the text embedding of one genre's prompt — so its cosine
    # similarity is 1.0 and it must rank first. This exercises the real ranking math with no CLAP.
    target = "deep house"
    audio = embedder.embed_text(tagger.prompt(target))
    result = tagger.tag(audio)
    assert result.top == target
    # Scores are sorted descending and the winner is (near) 1.0.
    assert result.scores[0][0] == target
    assert result.scores[0][1] >= result.scores[1][1]
    assert result.scores[0][1] > 0.99


def test_zero_shot_margin_can_withhold_a_shaky_tag():
    embedder = FakeEmbedder()
    # A large required margin means no candidate is "confidently ahead" → top=None (coarse honesty).
    tagger = ClapZeroShotGenreTagger(embedder, genres=GENRES, min_margin=2.0)
    audio = embedder.embed_audio(b"some track")
    result = tagger.tag(audio)
    assert result.top is None
    # ...but the ranking is still reported for inspection.
    assert len(result.scores) == len(GENRES)


def test_zero_shot_caches_prompt_embeddings_and_is_deterministic():
    embedder = FakeEmbedder()
    tagger = ClapZeroShotGenreTagger(embedder, genres=GENRES)
    audio = embedder.embed_audio(b"track")
    first = tagger.tag(audio)
    second = tagger.tag(audio)
    assert first.top == second.top
    assert first.scores == second.scores


def test_fake_genre_tagger_is_deterministic_and_picks_a_known_genre():
    embedder = FakeEmbedder()
    tagger = FakeGenreTagger(genres=GENRES)
    audio = embedder.embed_audio(b"deterministic bytes")
    a = tagger.tag(audio)
    b = tagger.tag(audio)
    assert a.top in GENRES
    assert a.top == b.top  # same embedding → same tag
    # The chosen genre leads the score ranking.
    assert a.scores[0][0] == a.top


def test_fake_genre_tagger_empty_vocabulary_yields_no_tag():
    tagger = FakeGenreTagger(genres=[])
    audio = FakeEmbedder().embed_audio(b"x")
    result = tagger.tag(audio)
    assert result.top is None
    assert result.scores == []
