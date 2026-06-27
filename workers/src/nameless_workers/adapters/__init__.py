"""Adapters — concrete implementations of the ports.

Two families, exactly as the testability law requires:

  * FAKE adapters (this module imports them eagerly; they need only numpy + the domain):
      - :class:`~nameless_workers.adapters.audio_loader_fake.InMemoryAudioLoader`
      - :class:`~nameless_workers.adapters.feature_fake.FakeFeatureExtractor`
      - :class:`~nameless_workers.adapters.embed_fake.FakeEmbedder`
      - :class:`~nameless_workers.adapters.repo_mem.InMemoryFragmentRepo`
      - :class:`~nameless_workers.adapters.job_source_mem.InMemoryJobSource`

  * REAL adapters (NOT imported here — importing them is cheap, but they import their heavy library
    lazily *inside methods* so the package still imports under the light base install):
      - ``feature_librosa.LibrosaFeatureExtractor``   (librosa + torchcrepe + pyloudnorm)
      - ``embed_clap.ClapEmbedder``                   (laion_clap)
      - ``audio_loader_store.FilesystemAudioLoader``  (content-addressed object store on disk)
      - ``repo_pg.PgFragmentRepo``                    (psycopg + pgvector)
    Import these from their modules directly where the real plane is built (see ``cli.py``).
"""

from .audio_loader_fake import InMemoryAudioLoader
from .embed_fake import FakeEmbedder
from .feature_fake import FakeFeatureExtractor
from .job_source_mem import InMemoryJobSource
from .repo_mem import InMemoryFragmentRepo

__all__ = [
    "InMemoryAudioLoader",
    "FakeEmbedder",
    "FakeFeatureExtractor",
    "InMemoryJobSource",
    "InMemoryFragmentRepo",
]
