"""Adapters — concrete implementations of the ports.

Two families, exactly as the testability law requires:

  * FAKE adapters (this module imports them eagerly; they need only numpy + the domain):
      - :class:`~nameless_workers.adapters.audio_loader_fake.InMemoryAudioLoader`
      - :class:`~nameless_workers.adapters.feature_fake.FakeFeatureExtractor`
      - :class:`~nameless_workers.adapters.embed_fake.FakeEmbedder`
      - :class:`~nameless_workers.adapters.repo_mem.InMemoryFragmentRepo`
      - :class:`~nameless_workers.adapters.job_source_mem.InMemoryJobSource`

      - ``feature_fake.FakeFeatureExtractor`` / ``embed_fake.FakeEmbedder`` (Phase 2)
      - Phase 7 reference fakes: ``reference_analyzer_fake.FakeReferenceAnalyzer``,
        ``vibe_describer_fake.FakeVibeDescriber``, ``genre_tagger.FakeGenreTagger``

  * REAL adapters (NOT imported here — importing them is cheap, but they import their heavy library
    lazily *inside methods* so the package still imports under the light base install):
      - ``feature_librosa.LibrosaFeatureExtractor``   (librosa + torchcrepe + pyloudnorm)
      - ``embed_clap.ClapEmbedder``                   (laion_clap)
      - ``audio_loader_store.FilesystemAudioLoader``  (content-addressed object store on disk)
      - ``repo_pg.PgFragmentRepo``                    (psycopg + pgvector)
      - Phase 7: ``reference_analyzer_clap.RestrictedReferenceAnalyzer`` (librosa + pyloudnorm +
        CLAP; NEVER chroma/f0), ``vibe_describer_claude.ClaudeVibeDescriber`` (anthropic),
        ``genre_tagger.ClapZeroShotGenreTagger`` (reuses the CLAP Embedder).
    Import these from their modules directly where the real plane is built (see ``cli.py``).
"""

from .audio_loader_fake import InMemoryAudioLoader
from .embed_fake import FakeEmbedder
from .feature_fake import FakeFeatureExtractor
from .genre_tagger import ClapZeroShotGenreTagger, FakeGenreTagger
from .job_source_mem import InMemoryJobSource
from .reference_analyzer_fake import FakeReferenceAnalyzer
from .repo_mem import InMemoryFragmentRepo
from .stem_separator_fake import FakeStemSeparator
from .stem_store_mem import InMemoryStemBlobStore, InMemoryStemRecordStore
from .track_loader_fake import InMemoryTrackLoader
from .vibe_describer_fake import FakeVibeDescriber

__all__ = [
    "InMemoryAudioLoader",
    "FakeEmbedder",
    "FakeFeatureExtractor",
    "InMemoryJobSource",
    "InMemoryFragmentRepo",
    # Phase 7 reference fakes
    "FakeReferenceAnalyzer",
    "FakeVibeDescriber",
    "FakeGenreTagger",
    "ClapZeroShotGenreTagger",
    # Phase 8 separation fakes
    "FakeStemSeparator",
    "InMemoryStemBlobStore",
    "InMemoryStemRecordStore",
    "InMemoryTrackLoader",
]
