"""Local translation via the configured LLM (Ollama by default).

Reuses the existing LLMProvider + versioned ``translation`` prompt — no new model,
no paid API. Translates segment texts in JSON batches (reliable + few calls), with
a per-segment fallback if a batch response doesn't line up.
"""
from __future__ import annotations

import json as jsonlib
import logging
import time

from django.conf import settings

from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import get_llm_provider
from apps.meetings.services.stt.languages import language_name

from .base import TranslationProvider, TranslationResult

logger = logging.getLogger("meetingmind.ai")

_BATCH = 12  # segments per LLM call


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


class OllamaTranslationProvider(TranslationProvider):
    def __init__(self, *, model: str | None = None):
        self._llm = get_llm_provider(model=model)

    @property
    def name(self) -> str:
        return f"llm:{self._llm.name}"

    @property
    def model_name(self) -> str:
        return self._llm.model_name

    def translate(
        self, texts: list[str], *, target_language: str, source_language: str | None = None
    ) -> TranslationResult:
        started = time.perf_counter()
        target_name = language_name(target_language)
        out: list[str] = []
        for batch in _chunks(list(texts), _BATCH):
            out.extend(self._translate_batch(batch, target_name))
        # Safety: never return a mis-aligned list.
        if len(out) != len(texts):
            out = (out + [""] * len(texts))[: len(texts)]
        full = " ".join(t for t in out if t).strip()
        return TranslationResult(
            text=full, segments=out, target_language=target_language,
            provider=self.name, confidence=None,
            ms=int((time.perf_counter() - started) * 1000),
        )

    def _translate_batch(self, batch: list[str], target_name: str) -> list[str]:
        non_empty = [t for t in batch if t.strip()]
        if not non_empty:
            return list(batch)
        lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(batch))
        system, user = prompt_registry.get("translation").render(
            target_language=target_name, lines=lines
        )
        try:
            resp = self._llm.generate(user, system=system, json=True, schema_hint="translation")
            data = jsonlib.loads(resp.text)
            translations = data.get("translations")
            if isinstance(translations, list) and len(translations) == len(batch):
                return [str(x) for x in translations]
        except Exception:  # noqa: BLE001 — fall through to per-segment
            logger.debug("Batch translation failed; falling back to per-segment", exc_info=True)
        return [self._translate_one(t, target_name) for t in batch]

    def _translate_one(self, text: str, target_name: str) -> str:
        if not text.strip():
            return ""
        try:
            resp = self._llm.generate(
                f"Translate this text into {target_name}. Output ONLY the translation, "
                f"no quotes, no explanation.\n\nText: {text}",
                system="You are a professional translator.",
            )
            return resp.text.strip()
        except Exception:  # noqa: BLE001 — degrade to original text
            logger.debug("Per-segment translation failed", exc_info=True)
            return text

    def supported_languages(self) -> dict[str, str]:
        # The LLM decides what it can translate INTO.
        langs = self._llm.supported_languages()
        return langs or {}
