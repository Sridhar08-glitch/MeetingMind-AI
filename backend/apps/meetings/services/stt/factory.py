"""Config-only provider selection with graceful fallback.

``STT_PROVIDER`` chooses the provider. ``faster_whisper`` uses the real local
model when the library is installed; if it isn't, we log and fall back to the
dummy provider so development stays functional (Phase 6 requirement #4). Any
other value (``mock``/``dummy``) uses the dummy provider. Optional cloud
providers can be added here without touching business logic.
"""
from __future__ import annotations

import logging

from django.conf import settings

from .base import SpeechToTextProvider
from .dummy import DummySpeechProvider

logger = logging.getLogger("meetingmind.processing")


def get_speech_provider(*, model: str | None = None) -> SpeechToTextProvider:
    provider = (settings.STT_PROVIDER or "mock").lower()

    if provider == "faster_whisper":
        try:
            import faster_whisper  # noqa: F401 — availability probe

            from .faster_whisper import FasterWhisperProvider

            return FasterWhisperProvider(model_size=model)
        except ImportError:
            logger.warning(
                "STT_PROVIDER=faster_whisper but faster-whisper is not installed; "
                "falling back to DummySpeechProvider. See docs/STT_ACTIVATION.md."
            )

    return DummySpeechProvider()
