"""PyannoteDiarizationProvider — opt-in, highest accuracy (needs HF token).

Uses pyannote.audio's pretrained speaker-diarization pipeline (requires a free
HuggingFace token to download the gated model, accepted once). Turns are aligned
to transcript segments by overlap; per-speaker mean embeddings are computed with
the same local encoder as the token-free provider so Phase 15B stays compatible.
"""
from __future__ import annotations

import logging

from django.conf import settings

from .base import DiarizationError, DiarizationProvider, DiarizationResult, assign_by_overlap

logger = logging.getLogger("meetingmind.processing")

_PIPELINE = None


class PyannoteDiarizationProvider(DiarizationProvider):
    @property
    def name(self) -> str:
        return "pyannote"

    @property
    def model_name(self) -> str:
        return getattr(settings, "DIARIZATION_PYANNOTE_MODEL", "pyannote/speaker-diarization-3.1")

    @classmethod
    def available(cls) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401
            return bool(getattr(settings, "HUGGINGFACE_TOKEN", ""))
        except Exception:  # noqa: BLE001
            return False

    def _pipeline(self):
        global _PIPELINE
        if _PIPELINE is None:
            from pyannote.audio import Pipeline

            token = getattr(settings, "HUGGINGFACE_TOKEN", "")
            _PIPELINE = Pipeline.from_pretrained(self.model_name, use_auth_token=token)
        return _PIPELINE

    def diarize(self, audio_path, *, segments, duration=None) -> DiarizationResult:
        if not segments:
            return DiarizationResult(segment_labels=[], provider=self.name, model=self.model_name)
        try:
            annotation = self._pipeline()(audio_path)
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(f"pyannote diarization failed: {exc}") from exc

        turns = [(turn.start, turn.end, str(label))
                 for turn, _, label in annotation.itertracks(yield_label=True)]
        labels = assign_by_overlap(turns, segments)

        # Mean + per-segment embeddings via the shared local encoder (best-effort;
        # keeps 15B ready). Per-segment vectors become SpeakerEmbedding rows.
        embeddings: dict[str, list[float]] = {}
        segment_embeddings: list[list[float]] = []
        try:
            from .embedding import EmbeddingDiarizationProvider

            if EmbeddingDiarizationProvider.available():
                segment_embeddings = EmbeddingDiarizationProvider().embed_segments(audio_path, segments)
                embeddings = _mean_by_label(segment_embeddings, labels)
        except Exception:  # noqa: BLE001
            logger.debug("pyannote embedding computation skipped", exc_info=True)

        return DiarizationResult(
            segment_labels=labels, embeddings=embeddings,
            segment_embeddings=segment_embeddings,
            provider=self.name, model=self.model_name,
        )


def _mean_by_label(vectors, labels) -> dict[str, list[float]]:
    import numpy as np

    arr = np.array(vectors)
    out: dict[str, list[float]] = {}
    for label in set(labels):
        idx = [i for i, l in enumerate(labels) if l == label]
        if not idx:
            continue
        mean = arr[idx].mean(axis=0)
        out[label] = (mean / (np.linalg.norm(mean) + 1e-9)).tolist()
    return out
