"""Adapters — concrete implementations of the ports.

Two families, exactly as the testability law (and the Phase-2 ``workers/`` precedent) requires:

  * FAKE / stdlib-only adapters (imported EAGERLY here — they need only pydantic + stdlib):
      - :class:`~knowledge_pipeline.adapters.discovery_fake.FixtureDiscoverySource`
      - :class:`~knowledge_pipeline.adapters.fetch_fake.FixtureTranscriptFetcher`
      - :class:`~knowledge_pipeline.adapters.transcribe_fake.FixedTextTranscriber`
      - :class:`~knowledge_pipeline.adapters.corpus_mem.InMemoryCorpusStore`
      - :class:`~knowledge_pipeline.adapters.corpus_fs.FilesystemCorpusStore`  (REAL, but sqlite3 is stdlib
        ⇒ safe to import + test on the base env — the actual persistence path, not a fake)
      - :class:`~knowledge_pipeline.adapters.clock_real.SystemClock`
      - :class:`~knowledge_pipeline.adapters.clock_fake.FakeClock`
      - :class:`~knowledge_pipeline.adapters.rate_limiter.IntervalRateLimiter` / ``NoOpRateLimiter``

  * REAL network/ASR adapters (NOT imported here — they import their heavy/network library LAZILY inside
    methods, so the package still imports under the light base install):
      - ``discovery_ytdlp.YtDlpDiscoverySource``        (yt-dlp ytsearch)
      - ``fetch_youtube.YoutubeTranscriptFetcher``      (youtube-transcript-api + yt-dlp subs)
      - ``transcribe_whisper.FasterWhisperTranscriber`` (faster-whisper + yt-dlp audio)
    Import these from their modules directly where the live plane is built (see ``cli.py``).
"""

from .clock_fake import FakeClock
from .clock_real import SystemClock
from .corpus_fs import FilesystemCorpusStore
from .corpus_mem import InMemoryCorpusStore
from .discovery_fake import FixtureDiscoverySource
from .fetch_fake import FixtureTranscriptFetcher
from .rate_limiter import IntervalRateLimiter, NoOpRateLimiter
from .transcribe_fake import FixedTextTranscriber

__all__ = [
    "FixtureDiscoverySource",
    "FixtureTranscriptFetcher",
    "FixedTextTranscriber",
    "InMemoryCorpusStore",
    "FilesystemCorpusStore",
    "SystemClock",
    "FakeClock",
    "IntervalRateLimiter",
    "NoOpRateLimiter",
]
