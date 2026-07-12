"""Speaker diarization (Phase 15) — who spoke when, as a provider abstraction.

Off by default; token-free embedding engine is the default when enabled, pyannote
is opt-in. Voice embeddings are persisted now so Phase 15B cross-meeting identity
needs no reprocessing.
"""
from __future__ import annotations

from .base import DiarizationError, DiarizationProvider, DiarizationResult, assign_by_overlap
from .factory import diarization_enabled, get_diarization_provider

__all__ = [
    "DiarizationError",
    "DiarizationProvider",
    "DiarizationResult",
    "assign_by_overlap",
    "diarization_enabled",
    "get_diarization_provider",
]
