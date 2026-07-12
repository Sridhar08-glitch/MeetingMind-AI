"""Local Ollama LLM provider (default) — free, offline, no paid API.

Talks to a locally-running Ollama server over HTTP. Uses stdlib ``urllib`` so no
extra dependency is required. ``json=True`` sets Ollama's ``format=json`` for
strict JSON output.
"""
from __future__ import annotations

import json as jsonlib
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings

from .base import LLMError, LLMProvider, LLMResponse

logger = logging.getLogger("meetingmind.ai")


class OllamaProvider(LLMProvider):
    def __init__(self, *, base_url: str | None = None, model: str | None = None):
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self, prompt, *, system="", temperature=None, max_tokens=None, json=False, schema_hint="",
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": prompt}]
            ),
            "stream": False,
            "options": {
                "temperature": settings.AI_TEMPERATURE if temperature is None else temperature,
                "num_predict": max_tokens or settings.AI_MAX_TOKENS,
            },
        }
        if json:
            payload["format"] = "json"

        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=jsonlib.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=settings.AI_REQUEST_TIMEOUT) as resp:
                data = jsonlib.loads(resp.read().decode())
        except urllib.error.URLError as exc:
            raise LLMError(f"Ollama request failed: {exc}", retryable=True) from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Ollama error: {exc}", retryable=True) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        text = (data.get("message", {}) or {}).get("content", "")
        return LLMResponse(text=text, model=self._model, provider=self.name,
                           inference_ms=elapsed_ms, raw=data)

    def supported_languages(self) -> dict[str, str]:
        # Local LLMs can attempt output in many languages (quality varies by
        # model). Default to the broad Whisper set; a deployment can narrow it via
        # settings.AI_SUPPORTED_LANGUAGES without any code change.
        from apps.meetings.services.stt.languages import WHISPER_LANGUAGE_NAMES

        allow = getattr(settings, "AI_SUPPORTED_LANGUAGES", None)
        if allow:
            return {c: WHISPER_LANGUAGE_NAMES.get(c, c.upper()) for c in allow}
        return dict(WHISPER_LANGUAGE_NAMES)
