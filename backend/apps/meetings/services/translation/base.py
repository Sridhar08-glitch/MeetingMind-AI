"""Translation provider interface + result type.

Translation is a first-class, config-selected provider exactly like STT and LLM —
business logic depends only on this interface, never on Ollama specifically. The
original transcript is always kept; a translation is a *separate* artifact.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationResult:
    #: Full translated text (segments joined).
    text: str
    #: Per-segment translated text, 1:1 with the input segment list.
    segments: list[str] = field(default_factory=list)
    target_language: str = ""
    provider: str = ""
    confidence: float | None = None
    ms: int = 0


class TranslationProvider(ABC):
    """Translate transcript segments into a target language (100% local)."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def translate(
        self, texts: list[str], *, target_language: str, source_language: str | None = None
    ) -> TranslationResult:
        """Translate each segment text into ``target_language`` (aligned 1:1)."""

    def supported_languages(self) -> dict[str, str]:
        """Target languages this provider can translate INTO (code → name).

        Never a hardcoded app list — reported by the provider so the UI adapts.
        """
        return {}
