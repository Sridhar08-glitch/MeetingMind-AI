"""System status — a read-only snapshot of the active AI/processing configuration.

Exposes which local providers/models are configured so the Settings page can show
them. It is strictly read-only (no settings are writable here) and owner-agnostic.
"""
from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class SystemInfoView(APIView):
    """GET /api/system/info/ — the active provider/model configuration (read-only)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "ai_provider": getattr(settings, "AI_PROVIDER", ""),
            "ai_model": getattr(settings, "OLLAMA_MODEL", ""),
            "embedding_provider": getattr(settings, "EMBEDDING_PROVIDER", ""),
            "stt_provider": getattr(settings, "STT_PROVIDER", ""),
            "whisper_model": getattr(settings, "WHISPER_MODEL_SIZE", ""),
            "whisper_device": getattr(settings, "WHISPER_DEVICE", ""),
            "async_processing": not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", True),
            "storage_backend": getattr(settings, "STORAGE_BACKEND", "local"),
            "max_upload_mb": getattr(settings, "MAX_UPLOAD_SIZE_MB", None),
        })
