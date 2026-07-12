"""Speech-to-Text provider interface + result types.

Business logic depends only on this interface (via ``SpeechToTextService``) and
never on which concrete provider is active — provider selection is config-only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class STTWord:
    start: float
    end: float
    word: str
    probability: float | None = None


@dataclass
class STTSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None
    words: list[STTWord] = field(default_factory=list)


@dataclass
class STTResult:
    segments: list[STTSegment]
    language: str
    language_confidence: float | None
    model: str
    provider: str
    duration: float | None = None


class SpeechToTextProvider(ABC):
    """Interface implemented by every STT backend (local or optional cloud)."""

    #: Whether this provider needs real decoded audio (drives the ffmpeg path).
    #: The dummy provider does not, so development works without ffmpeg.
    requires_audio: bool = True
    #: Whether the provider can auto-detect the spoken language.
    supports_auto_detect: bool = True

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def transcribe(
        self,
        audio_path: str | None,
        *,
        language: str | None = None,
        duration: float | None = None,
        task: str = "transcribe",
    ) -> STTResult:
        """Transcribe audio. ``task`` is "transcribe" (native language) or
        "translate" (Whisper's speech→English mode)."""
        ...

    def supported_languages(self) -> dict[str, str]:
        """Map of ISO code → display name the provider can transcribe.

        The app NEVER hardcodes a language list — the UI populates itself from
        whatever the active provider reports here.
        """
        return {}
