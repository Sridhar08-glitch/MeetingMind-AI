"""Deterministic translation provider for tests/dev (no LLM, no network)."""
from __future__ import annotations

from .base import TranslationProvider, TranslationResult


class DummyTranslationProvider(TranslationProvider):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def model_name(self) -> str:
        return "dummy"

    def translate(
        self, texts: list[str], *, target_language: str, source_language: str | None = None
    ) -> TranslationResult:
        segments = [f"[{target_language}] {t}" if t else "" for t in texts]
        return TranslationResult(
            text=" ".join(s for s in segments if s).strip(),
            segments=segments,
            target_language=target_language,
            provider=self.name,
            confidence=0.99,
            ms=1,
        )

    def supported_languages(self) -> dict[str, str]:
        return {"en": "English", "es": "Spanish", "fr": "French", "ar": "Arabic", "hi": "Hindi"}
