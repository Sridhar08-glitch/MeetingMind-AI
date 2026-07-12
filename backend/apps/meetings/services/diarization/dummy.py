"""DummyDiarizationProvider — deterministic, no-torch, no-network (tests).

Splits segments into a fixed number of speakers in contiguous blocks and returns
stable fake embeddings, so the whole diarization → Speaker-entity path can be
exercised without heavy dependencies.
"""
from __future__ import annotations

from django.conf import settings

from .base import DiarizationProvider, DiarizationResult


class DummyDiarizationProvider(DiarizationProvider):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def model_name(self) -> str:
        return "dummy"

    def diarize(self, audio_path, *, segments, duration=None) -> DiarizationResult:
        n = len(segments)
        if n == 0:
            return DiarizationResult(segment_labels=[], provider=self.name, model=self.model_name)
        want = int(getattr(settings, "DIARIZATION_DUMMY_SPEAKERS", 2))
        want = max(1, min(want, n))
        # Contiguous blocks: seg i → SPEAKER_{ i * want // n }.
        labels = [f"SPEAKER_{(i * want) // n:02d}" for i in range(n)]
        # Stable, distinct fake embeddings per label.
        embeddings: dict[str, list[float]] = {}
        for label in set(labels):
            seed = int(label.split("_")[1])
            vec = [((seed + j) % 7) / 7.0 for j in range(16)]
            embeddings[label] = vec
        # Per-segment embeddings mirror the label vector (deterministic for tests).
        segment_embeddings = [embeddings[label] for label in labels]
        return DiarizationResult(
            segment_labels=labels, embeddings=embeddings,
            segment_embeddings=segment_embeddings,
            provider=self.name, model=self.model_name,
        )
