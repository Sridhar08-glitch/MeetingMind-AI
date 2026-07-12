"""Production Speech-to-Text provider using local Faster-Whisper.

Free, offline, no paid API. The heavy ``faster_whisper`` import is lazy so the
base project runs without it; models are cached process-wide so they are loaded
once, not per job. GPU can be enabled later purely via ``WHISPER_DEVICE=cuda`` —
no code change.

This module is an *integration point*: it is exercised in production, not in the
test suite (tests use the dummy provider and never download models).
"""
from __future__ import annotations

import logging
import math

from django.conf import settings

from .base import STTResult, STTSegment, STTWord, SpeechToTextProvider
from .languages import language_name as _language_name

logger = logging.getLogger("meetingmind.processing")

# Process-wide model cache keyed by (model, device, compute_type) so a warm
# worker never reloads the same model.
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}


def _load_model(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel  # lazy import

        logger.info("Loading Faster-Whisper model %s (%s/%s)…", model_size, device, compute_type)
        _MODEL_CACHE[key] = WhisperModel(
            model_size, device=device, compute_type=compute_type,
            download_root=settings.WHISPER_DOWNLOAD_ROOT,
        )
    return _MODEL_CACHE[key]


def _confidence(avg_logprob: float | None) -> float | None:
    if avg_logprob is None:
        return None
    # avg_logprob is a mean log-probability (<= 0); map to (0, 1].
    return round(min(1.0, math.exp(avg_logprob)), 4)


class FasterWhisperProvider(SpeechToTextProvider):
    requires_audio = True

    def __init__(self, *, model_size: str | None = None, device: str | None = None,
                 compute_type: str | None = None, beam_size: int | None = None):
        self._model_size = model_size or settings.WHISPER_MODEL_SIZE
        self._device = device or settings.WHISPER_DEVICE
        self._compute_type = compute_type or settings.WHISPER_COMPUTE_TYPE
        self._beam_size = beam_size or settings.WHISPER_BEAM_SIZE

    @property
    def name(self) -> str:
        return "faster_whisper"

    @property
    def model_name(self) -> str:
        return self._model_size

    def transcribe(
        self,
        audio_path: str | None,
        *,
        language: str | None = None,
        duration: float | None = None,
        task: str = "transcribe",
    ) -> STTResult:
        if not audio_path:
            raise ValueError("FasterWhisperProvider requires an audio path.")
        model = _load_model(self._model_size, self._device, self._compute_type)
        segments_iter, info = model.transcribe(
            audio_path,
            beam_size=self._beam_size,
            language=language,          # None → auto-detect
            task=task if task in ("transcribe", "translate") else "transcribe",
            word_timestamps=True,
            vad_filter=True,
        )
        segments: list[STTSegment] = []
        for seg in segments_iter:  # generator — consumed here
            words = [
                STTWord(start=w.start, end=w.end, word=w.word, probability=getattr(w, "probability", None))
                for w in (seg.words or [])
            ]
            segments.append(STTSegment(
                start=seg.start, end=seg.end, text=seg.text,
                confidence=_confidence(getattr(seg, "avg_logprob", None)),
                words=words,
            ))
        return STTResult(
            segments=segments,
            language=info.language,
            language_confidence=round(float(info.language_probability), 4),
            model=self._model_size,
            provider=self.name,
            duration=getattr(info, "duration", duration),
        )

    def supported_languages(self) -> dict[str, str]:
        # Sourced from Whisper's own tokenizer — never a hardcoded app list, so a
        # model swap changes the languages automatically.
        try:
            from faster_whisper.tokenizer import _LANGUAGE_CODES  # type: ignore

            codes = sorted(_LANGUAGE_CODES)
        except Exception:  # noqa: BLE001 — lib missing/renamed → empty, UI hides selector
            return {}
        return {code: _language_name(code) for code in codes}
