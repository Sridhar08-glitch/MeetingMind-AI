"""Meetings API.

Read, metadata-update, soft-delete, upload, download, status-polling and
reprocess are implemented here. The AI pipeline is introduced in later phases —
an uploaded meeting is validated, versioned and queued only.
"""
from __future__ import annotations

import logging
import os
import re

from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request

from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.meetings.api.permissions import IsOwner
from apps.meetings.api.serializers import (
    AIAnalysisSerializer,
    AIAnalysisVersionSerializer,
    MeetingDetailSerializer,
    MeetingEventSerializer,
    MeetingListSerializer,
    MeetingUpdateSerializer,
    MeetingUploadSerializer,
    RetranscribeSerializer,
    SpeakerEditSerializer,
    SpeakerSerializer,
    TranscriptSegmentEditSerializer,
    TranscriptSegmentSerializer,
    TranscriptSerializer,
)
from apps.meetings.models import AIAnalysis, Meeting, Speaker, Transcript, TranscriptSegment
from apps.meetings.selectors.meetings import dashboard_stats, meetings_for_owner
from apps.meetings.services import transcript_formats, transcripts
from apps.meetings.services.uploads import (
    UploadError,
    create_upload,
    enqueue_ai_summarization,
    enqueue_meeting_processing,
)

logger = logging.getLogger("meetingmind")

_STREAM_CHUNK = 512 * 1024  # 512 KB per read while streaming


def _resolve_stream_user(request):
    """Owner for a media stream: header-authenticated user, else ``?token=`` JWT."""
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user
    token = request.query_params.get("token")
    if not token:
        return None
    try:
        from rest_framework_simplejwt.tokens import AccessToken

        from apps.accounts.models import User

        access = AccessToken(token)
        return User.objects.filter(pk=access["user_id"], is_active=True).first()
    except Exception:  # noqa: BLE001 — invalid/expired token → 404
        return None


def _file_iterator(path: str, start: int, length: int):
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            data = fh.read(min(_STREAM_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _range_file_response(request: Request, target):
    """Serve a MeetingFile inline, honoring a Range header for seek/stream."""
    try:
        path = target.file.path
        size = os.path.getsize(path)
    except (NotImplementedError, OSError):
        # Non-filesystem storage (shouldn't happen in local-first): fall back to a
        # plain inline response with no Range support.
        resp = FileResponse(target.file.open("rb"),
                            content_type=target.content_type or "application/octet-stream")
        resp["Content-Disposition"] = "inline"
        return resp

    content_type = target.content_type or "application/octet-stream"
    range_match = re.match(r"bytes=(\d+)-(\d*)", request.META.get("HTTP_RANGE", "").strip())
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2)) if range_match.group(2) else size - 1
        end = min(end, size - 1)
        start = min(start, end)
        length = end - start + 1
        resp = StreamingHttpResponse(
            _file_iterator(path, start, length), status=206, content_type=content_type,
        )
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(length)
    else:
        resp = StreamingHttpResponse(
            _file_iterator(path, 0, size), content_type=content_type,
        )
        resp["Content-Length"] = str(size)
    resp["Accept-Ranges"] = "bytes"
    resp["Content-Disposition"] = "inline"
    return resp


class MeetingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Owner-scoped access to meetings."""

    permission_classes = [IsAuthenticated, IsOwner]
    filterset_fields = ("processing_status", "language", "source", "is_archived", "is_favorite")
    search_fields = ("title", "description")
    ordering_fields = ("created_at", "updated_at", "duration_seconds", "title")
    ordering = ("-created_at",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Meeting.objects.none()
        qs = meetings_for_owner(self.request.user)
        if self.action == "retrieve":
            return qs.prefetch_related("segments", "ai_outputs", "logs", "events")
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return MeetingDetailSerializer
        if self.action in {"update", "partial_update"}:
            return MeetingUpdateSerializer
        if self.action == "upload":
            return MeetingUploadSerializer
        return MeetingListSerializer

    def get_parsers(self):
        if getattr(self, "action", None) == "upload":
            return [MultiPartParser(), FormParser()]
        return super().get_parsers()

    def get_throttles(self):
        if getattr(self, "action", None) == "upload":
            self.throttle_scope = "upload"
        return super().get_throttles()

    # --- Metadata edit ---------------------------------------------------
    def perform_update(self, serializer) -> None:
        serializer.instance.set_acting_user(self.request.user)
        serializer.save()

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        instance = self.get_object()
        data = MeetingDetailSerializer(instance, context=self.get_serializer_context()).data
        return success_response(data=data, message="Meeting updated.")

    # --- Soft delete -----------------------------------------------------
    def perform_destroy(self, instance: Meeting) -> None:
        instance.set_acting_user(self.request.user)
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(message="Meeting deleted.", status=status.HTTP_200_OK)

    # --- Upload ----------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request: Request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            outcome = create_upload(
                owner=request.user,
                uploaded_file=data["file"],
                title=data.get("title", ""),
                description=data.get("description", ""),
                language=data.get("language") or "en",
                source=data.get("source"),
                tags=data.get("tags") or [],
                on_duplicate=data.get("on_duplicate"),
            )
        except UploadError as exc:
            return error_response(exc.message, code=exc.code, details=exc.details, status=exc.status)

        payload = MeetingDetailSerializer(outcome.meeting, context=self.get_serializer_context()).data
        payload["validation_report"] = outcome.report.as_dict()
        payload["upload_session_id"] = str(outcome.session.id)
        message = (
            "Upload received and queued for processing."
            if outcome.created else "You already had this file; showing the existing meeting."
        )
        return success_response(
            data=payload, message=message,
            status=status.HTTP_201_CREATED if outcome.created else status.HTTP_200_OK,
        )

    # --- Favorite toggle -------------------------------------------------
    @action(detail=True, methods=["post"], url_path="favorite")
    def favorite(self, request: Request, pk=None):
        meeting = self.get_object()
        meeting.is_favorite = not meeting.is_favorite
        meeting.set_acting_user(request.user)
        meeting.save(update_fields=["is_favorite", "updated_at"])
        return success_response(
            data={"id": str(meeting.id), "is_favorite": meeting.is_favorite},
            message="Added to favorites." if meeting.is_favorite else "Removed from favorites.",
        )

    # --- Reprocess (lock-protected) --------------------------------------
    @action(detail=True, methods=["post"], url_path="reprocess")
    def reprocess(self, request: Request, pk=None):
        meeting = self.get_object()
        try:
            enqueue_meeting_processing(meeting, actor=request.user)
        except UploadError as exc:
            return error_response(exc.message, code=exc.code, details=exc.details, status=exc.status)
        data = MeetingDetailSerializer(meeting, context=self.get_serializer_context()).data
        return success_response(data=data, message="Meeting re-queued for processing.")

    # --- Status polling --------------------------------------------------
    @action(detail=True, methods=["get"], url_path="status")
    def status(self, request: Request, pk=None):
        meeting = self.get_object()
        current = meeting.current_file
        events = MeetingEventSerializer(meeting.events.all(), many=True).data
        return success_response(data={
            "id": str(meeting.id),
            "processing_status": meeting.processing_status,
            "processing_status_display": meeting.get_processing_status_display(),
            "upload_status": current.upload_status if current else None,
            "duration_seconds": meeting.duration_seconds,
            "updated_at": meeting.updated_at,
            "events": events,
        })

    # --- Owner-only download ---------------------------------------------
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request: Request, pk=None):
        meeting = self.get_object()
        version = request.query_params.get("version")
        if version:
            target = meeting.files.filter(version=version).first()
        else:
            target = meeting.current_file
        if target is None or not target.file:
            raise Http404("No file is associated with this meeting.")
        return FileResponse(
            target.file.open("rb"),
            as_attachment=True,
            filename=target.original_filename or target.stored_filename,
            content_type=target.content_type or "application/octet-stream",
        )

    # --- Owner-only inline stream (Range-capable, for the media player) ---
    @action(detail=True, methods=["get"], url_path="stream",
            permission_classes=[AllowAny], authentication_classes=[])
    def stream(self, request: Request, pk=None):
        """Range-capable inline media stream for the <video>/<audio> element.

        The media element can't attach an Authorization header, so this endpoint
        also accepts the JWT via ``?token=``. HTTP Range support lets the browser
        seek and stream multi-GB recordings without loading the whole file into
        memory (the previous whole-file blob download froze the page).
        """
        user = _resolve_stream_user(request)
        if user is None:
            raise Http404("Not found.")
        meeting = meetings_for_owner(user).filter(pk=pk).first()
        if meeting is None:
            raise Http404("Not found.")
        version = request.query_params.get("version")
        target = meeting.files.filter(version=version).first() if version else meeting.current_file
        if target is None or not target.file:
            raise Http404("No file is associated with this meeting.")
        return _range_file_response(request, target)

    # --- Transcript: read ------------------------------------------------
    def _transcript(self, meeting) -> Transcript | None:
        return meeting.transcripts.order_by("-created_at").first()

    @action(detail=True, methods=["get"], url_path="transcript")
    def transcript(self, request: Request, pk=None):
        meeting = self.get_object()
        transcript = self._transcript(meeting)
        segments = TranscriptSegment.objects.filter(meeting=meeting).order_by("index")
        speakers = Speaker.objects.filter(meeting=meeting).order_by("label")
        return success_response(data={
            "transcript": TranscriptSerializer(transcript).data if transcript else None,
            "segments": TranscriptSegmentSerializer(segments, many=True).data,
            "speakers": SpeakerSerializer(speakers, many=True).data,
        })

    # --- Speakers (Phase 15) ---------------------------------------------
    @action(detail=True, methods=["get"], url_path="speakers")
    def speakers(self, request: Request, pk=None):
        meeting = self.get_object()
        qs = Speaker.objects.filter(meeting=meeting).order_by("label")
        return success_response(data={"speakers": SpeakerSerializer(qs, many=True).data})

    def _speaker(self, meeting, sid):
        return Speaker.objects.filter(meeting=meeting, id=sid).first()

    @action(detail=True, methods=["patch"], url_path=r"speakers/(?P<sid>[0-9a-f-]+)")
    def edit_speaker(self, request: Request, pk=None, sid=None):
        from apps.meetings.services import speakers as speaker_svc

        meeting = self.get_object()
        speaker = self._speaker(meeting, sid)
        if speaker is None:
            raise Http404("Speaker not found.")
        serializer = SpeakerEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        confirmed = data.pop("confirmed", None)
        speaker_svc.update_speaker(speaker, changes=data, confirmed=confirmed)
        return success_response(data=SpeakerSerializer(speaker).data, message="Speaker updated.")

    @action(detail=True, methods=["post"], url_path=r"speakers/(?P<sid>[0-9a-f-]+)/accept-suggestion")
    def accept_speaker_suggestion(self, request: Request, pk=None, sid=None):
        from apps.meetings.services import speakers as speaker_svc

        meeting = self.get_object()
        speaker = self._speaker(meeting, sid)
        if speaker is None:
            raise Http404("Speaker not found.")
        speaker_svc.accept_suggestion(speaker)
        return success_response(data=SpeakerSerializer(speaker).data, message="Suggestion accepted.")

    @action(detail=True, methods=["post"], url_path=r"speakers/(?P<sid>[0-9a-f-]+)/merge")
    def merge_speaker(self, request: Request, pk=None, sid=None):
        from apps.meetings.services import speakers as speaker_svc

        meeting = self.get_object()
        target = self._speaker(meeting, sid)
        source = self._speaker(meeting, request.data.get("from"))
        if target is None or source is None:
            raise Http404("Speaker not found.")
        speaker_svc.merge_speakers(target, source)
        return success_response(data=SpeakerSerializer(target).data, message="Speakers merged.")

    @action(detail=True, methods=["get"], url_path="transcript/segments")
    def transcript_segments(self, request: Request, pk=None):
        meeting = self.get_object()
        segments = TranscriptSegment.objects.filter(meeting=meeting).order_by("index")
        return success_response(data=TranscriptSegmentSerializer(segments, many=True).data)

    @action(detail=True, methods=["get"], url_path="transcript/stats")
    def transcript_stats(self, request: Request, pk=None):
        meeting = self.get_object()
        transcript = self._transcript(meeting)
        if transcript is None:
            return error_response("No transcript yet.", code="no_transcript", status=404)
        return success_response(data={
            "word_count": transcript.word_count,
            "char_count": transcript.char_count,
            "segment_count": meeting.segments.count(),
            "avg_confidence": transcript.avg_confidence,
            "detected_language": transcript.detected_language,
            "language_confidence": transcript.language_confidence,
            "model_used": transcript.model_used,
            "provider": transcript.provider,
            "processing_ms": transcript.processing_ms,
            "audio_duration_seconds": transcript.audio_duration_seconds,
            "transcription_speed": transcript.transcription_speed,
            "is_edited": transcript.is_edited,
        })

    @action(detail=True, methods=["get"], url_path="transcript/language")
    def transcript_language(self, request: Request, pk=None):
        meeting = self.get_object()
        transcript = self._transcript(meeting)
        if transcript is None:
            return error_response("No transcript yet.", code="no_transcript", status=404)
        return success_response(data={
            "detected_language": transcript.detected_language,
            "language_confidence": transcript.language_confidence,
            "meeting_language": meeting.language,
        })

    @action(detail=True, methods=["get"], url_path="transcript/search")
    def transcript_search(self, request: Request, pk=None):
        meeting = self.get_object()
        p = request.query_params
        start = p.get("start")
        end = p.get("end")
        results = transcripts.search_segments(
            meeting,
            query=p.get("q", ""),
            speaker=p.get("speaker", ""),
            start=float(start) if start else None,
            end=float(end) if end else None,
        )
        return success_response(data={
            "query": p.get("q", ""),
            "count": results.count(),
            "segments": TranscriptSegmentSerializer(results, many=True).data,
        })

    @action(detail=True, methods=["get"], url_path="transcript/download")
    def transcript_download(self, request: Request, pk=None):
        meeting = self.get_object()
        transcript = self._transcript(meeting)
        segments = list(meeting.segments.order_by("index"))
        if not segments:
            raise Http404("No transcript to download.")
        # Note: the query param is `fmt`, not `format` — the latter is reserved
        # by DRF for content negotiation and would 404 before the view runs.
        try:
            content, mime, ext = transcript_formats.render(
                request.query_params.get("fmt", "txt"), meeting, transcript, segments
            )
        except ValueError as exc:
            return error_response(str(exc), code="invalid_format", status=400)
        resp = HttpResponse(content, content_type=mime)
        safe = "".join(c for c in meeting.title if c.isalnum() or c in " -_").strip() or "transcript"
        resp["Content-Disposition"] = f'attachment; filename="{safe}.{ext}"'
        return resp

    # --- Transcript: edit / restore / retranscribe -----------------------
    @action(detail=True, methods=["patch"], url_path=r"segments/(?P<seg_id>[0-9a-f-]+)")
    def edit_segment(self, request: Request, pk=None, seg_id=None):
        meeting = self.get_object()
        segment = TranscriptSegment.objects.filter(meeting=meeting, id=seg_id).first()
        if segment is None:
            raise Http404("Segment not found.")
        serializer = TranscriptSegmentEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transcripts.edit_segment(
            segment, text=serializer.validated_data["text"],
            speaker=serializer.validated_data.get("speaker"), actor=request.user,
        )
        return success_response(data=TranscriptSegmentSerializer(segment).data, message="Segment updated.")

    @action(detail=True, methods=["post"], url_path=r"segments/(?P<seg_id>[0-9a-f-]+)/restore")
    def restore_segment(self, request: Request, pk=None, seg_id=None):
        meeting = self.get_object()
        segment = TranscriptSegment.objects.filter(meeting=meeting, id=seg_id).first()
        if segment is None:
            raise Http404("Segment not found.")
        transcripts.restore_segment(segment)
        return success_response(data=TranscriptSegmentSerializer(segment).data, message="Segment restored.")

    @action(detail=True, methods=["post"], url_path="transcript/restore")
    def transcript_restore(self, request: Request, pk=None):
        meeting = self.get_object()
        count = transcripts.restore_transcript(meeting)
        return success_response(message=f"Restored {count} segment(s).", data={"restored": count})

    @action(detail=True, methods=["post"], url_path="retranscribe")
    def retranscribe(self, request: Request, pk=None):
        meeting = self.get_object()
        serializer = RetranscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transcripts.retranscribe(
                meeting, actor=request.user,
                model=serializer.validated_data.get("model"),
                language=serializer.validated_data.get("language"),
            )
        except UploadError as exc:
            return error_response(exc.message, code=exc.code, details=exc.details, status=exc.status)
        data = MeetingDetailSerializer(meeting, context=self.get_serializer_context()).data
        return success_response(data=data, message="Re-transcription queued.")

    # --- AI analysis (Phase 7) -------------------------------------------
    def _analysis(self, meeting) -> AIAnalysis | None:
        return meeting.analyses.filter(is_current=True).order_by("-version").first()

    @action(detail=True, methods=["get"], url_path="ai")
    def ai(self, request: Request, pk=None):
        meeting = self.get_object()
        analysis = self._analysis(meeting)
        return success_response(data=AIAnalysisSerializer(analysis).data if analysis else None)

    @action(detail=True, methods=["get"], url_path="ai/action-items")
    def ai_action_items(self, request: Request, pk=None):
        return self._ai_field(self.get_object(), "action_items")

    @action(detail=True, methods=["get"], url_path="ai/decisions")
    def ai_decisions(self, request: Request, pk=None):
        return self._ai_field(self.get_object(), "decisions")

    @action(detail=True, methods=["get"], url_path="ai/risks")
    def ai_risks(self, request: Request, pk=None):
        return self._ai_field(self.get_object(), "risks")

    @action(detail=True, methods=["get"], url_path="ai/keywords")
    def ai_keywords(self, request: Request, pk=None):
        return self._ai_field(self.get_object(), "keywords")

    def _ai_field(self, meeting, field: str):
        analysis = self._analysis(meeting)
        if analysis is None:
            return error_response("No AI analysis yet.", code="no_analysis", status=404)
        return success_response(data=getattr(analysis, field))

    @action(detail=True, methods=["get"], url_path="ai/history")
    def ai_history(self, request: Request, pk=None):
        meeting = self.get_object()
        versions = meeting.analyses.order_by("-version")
        return success_response(data=AIAnalysisVersionSerializer(versions, many=True).data)

    @action(detail=True, methods=["post"], url_path="ai/regenerate")
    def ai_regenerate(self, request: Request, pk=None):
        meeting = self.get_object()
        model = request.data.get("model") or None
        try:
            enqueue_ai_summarization(meeting, actor=request.user, model=model)
        except UploadError as exc:
            return error_response(exc.message, code=exc.code, details=exc.details, status=exc.status)
        return success_response(message="AI summary regeneration queued.",
                                data={"meeting_id": str(meeting.id)})


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=dashboard_stats(request.user))
