"""Universal media import API (Phase 14).

Endpoints (mounted under /api/meetings/):
  POST import/analyze/   → metadata preview for one or many URLs (no download)
  POST import/           → start import session(s); returns them for polling
  GET  import/           → the caller's recent/active import sessions
  GET  import/<id>/      → poll one session (includes meeting_id when done)
  POST import/<id>/cancel/ → cancel an in-flight import

Capabilities live at /api/media/sources/ (see MediaSourcesView).

Every path ends by handing a local file to create_upload — no AI logic here.
"""
from __future__ import annotations

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.meetings.enums import DuplicateAction
from apps.meetings.ingest import service as ingest
from apps.meetings.ingest.models import ACTIVE_IMPORT_STATUSES, MediaImportSession
from apps.meetings.services import media_sources as ms
from apps.meetings.services.media_sources.base import MediaProviderError


# ─────────────────────────── serializers ───────────────────────────────────
class EpisodeSerializer(serializers.Serializer):
    episode_id = serializers.CharField()
    title = serializers.CharField()
    guid = serializers.CharField()
    url = serializers.CharField()
    duration = serializers.IntegerField(allow_null=True)
    published_at = serializers.CharField(allow_blank=True)


class MediaSourceInfoSerializer(serializers.Serializer):
    source_type = serializers.CharField()
    webpage_url = serializers.CharField()
    platform = serializers.CharField()
    platform_id = serializers.CharField()
    title = serializers.CharField()
    author = serializers.CharField()
    duration = serializers.IntegerField(allow_null=True)
    thumbnail_url = serializers.CharField()
    published_at = serializers.CharField()
    license = serializers.CharField()
    media_kind = serializers.CharField()
    is_playlist = serializers.BooleanField()
    episodes = EpisodeSerializer(many=True)


class MediaImportSessionSerializer(serializers.ModelSerializer):
    meeting_id = serializers.UUIDField(source="meeting.id", read_only=True, allow_null=True)
    duplicate_meeting_id = serializers.UUIDField(
        source="duplicate_meeting.id", read_only=True, allow_null=True
    )
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = MediaImportSession
        fields = (
            "id", "status", "progress", "bytes_downloaded", "total_bytes",
            "source_type", "provider_id", "source_url", "platform", "platform_id",
            "title", "author", "thumbnail_url", "published_at", "license",
            "duration_seconds", "media_kind", "requested_media", "episode_id",
            "playlist", "meeting_language", "transcript_language", "ai_language",
            "on_duplicate", "meeting_id", "duplicate_meeting_id", "is_active",
            "error_code", "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields


class _AnalyzeSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, allow_blank=True)
    urls = serializers.ListField(child=serializers.CharField(), required=False, max_length=25)


class _ImportSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, allow_blank=True)
    urls = serializers.ListField(child=serializers.CharField(), required=False, max_length=25)
    episode_id = serializers.CharField(required=False, allow_blank=True)
    requested_media = serializers.ChoiceField(choices=["audio", "video"], default="video")
    title = serializers.CharField(required=False, allow_blank=True)
    meeting_language = serializers.CharField(required=False, allow_blank=True, default="")
    transcript_language = serializers.CharField(required=False, allow_blank=True, default="original")
    ai_language = serializers.CharField(required=False, allow_blank=True, default="")
    on_duplicate = serializers.ChoiceField(
        choices=DuplicateAction.choices, required=False, default=DuplicateAction.REJECT
    )


# ─────────────────────────── viewset ───────────────────────────────────────
class MediaImportViewSet(viewsets.ViewSet):
    """Owner-scoped media import sessions."""

    permission_classes = [IsAuthenticated]

    def _queryset(self, request):
        return MediaImportSession.objects.filter(owner=request.user).select_related(
            "meeting", "duplicate_meeting"
        )

    def list(self, request: Request):
        active = request.query_params.get("active")
        qs = self._queryset(request).order_by("-created_at")
        if active in ("1", "true", "True"):
            qs = qs.filter(status__in=ACTIVE_IMPORT_STATUSES)
        else:
            qs = qs[:50]
        return success_response(data=MediaImportSessionSerializer(qs, many=True).data)

    def retrieve(self, request: Request, pk=None):
        session = self._queryset(request).filter(pk=pk).first()
        if session is None:
            return error_response("Import not found.", code="not_found", status=404)
        return success_response(data=MediaImportSessionSerializer(session).data)

    @action(detail=False, methods=["post"], url_path="analyze")
    def analyze(self, request: Request):
        s = _AnalyzeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        urls = _collect_urls(s.validated_data)
        if not urls:
            return error_response("Provide a url or urls.", code="no_url", status=400)
        results = []
        for url in urls:
            try:
                info = ingest.analyze_url(url)
                results.append({"url": url, "ok": True, "info": MediaSourceInfoSerializer(info).data})
            except MediaProviderError as exc:
                results.append({"url": url, "ok": False, "error": exc.message, "code": exc.code})
            except Exception as exc:  # noqa: BLE001
                results.append({"url": url, "ok": False, "error": str(exc), "code": "analyze_error"})
        return success_response(data={"results": results})

    def create(self, request: Request):
        s = _ImportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        urls = _collect_urls(data)
        if not urls:
            return error_response("Provide a url or urls.", code="no_url", status=400)
        # Each URL is imported independently — one failure never blocks the rest.
        sessions = []
        for url in urls:
            try:
                session = ingest.create_import(
                    request.user, url=url,
                    requested_media=data["requested_media"],
                    meeting_language=data.get("meeting_language", ""),
                    transcript_language=data.get("transcript_language", "original"),
                    ai_language=data.get("ai_language", ""),
                    on_duplicate=data.get("on_duplicate", DuplicateAction.REJECT),
                    episode_id=data.get("episode_id", "") if len(urls) == 1 else "",
                    title=data.get("title", "") if len(urls) == 1 else "",
                )
                sessions.append(MediaImportSessionSerializer(session).data)
            except MediaProviderError as exc:
                sessions.append({"source_url": url, "status": "blocked",
                                 "error_code": exc.code, "error_message": exc.message})
        return success_response(data={"imports": sessions}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk=None):
        session = self._queryset(request).filter(pk=pk).first()
        if session is None:
            return error_response("Import not found.", code="not_found", status=404)
        ingest.cancel_import(session)
        session.refresh_from_db()
        return success_response(data=MediaImportSessionSerializer(session).data)


def _collect_urls(data: dict) -> list[str]:
    urls = list(data.get("urls") or [])
    if data.get("url"):
        urls.insert(0, data["url"])
    # De-dupe while preserving order; drop blanks.
    seen, out = set(), []
    for u in (u.strip() for u in urls):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ─────────────────────────── capabilities ──────────────────────────────────
class MediaSourcesView(APIView):
    """GET /api/media/sources/ — which import providers are available."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings

        enabled = getattr(settings, "MEDIA_IMPORT_ENABLED", True)
        providers = [
            {"id": p.id, "label": p.label, "source_type": p.source_type,
             "supports_resume": p.supports_resume}
            for p in ms.enabled_providers()
        ]
        return Response({
            "import_available": bool(enabled and ms.import_available()),
            "enabled": bool(enabled),
            "video_download": True,
            "providers": providers,
            "max_duration_seconds": getattr(settings, "MEDIA_IMPORT_MAX_DURATION_SECONDS", None),
        })
