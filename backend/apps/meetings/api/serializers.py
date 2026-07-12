"""Serializers for the meetings API."""
from __future__ import annotations

from rest_framework import serializers

from apps.meetings.enums import DuplicateAction, MeetingSource
from apps.meetings.models import (
    AIAnalysis,
    AIOutput,
    MediaMetadata,
    Meeting,
    MeetingEvent,
    MeetingFile,
    ProcessingLog,
    Speaker,
    Transcript,
    TranscriptSegment,
)


class AIAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAnalysis
        fields = (
            "id", "version", "is_current",
            "executive_summary", "detailed_summary", "bullet_summary", "meeting_minutes",
            "action_items", "decisions", "risks", "follow_ups", "deadlines", "keywords",
            "model_used", "provider", "prompt_version", "inference_ms", "chunks",
            "temperature", "output_language", "created_at",
        )
        read_only_fields = fields


class AIAnalysisVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAnalysis
        fields = ("id", "version", "is_current", "model_used", "provider",
                  "prompt_version", "inference_ms", "created_at")
        read_only_fields = fields


class SpeakerSerializer(serializers.ModelSerializer):
    """A first-class meeting speaker (Phase 15) — editable identity + analytics."""

    name = serializers.CharField(read_only=True)  # display_name or label
    # Cross-meeting identity link (Phase 15B), if this speaker has been confirmed.
    voice_person_id = serializers.UUIDField(source="voice_person.id", read_only=True, allow_null=True)
    voice_person_name = serializers.CharField(
        source="voice_person.display_name", read_only=True, allow_null=True
    )

    class Meta:
        model = Speaker
        fields = (
            "id", "label", "display_name", "name", "confirmed", "color",
            "role", "department", "email", "avatar", "aliases",
            "suggested_name", "suggested_confidence", "recognition_confidence",
            "talk_time_seconds", "segment_count", "word_count", "avg_confidence",
            "voice_person_id", "voice_person_name",
        )
        read_only_fields = (
            "id", "label", "name", "suggested_name", "suggested_confidence",
            "recognition_confidence", "talk_time_seconds", "segment_count",
            "word_count", "avg_confidence", "voice_person_id", "voice_person_name",
        )


class SpeakerEditSerializer(serializers.Serializer):
    """Editable speaker-card fields. A display_name change cascades to segments."""

    display_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    role = serializers.CharField(required=False, allow_blank=True, max_length=120)
    department = serializers.CharField(required=False, allow_blank=True, max_length=120)
    email = serializers.EmailField(required=False, allow_blank=True)
    color = serializers.CharField(required=False, allow_blank=True, max_length=16)
    avatar = serializers.URLField(required=False, allow_blank=True, max_length=512)
    aliases = serializers.ListField(child=serializers.CharField(max_length=120), required=False)
    confirmed = serializers.BooleanField(required=False)


class TranscriptSegmentSerializer(serializers.ModelSerializer):
    speaker_id = serializers.UUIDField(source="speaker_ref_id", read_only=True, allow_null=True)

    class Meta:
        model = TranscriptSegment
        fields = (
            "id", "index", "start_time", "end_time", "speaker", "speaker_id", "text",
            "translated_text", "confidence", "word_count", "is_edited", "edited_at",
        )
        read_only_fields = (
            "id", "index", "start_time", "end_time", "speaker_id", "translated_text",
            "confidence", "word_count", "is_edited", "edited_at",
        )


class TranscriptSegmentEditSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=False)
    speaker = serializers.CharField(required=False, allow_blank=True, max_length=100)


