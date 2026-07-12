"""Config-only translation provider selection (mirrors STT/LLM factories)."""
from __future__ import annotations

from django.conf import settings

from .base import TranslationProvider
from .dummy import DummyTranslationProvider


def get_translation_provider(*, model: str | None = None) -> TranslationProvider:
    provider = (getattr(settings, "TRANSLATION_PROVIDER", "ollama") or "ollama").lower()
    if provider in {"dummy", "mock"}:
        return DummyTranslationProvider()
    # Default: local LLM-backed translation (Ollama).
    from .ollama import OllamaTranslationProvider

    return OllamaTranslationProvider(model=model)
