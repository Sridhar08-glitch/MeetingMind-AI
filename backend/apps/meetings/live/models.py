"""Live-recording session models — deliberately ISOLATED from ``Meeting``.

A live recording lives entirely in ``LiveMeetingSession`` (+ preview
``LiveTranscriptSegment`` rows) while in progress, so unfinished/abandoned
recordings never appear in the Meetings list. Only at **finalize** do we create a
real ``Meeting`` + ``MeetingFile`` and run the existing Phase 6–12 pipeline. This
also gives clean pause/resume and crash recovery.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class LiveSessionStatus(models.TextChoices):
    RECORDING = "recording", "Recording"
    PAUSED = "paused", "Paused"
    FINALIZING = "finalizing", "Finalizing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"


ACTIVE_LIVE_STATUSES = (LiveSessionStatus.RECORDING, LiveSessionStatus.PAUSED)


class LiveMeetingSession(BaseModel):
    """One in-progress live recording. Becomes a Meeting only at finalize."""

    class Meta(BaseModel.Meta):
        app_label = "meetings"
        indexes = [models.Index(fields=["owner", "status", "-created_at"])]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_sessions"
    )
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16, choices=LiveSessionStatus.choices,
        default=LiveSessionStatus.RECORDING, db_index=True,
    )
    source = models.CharField(max_length=32, blank=True)  # mic/screen/tab/webcam/…
    media_kind = models.CharField(max_length=16, blank=True)  # audio|video
    file_extension = models.CharField(max_length=8, default="webm")

    # Language config for this recording (the three independent concepts).
    meeting_language = models.CharField(max_length=16, blank=True)       # "" = auto-detect
    transcript_language = models.CharField(max_length=16, default="original")
    ai_language = models.CharField(max_length=16, blank=True)

    # Where the growing recording is stored (assembled on finalize).
    storage_key = models.CharField(max_length=512, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    bytes_received = models.BigIntegerField(default=0)
    duration_seconds = models.FloatField(default=0.0)
    # Live-transcription checkpoint: seconds already committed to preview segments.
    last_committed_time = models.FloatField(default=0.0)

    # Live AI preview (throttled) — canonical AI comes from the finalize pipeline.
    live_summary = models.TextField(blank=True)
    live_ai = models.JSONField(default=dict, blank=True)

    # Set only at finalize.
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="live_session",
    )
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"LiveSession {self.id} ({self.status})"


class LiveTranscriptSegment(BaseModel):
    """A preview transcript segment produced during a live recording.

    Lightweight and disposable — the canonical transcript is produced by the
    finalize pipeline against the full recording.
    """

    class Meta(BaseModel.Meta):
        app_label = "meetings"
        ordering = ("session", "index")
        indexes = [models.Index(fields=["session", "index"])]

    session = models.ForeignKey(
        LiveMeetingSession, on_delete=models.CASCADE, related_name="segments"
    )
    index = models.PositiveIntegerField()
    start_time = models.FloatField()
    end_time = models.FloatField()
    speaker = models.CharField(max_length=100, blank=True)
    text = models.TextField()
    translated_text = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
