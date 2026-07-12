"""Provider-agnostic transcription orchestration + text services.

`SpeechToTextService` is the single entry point stages use; it delegates to the
configured provider without the caller knowing which one is active. The cleanup
and segmentation services are pure text utilities (no provider knowledge).
"""
from __future__ import annotations

import re

from apps.meetings.services.stt import STTResult, get_speech_provider


class SpeechToTextService:
    def __init__(self, provider=None, *, model: str | None = None):
        self.provider = provider or get_speech_provider(model=model)

    @property
    def requires_audio(self) -> bool:
        return self.provider.requires_audio

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    def transcribe(self, audio_path, *, language=None, duration=None, task="transcribe") -> STTResult:
        return self.provider.transcribe(audio_path, language=language, duration=duration, task=task)

    def supported_languages(self) -> dict[str, str]:
        return self.provider.supported_languages()

    @property
    def supports_auto_detect(self) -> bool:
        return self.provider.supports_auto_detect


class TranscriptCleanupService:
    """Cosmetic cleanup only — never changes meaning."""

    _MULTISPACE = re.compile(r"[ \t]+")
    _SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
    _REPEAT_PUNCT = re.compile(r"([!?,;:])\1+")
    _MANY_DOTS = re.compile(r"\.{4,}")

    def clean(self, text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        text = self._MULTISPACE.sub(" ", text)
        text = self._SPACE_BEFORE_PUNCT.sub(r"\1", text)
        text = self._REPEAT_PUNCT.sub(r"\1", text)   # "!!!" -> "!"
        text = self._MANY_DOTS.sub("...", text)       # keep ellipsis, cap runs
        return text.strip()

    def clean_full(self, segments_text: list[str]) -> str:
        return self.clean(" ".join(t for t in segments_text if t))


class TranscriptSegmentationService:
    """Normalize provider segments into storable rows (never one big blob)."""

    def __init__(self, cleanup: TranscriptCleanupService | None = None):
        self.cleanup = cleanup or TranscriptCleanupService()

    def build(self, result: STTResult) -> list[dict]:
        rows: list[dict] = []
        for i, seg in enumerate(result.segments):
            text = self.cleanup.clean(seg.text)
            rows.append({
                "index": i,
                "start_time": round(seg.start, 3),
                "end_time": round(seg.end, 3),
                "speaker": "",
                "text": text,
                "confidence": seg.confidence,
                "word_count": len(text.split()),
            })
        return rows
