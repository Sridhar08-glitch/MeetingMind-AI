"""Config-only LLM provider selection.

Default is the local ``OllamaProvider``. ``DummyLLMProvider`` is returned only
when ``AI_PROVIDER`` is ``dummy``/``mock`` (tests) — never as a silent fallback in
normal operation. If Ollama is unreachable at call time the provider raises an
``LLMError`` which the pipeline records as a structured ProcessingError.
"""
from __future__ import annotations

from django.conf import settings

from .base import LLMProvider
from .dummy import DummyLLMProvider
from .ollama import OllamaProvider


def get_llm_provider(*, model: str | None = None) -> LLMProvider:
    provider = (settings.AI_PROVIDER or "ollama").lower()
    if provider in {"dummy", "mock"}:
        return DummyLLMProvider()
    if provider == "openai":
        from .cloud import OpenAIProvider
        return OpenAIProvider()
    if provider == "claude":
        from .cloud import ClaudeProvider
        return ClaudeProvider()
    # Default: local Ollama.
    return OllamaProvider(model=model)
