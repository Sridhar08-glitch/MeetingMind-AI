"""Language capabilities — assembled from the ACTIVE providers (never hardcoded).

The frontend fills its Meeting / Transcript / AI-output language selectors from
this endpoint, so swapping the STT/LLM/translation model updates the available
languages with zero UI code change.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class LanguagesView(APIView):
    """GET /api/languages/ — capabilities of the configured providers."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.meetings.services.llm import get_llm_provider
        from apps.meetings.services.transcription import SpeechToTextService
        from apps.meetings.services.translation import get_translation_provider

        stt = SpeechToTextService()
        try:
            transcription = stt.supported_languages()
        except Exception:  # noqa: BLE001 — provider lib may be absent
            transcription = {}
        try:
            transcript_targets = get_translation_provider().supported_languages()
        except Exception:  # noqa: BLE001
            transcript_targets = {}
        try:
            ai_output = get_llm_provider().supported_languages()
        except Exception:  # noqa: BLE001
            ai_output = {}

        return Response({
            "detect": bool(getattr(stt, "supports_auto_detect", True)),
            "transcription": transcription,
            "transcript_targets": transcript_targets,
            "ai_output": ai_output,
        })
