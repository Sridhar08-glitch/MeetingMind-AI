"""Diarization provider selection (config-driven, graceful fallback).

Off by default: if ``DIARIZATION_ENABLED`` is false the caller skips diarization
entirely (one unnamed speaker — today's behavior). When enabled, selects the
token-free ``embedding`` provider by default, ``pyannote`` opt-in, ``dummy`` for
tests — falling back to dummy if the chosen provider's deps are missing.
"""
from __future__ import annotations

import logging

from django.conf import settings

from .base import DiarizationProvider
from .dummy import DummyDiarizationProvider

logger = logging.getLogger("meetingmind.processing")


def diarization_enabled() -> bool:
    return bool(getattr(settings, "DIARIZATION_ENABLED", False))


def get_diarization_provider() -> DiarizationProvider:
    provider = (getattr(settings, "DIARIZATION_PROVIDER", "embedding") or "embedding").lower()

    if provider in {"dummy", "mock"}:
        return DummyDiarizationProvider()

    if provider == "pyannote":
        from .pyannote import PyannoteDiarizationProvider
        if PyannoteDiarizationProvider.available():
            return PyannoteDiarizationProvider()
        logger.warning("DIARIZATION_PROVIDER=pyannote but unavailable (deps/token); using dummy.")
        return DummyDiarizationProvider()

    # Default: token-free embedding + clustering.
    from .embedding import EmbeddingDiarizationProvider
    if EmbeddingDiarizationProvider.available():
        return EmbeddingDiarizationProvider()
    logger.warning("DIARIZATION_PROVIDER=embedding but deps missing; using dummy provider.")
    return DummyDiarizationProvider()
