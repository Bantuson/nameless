"""FasterWhisperTranscriber — the REAL ASR :class:`~knowledge_pipeline.ports.Transcriber`.

The honest fallback (STACK.md / PITFALLS #1): many producer tutorials have only auto-captions or none,
and target-genre speech is code-switched (English + isiZulu/Sesotho/Afrikaans). YouTube auto-captions
mangle producer jargon ("log drum", "Serato", "300 Hz"); faster-whisper (``large-v3``) recovers real
punctuation, timestamps, and jargon far better — at GPU cost, which is why this runs ONLY on the fallback
path the pure :func:`fallback_decision` selected.

Two lazy steps, both env-gated (the 4GB box runs neither — the suite uses :class:`FixedTextTranscriber`):
  1. ``yt-dlp`` pulls the bestaudio stream to a temp file (audio only; no video).
  2. ``faster_whisper.WhisperModel`` transcribes it to timestamped segments.

faster-whisper is CTranslate2-based: ``int8`` on CPU, ``float16`` on GPU (CUDA 12 + cuDNN 9). We default
to CPU/int8 so a CPU-only worker still functions (slowly); pass ``device="cuda"`` for the GPU worker.
"""

from __future__ import annotations

import logging
import os
import tempfile

from ..domain.models import CaptionSource, RawTranscript, TranscriptSegment, VideoRef

logger = logging.getLogger("knowledge_pipeline.transcribe_whisper")


class FasterWhisperTranscriber:
    """Real ASR fallback: yt-dlp pulls audio, faster-whisper (large-v3) transcribes it."""

    def __init__(
        self,
        *,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,  # None ⇒ let Whisper detect (handles code-switching gracefully)
        beam_size: int = 5,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._model = None  # loaded lazily on first transcribe (it is large)

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # lazy (env-gated, heavy)

            logger.info(
                "loading faster-whisper %s on %s (%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def transcribe(self, video: VideoRef) -> RawTranscript:
        audio_path = self._download_audio(video.video_id)
        try:
            model = self._ensure_model()
            segments_iter, info = model.transcribe(
                audio_path,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=True,  # drop non-speech (music beds) so the transcript is speech, not lyrics
            )
            language = getattr(info, "language", None) or self._language or "en"
            segments: list[TranscriptSegment] = []
            for seg in segments_iter:
                text = (seg.text or "").strip()
                if not text:
                    continue
                start = float(seg.start)
                end = float(seg.end)
                segments.append(
                    TranscriptSegment(
                        start_s=start,
                        duration_s=max(0.0, round(end - start, 3)),
                        text=text,
                    )
                )
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

        return RawTranscript(
            video_id=video.video_id,
            caption_source=CaptionSource.ASR,
            language=language,
            fetched_via=f"faster-whisper-{self._model_size}",
            segments=segments,
        )

    @staticmethod
    def _download_audio(video_id: str) -> str:
        """Pull bestaudio to a temp file via yt-dlp; return the path. Caller deletes it."""
        from yt_dlp import YoutubeDL  # lazy

        tmpdir = tempfile.mkdtemp(prefix="nameless-asr-")
        outtmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}
            ],
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        wav_path = os.path.join(tmpdir, f"{video_id}.wav")
        if not os.path.exists(wav_path):
            # ffmpeg may have produced a different container; pick the single file in the dir.
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
            if not files:
                raise FileNotFoundError(f"yt-dlp produced no audio for {video_id}")
            wav_path = files[0]
        return wav_path
