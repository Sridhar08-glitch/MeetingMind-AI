"""Deterministic development/testing STT provider.

Produces a stable, offline transcript with no external dependencies (no ffmpeg,
no Faster-Whisper, no model download), so the whole application — APIs, editing,
search, downloads, tests — stays fully functional in development. Output depends
only on the audio duration, so tests are deterministic.
"""
from __future__ import annotations

from .base import STTResult, STTSegment, SpeechToTextProvider

# A fixed pool of plausible meeting sentences (no randomness → deterministic).
_SENTENCES = [
    "Thanks everyone for joining the call today.",
    "Let's start by reviewing the action items from last week.",
    "The migration to the new platform is on track for the end of the month.",
    "We should double-check the budget numbers before the board meeting.",
    "I'll follow up with the design team about the updated mockups.",
    "Can we confirm the deadline for the first release candidate?",
    "The customer feedback has been overwhelmingly positive so far.",
    "Let's make sure the documentation is ready before we ship.",
    "I think we can close out three of the open risks this sprint.",
    "Great, let's reconvene next Thursday to check on progress.",
]


class DummySpeechProvider(SpeechToTextProvider):
    requires_audio = False

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def model_name(self) -> str:
        return "dummy"

    def transcribe(
        self,
        audio_path: str | None,
        *,
        language: str | None = None,
        duration: float | None = None,
        task: str = "transcribe",
    ) -> STTResult:
        total = float(duration or 60.0)
        # ~1 segment per 10s of audio, clamped to a sensible range.
        count = max(3, min(len(_SENTENCES), int(total // 10) or 3))
        span = total / count
        segments: list[STTSegment] = []
        for i in range(count):
            start = round(i * span, 2)
            end = round(min(total, (i + 1) * span), 2)
            segments.append(STTSegment(
                start=start, end=end,
                text=_SENTENCES[i % len(_SENTENCES)],
                confidence=0.95,
            ))
        return STTResult(
            segments=segments,
            language=(language or "en"),
            language_confidence=0.99,
            model=self.model_name,
            provider=self.name,
            duration=total,
        )

    def supported_languages(self) -> dict[str, str]:
        return {"en": "English", "es": "Spanish", "fr": "French", "ar": "Arabic", "hi": "Hindi"}
