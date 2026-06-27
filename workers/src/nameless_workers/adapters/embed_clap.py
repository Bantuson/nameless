"""ClapEmbedder — the REAL :class:`~nameless_workers.ports.Embedder` (CAP-04), LAION-CLAP.

CLAP (Contrastive Language-Audio Pretraining) trains an audio tower and a text tower jointly so that a
clip and a sentence describing it land near each other in ONE shared 512-d space. That single property
is what the fragment graph needs (PRD §6): the same index answers "find audio like THIS audio"
(``--similar-to``) and "find audio that matches THIS note" (``--note "the chorus-like ideas"``).

We use the ``laion_clap`` package pinned at 1.1.7 with a MUSIC checkpoint (the ``larger_clap_music`` /
HTSAT-music family — pin the checkpoint, weights have drifted historically; STACK.md). Both towers are
L2-normalized on the way out so cosine == dot product and the worker writes unit vectors (matching the
cosine index in migration 0002).

WHY LAZY IMPORTS: ``laion_clap`` pulls in torch + transformers, which the 4GB build box cannot install
and which the test suite (using :class:`FakeEmbedder`) never needs. The import happens inside
:meth:`_ensure_model`, so importing this module is free. To swap to the HuggingFace ``transformers``
route (``ClapModel.from_pretrained("laion/larger_clap_music")``) just reimplement these two methods
behind the same port — nothing else changes.
"""

from __future__ import annotations

import numpy as np

from .. import CLAP_DIM
from ..domain.models import Embedding
from ..pure.vectors import l2_normalize

# Default music checkpoint for laion_clap. Pinned + overridable; see __init__.
DEFAULT_CLAP_CHECKPOINT = "music_audioset_epoch_15_esc_90.pt"
DEFAULT_AUDIO_MODEL = "HTSAT-base"
MODEL_NAME = "laion_clap:larger_clap_music"
CLAP_INPUT_SR = 48_000  # laion_clap expects 48 kHz audio


class ClapEmbedder:
    """Real CLAP embeddings for audio and note text, in one joint 512-d space."""

    def __init__(
        self,
        *,
        checkpoint: str | None = DEFAULT_CLAP_CHECKPOINT,
        amodel: str = DEFAULT_AUDIO_MODEL,
        enable_fusion: bool = False,
        device: str = "cpu",
    ) -> None:
        self._checkpoint = checkpoint
        self._amodel = amodel
        self._enable_fusion = enable_fusion
        self._device = device
        self._model = None  # loaded lazily

    def _ensure_model(self):
        if self._model is None:
            import laion_clap  # lazy: torch + transformers backend

            model = laion_clap.CLAP_Module(enable_fusion=self._enable_fusion, amodel=self._amodel)
            # load_ckpt(None) downloads the package default; a path/name pins a specific checkpoint.
            if self._checkpoint:
                model.load_ckpt(self._checkpoint)
            else:
                model.load_ckpt()
            self._model = model
        return self._model

    def embed_audio(self, audio: bytes) -> Embedding:
        import librosa  # lazy (decode + resample to 48 kHz mono)
        import soundfile as sf  # lazy
        import io

        model = self._ensure_model()
        try:
            y, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
        except Exception:
            import os
            import tempfile

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                    tmp.write(audio)
                    tmp_path = tmp.name
                y, sr = librosa.load(tmp_path, sr=None, mono=True)
            finally:
                if tmp_path is not None:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        y = np.asarray(y, dtype=np.float32)
        if y.ndim == 2:
            y = y.mean(axis=1)
        if sr != CLAP_INPUT_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=CLAP_INPUT_SR)

        # laion_clap wants a (batch, samples) float32 array.
        emb = model.get_audio_embedding_from_data(x=y[np.newaxis, :], use_tensor=False)
        vec = l2_normalize(np.asarray(emb, dtype=np.float64).reshape(-1))
        return Embedding(model_name=MODEL_NAME, dim=int(vec.shape[0]), vector=vec.tolist())

    def embed_text(self, text: str) -> Embedding:
        model = self._ensure_model()
        # get_text_embedding takes a list; some versions need ≥2 items — pad with "" and keep row 0.
        emb = model.get_text_embedding([text, ""], use_tensor=False)
        vec = l2_normalize(np.asarray(emb, dtype=np.float64)[0].reshape(-1))
        return Embedding(model_name=MODEL_NAME, dim=int(vec.shape[0]), vector=vec.tolist())

    @property
    def expected_dim(self) -> int:
        """The joint-space dimension this embedder targets (512 for the music CLAP family)."""
        return CLAP_DIM
