"""Optional cloud LLM providers.

These are OPTIONAL integration points only — the application never requires them
(the default is local Ollama, per the free/open-source policy). They lazily
import their SDKs and raise a clear error unless explicitly configured, so the
project stays fully functional offline without any paid API.
"""
from __future__ import annotations

import time

from django.conf import settings

from .base import LLMError, LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return settings.OPENAI_MODEL

    def generate(self, prompt, *, system="", temperature=None, max_tokens=None, json=False, schema_hint=""):
        if not settings.OPENAI_API_KEY:
            raise LLMError("OpenAI provider requires OPENAI_API_KEY (optional; local Ollama is the default).",
                           retryable=False)
        try:
            from openai import OpenAI  # optional dependency
        except ImportError as exc:
            raise LLMError("The `openai` package is not installed.", retryable=False) from exc
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        started = time.perf_counter()
        resp = client.chat.completions.create(
            model=self.model_name,
            messages=([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
            temperature=settings.AI_TEMPERATURE if temperature is None else temperature,
            max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            response_format={"type": "json_object"} if json else None,
        )
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            model=self.model_name, provider=self.name,
            inference_ms=int((time.perf_counter() - started) * 1000), raw={},
        )


class ClaudeProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return settings.ANTHROPIC_MODEL

    def generate(self, prompt, *, system="", temperature=None, max_tokens=None, json=False, schema_hint=""):
        if not settings.ANTHROPIC_API_KEY:
            raise LLMError("Claude provider requires ANTHROPIC_API_KEY (optional; local Ollama is the default).",
                           retryable=False)
        try:
            import anthropic  # optional dependency
        except ImportError as exc:
            raise LLMError("The `anthropic` package is not installed.", retryable=False) from exc
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        started = time.perf_counter()
        msg = client.messages.create(
            model=self.model_name,
            system=system or None,
            max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            temperature=settings.AI_TEMPERATURE if temperature is None else temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return LLMResponse(
            text="".join(b.text for b in msg.content if getattr(b, "type", "") == "text"),
            model=self.model_name, provider=self.name,
            inference_ms=int((time.perf_counter() - started) * 1000), raw={},
        )
