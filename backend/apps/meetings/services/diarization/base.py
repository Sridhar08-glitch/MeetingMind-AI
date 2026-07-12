"""DiarizationProvider abstraction — "who spoke when" over transcript segments.

A provider is given the normalized audio + the transcript segment spans, and
returns a speaker label per segment plus a mean voice embedding per label. The
embeddings are persisted now (Phase 15) so cross-meeting recognition (Phase 15B)
needs no reprocessing. Mirrors the STT/LLM/Translation provider pattern.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DiarizationResult:
    # One speaker label per input segment (aligned by index), e.g. "SPEAKER_00".
    segment_labels: list[str]
    # Mean L2-normalized voice embedding per label (may be empty if unavailable).
    embeddings: dict[str, list[float]] = field(default_factory=dict)
    # One L2-normalized embedding per input segment (aligned by index). Persisted
    # now (Phase 15) as SpeakerEmbedding rows so 15B never re-embeds audio. May be
    # empty when the provider cannot produce per-segment vectors.
    segment_embeddings: list[list[float]] = field(default_factory=list)
    provider: str = ""
    model: str = ""

    @property
    def num_speakers(self) -> int:
        return len({label for label in self.segment_labels if label})


class DiarizationError(Exception):
    """Diarization could not be performed (missing dep, bad audio, etc.)."""


class DiarizationProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def diarize(
        self,
        audio_path: str,
        *,
        segments: list[tuple[float, float]],
        duration: float | None = None,
    ) -> DiarizationResult:
        """Return a speaker label per input segment + a mean embedding per label."""

    @classmethod
    def available(cls) -> bool:
        """Whether this provider's optional dependencies are importable."""
        return True


def assign_by_overlap(
    turns: list[tuple[float, float, str]], segments: list[tuple[float, float]]
) -> list[str]:
    """Assign each segment the speaker whose turns overlap it most (for turn-based
    providers like pyannote). Ties/no-overlap fall back to the nearest turn."""
    labels: list[str] = []
    for seg_start, seg_end in segments:
        best_label, best_overlap = "", 0.0
        nearest_label, nearest_gap = "", float("inf")
        for t_start, t_end, label in turns:
            overlap = min(seg_end, t_end) - max(seg_start, t_start)
            if overlap > best_overlap:
                best_overlap, best_label = overlap, label
            gap = min(abs(seg_start - t_end), abs(t_start - seg_end))
            if gap < nearest_gap:
                nearest_gap, nearest_label = gap, label
        labels.append(best_label or nearest_label)
    return labels