class TranscriptSerializer(serializers.ModelSerializer):
    transcription_speed = serializers.FloatField(read_only=True)

    class Meta:
        model = Transcript
        fields = (
            "id", "clean_text", "raw_text", "word_count", "char_count",
            "detected_language", "language_confidence", "avg_confidence",
            "translated_text", "target_language", "translation_provider",
            "translation_confidence", "translation_ms",
            "model_used", "provider", "processing_ms", "audio_duration_seconds",
            "transcription_speed", "is_edited", "edited_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class RetranscribeSerializer(serializers.Serializer):
    model = serializers.ChoiceField(choices=[], required=False)
    language = serializers.CharField(required=False, allow_blank=True, max_length=16)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.conf import settings

        self.fields["model"].choices = [(m, m) for m in settings.WHISPER_MODELS]


class AIOutputSerializer(serializers.ModelSerializer):
    current_output = serializers.JSONField(read_only=True)

    class Meta:
        model = AIOutput
        fields = ("id", "kind", "raw_output", "edited_output", "current_output", "metadata", "updated_at")
        read_only_fields = ("id", "kind", "raw_output", "current_output", "metadata", "updated_at")


class ProcessingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingLog
        fields = ("id", "stage", "status", "message", "duration_ms", "created_at")
        read_only_fields = fields


class MeetingEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    actor = serializers.SerializerMethodField()

    class Meta:
        model = MeetingEvent
        fields = (
            "id", "event_type", "event_type_display", "source", "actor",
            "message", "details", "duration_ms", "created_at",
        )
        read_only_fields = fields

    def get_actor(self, obj: MeetingEvent) -> str | None:
        return obj.created_by.email if obj.created_by_id else None


class MediaMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaMetadata
        fields = (
            "container", "audio_codec", "video_codec", "bitrate",
            "sample_rate", "channels", "frame_rate", "extra",
        )
        read_only_fields = fields


class MeetingFileSerializer(serializers.ModelSerializer):
    media_metadata = MediaMetadataSerializer(read_only=True)
    download_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = MeetingFile
        fields = (
            "id", "version", "is_current", "original_filename", "stored_filename",
            "file_extension", "content_type", "media_kind", "size_bytes",
            "checksum_sha256", "upload_status", "validation_report",
            "uploaded_at", "media_metadata", "download_url", "thumbnail_url",
        )
        read_only_fields = fields

    def get_download_url(self, obj: MeetingFile) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        path = f"/api/meetings/{obj.meeting_id}/download/?version={obj.version}"
        return request.build_absolute_uri(path) if request is not None else path

    def get_thumbnail_url(self, obj: MeetingFile) -> str | None:
        if not getattr(obj, "thumbnail", None):
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.thumbnail.url) if request else obj.thumbnail.url


class MeetingListSerializer(serializers.ModelSerializer):
    current_file = serializers.SerializerMethodField()
    upload_status = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = (
            "id", "title", "description", "language", "source",
            "processing_status", "upload_status", "is_archived", "is_favorite",
            "duration_seconds", "current_file", "tags", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_current_file(self, obj: Meeting):
        cur = obj.current_file
        return MeetingFileSerializer(cur, context=self.context).data if cur else None

    def get_upload_status(self, obj: Meeting) -> str | None:
        cur = obj.current_file
        return cur.upload_status if cur else None


class MeetingDetailSerializer(serializers.ModelSerializer):
    files = MeetingFileSerializer(many=True, read_only=True)
    current_file = serializers.SerializerMethodField()
    upload_status = serializers.SerializerMethodField()
    segments = TranscriptSegmentSerializer(many=True, read_only=True)
    ai_outputs = AIOutputSerializer(many=True, read_only=True)
    logs = ProcessingLogSerializer(many=True, read_only=True)
    events = MeetingEventSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = (
            "id", "title", "description", "language", "source",
            "processing_status", "upload_status", "is_archived", "is_favorite", "duration_seconds",
            "tags", "source_url", "source_metadata", "created_at", "updated_at",
            "current_file", "files", "segments", "ai_outputs", "logs", "events",
        )
        read_only_fields = fields

    def get_current_file(self, obj: Meeting):
        cur = obj.current_file
        return MeetingFileSerializer(cur, context=self.context).data if cur else None

    def get_upload_status(self, obj: Meeting) -> str | None:
        cur = obj.current_file
        return cur.upload_status if cur else None


class MeetingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ("id", "title", "description", "language", "source", "tags", "is_archived", "is_favorite")
        read_only_fields = ("id",)

    def validate_title(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value


class MeetingUploadSerializer(serializers.Serializer):
    """Validates the shape of an upload request; the service owns the workflow."""

    file = serializers.FileField(write_only=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    language = serializers.CharField(required=False, allow_blank=True, max_length=16)
    source = serializers.ChoiceField(
        choices=MeetingSource.choices, required=False, default=MeetingSource.MANUAL_UPLOAD
    )
    tags = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    on_duplicate = serializers.ChoiceField(
        choices=DuplicateAction.choices, required=False, default=DuplicateAction.REJECT
    )
