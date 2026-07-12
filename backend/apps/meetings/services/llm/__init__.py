"""LLM provider abstraction (local-first)."""
from .base import LLMError, LLMProvider, LLMResponse
from .dummy import DummyLLMProvider
from .factory import get_llm_provider
from .ollama import OllamaProvider

__all__ = [
    "LLMProvider", "LLMResponse", "LLMError",
    "OllamaProvider", "DummyLLMProvider", "get_llm_provider",
]
