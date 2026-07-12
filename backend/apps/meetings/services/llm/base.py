"""LLM provider interface + result types.

Business logic depends only on this interface (via ``LLMService``) and never on
which concrete provider is active — selection is config-only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(Exception):
    """An LLM provider/transport failure."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    inference_ms: int = 0
    raw: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        json: bool = False,
        schema_hint: str = "",
    ) -> LLMResponse:
        """Generate a completion. ``json=True`` requests strict JSON output.

        ``schema_hint`` is an opaque task label real providers may ignore; the
        dummy provider uses it to return appropriately-shaped test data.
        """

    def supported_languages(self) -> dict[str, str]:
        """Languages this model can reasonably generate output/translations in.

        Never a hardcoded app list — a stronger multilingual model can report its
        own set here. Defaults to empty (the caller then hides the selector or
        falls back to the STT set).
        """
        return {}
