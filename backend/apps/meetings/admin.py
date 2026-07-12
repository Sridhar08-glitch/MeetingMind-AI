from django.contrib import admin

from apps.meetings.models import (
    AIAnalysis,
    AIOutput,
    ChatConversation,
    ChatMessage,
    MessageCitation,
    MediaMetadata,
    Meeting,
    MeetingEvent,
    MeetingFile,
    MeetingJob,
    ProcessingLog,
    Transcript,
    TranscriptSegment,
    UploadSession,
)


class MeetingFileInline(admin.TabularInline):
    model = MeetingFile
    extra = 0
    fields = ("version", "is_current", "original_filename", "media_kind", "size_bytes", "upload_status")
    readonly_fields = fields
    show_change_link = True


class TranscriptSegmentInline(admin.TabularInline):
    model = TranscriptSegment
    extra = 0
    fields = ("index", "start_time", "end_time", "speaker", "text", "confidence")


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "processing_status", "source", "duration_seconds", "is_archived", "created_at")
    list_filter = ("processing_status", "source", "is_archived", "language")
    search_fields = ("title", "description", "owner__email")
    inlines = [MeetingFileInline, TranscriptSegmentInline]
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(MeetingFile)
class MeetingFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "meeting", "version", "is_current", "media_kind", "size_bytes", "upload_status")
    list_filter = ("upload_status", "media_kind", "is_current")
    search_fields = ("original_filename", "checksum_sha256", "meeting__title")


@admin.register(MeetingJob)
class MeetingJobAdmin(admin.ModelAdmin):
    list_display = ("meeting", "background_job", "created_at")


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "original_filename", "received_bytes", "created_at")
    list_filter = ("status",)
    search_fields = ("original_filename", "user__email")


@admin.register(MeetingEvent)
class MeetingEventAdmin(admin.ModelAdmin):
    list_display = ("meeting", "event_type", "source", "message", "duration_ms", "created_at")
    list_filter = ("event_type", "source")
    search_fields = ("meeting__title", "message")


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ("meeting", "stage", "status", "duration_ms", "created_at")
    list_filter = ("stage", "status")


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("meeting", "detected_language", "word_count", "avg_confidence", "model_used", "is_edited", "created_at")
    list_filter = ("detected_language", "model_used", "provider", "is_edited")
    search_fields = ("meeting__title", "clean_text")


@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ("meeting", "version", "is_current", "provider", "model_used", "inference_ms", "created_at")
    list_filter = ("provider", "model_used", "is_current")
    search_fields = ("meeting__title", "executive_summary")


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "meeting", "created_at")
    search_fields = ("title", "meeting__title")


admin.site.register(MediaMetadata)
admin.site.register(AIOutput)
admin.site.register(ChatMessage)
admin.site.register(MessageCitation)
