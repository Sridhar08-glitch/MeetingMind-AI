"""MediaImportSession — one in-flight import, ISOLATED from Meeting until done.

Mirrors the LiveMeetingSession pattern: an import that is downloading/failed/
cancelled never shows up in the Meetings list. Only when a local file exists and
``create_upload()`` succeeds is a real Meeting created and linked. This gives a
clean queue with live progress, duplicate detection, and cancellation.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class MediaImportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ANALYZING = "analyzing", "Analyzing"
    DOWNLOADING = "downloading", "Downloading"
    DOWNLOADED = "downloaded", "Downloaded"
    VALIDATING = "validating", "Validating"
    IMPORTING = "importing", "Importing"
    PROCESSING = "processing", "Processing"      # handed off to the meeting pipeline
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    BLOCKED = "blocked", "Blocked"               # private/DRM/unsafe URL — permanent


# Statuses that mean "still working" (used for the active-imports list + cancel).
ACTIVE_IMPORT_STATUSES = (
    MediaImportStatus.PENDING,
    MediaImportStatus.ANALYZING,
    MediaImportStatus.DOWNLOADING,
    MediaImportStatus.DOWNLOADED,
    MediaImportStatus.VALIDATING,
    MediaImportStatus.IMPORTING,
    MediaImportStatus.PROCESSING,
)

# Terminal failure/blocked states.
FAILED_IMPORT_STATUSES = (MediaImportStatus.FAILED, MediaImportStatus.BLOCKED)


class MediaImportSession(BaseModel):
    """One media import request and its live progress."""

    class Meta(BaseModel.Meta):
        app_label = "meetings"
        indexes = [
            models.Index(fields=["owner", "status", "-created_at"]),
            models.Index(fields=["owner", "source_url"]),
            models.Index(fields=["platform", "platform_id"]),
        ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="media_imports"
    )

    # Routing / origin.
    source_type = models.CharField(max_length=32, blank=True)   # MeetingSource value
    provider_id = models.CharField(max_length=32, blank=True)
    source_url = models.URLField(max_length=1024)
    platform = models.CharField(max_length=64, blank=True)
    platform_id = models.CharField(max_length=128, blank=True)  # native id (video id, …)
    episode_id = models.CharField(max_length=64, blank=True)    # chosen podcast episode
    episode_guid = models.CharField(max_length=512, blank=True)
    playlist = models.CharField(max_length=255, blank=True)

    status = models.CharField(
        max_length=16, choices=MediaImportStatus.choices,
        default=MediaImportStatus.PENDING, db_index=True,
    )
    progress = models.PositiveSmallIntegerField(default=0)       # 0–100
    bytes_downloaded = models.BigIntegerField(default=0)
    total_bytes = models.BigIntegerField(null=True, blank=True)

    # Provenance (populated by analyze).
    title = models.CharField(max_length=512, blank=True)
    author = models.CharField(max_length=255, blank=True)
    thumbnail_url = models.URLField(max_length=1024, blank=True)
    published_at = models.CharField(max_length=64, blank=True)
    license = models.CharField(max_length=128, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    media_kind = models.CharField(max_length=16, blank=True)    # audio|video
    requested_media = models.CharField(max_length=16, default="video")
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    importer_version = models.CharField(max_length=16, blank=True)

    # Language config carried onto the finished Meeting (same as live).
    meeting_language = models.CharField(max_length=16, blank=True)
    transcript_language = models.CharField(max_length=16, default="original")
    ai_language = models.CharField(max_length=16, blank=True)

    # How to handle an already-imported duplicate: reject/replace/keep_both/ignore
    on_duplicate = models.CharField(max_length=16, default="reject")

    # Set only once the import finishes.
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="import_session",
    )
    # Set when a duplicate is detected (so the UI can offer Skip / open existing).
    duplicate_meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=48, blank=True)

    def __str__(self) -> str:
        return f"MediaImport {self.id} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_IMPORT_STATUSES
