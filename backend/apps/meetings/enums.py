"""Enumerations shared across the meetings domain.

Upload state and processing state are deliberately *separate* lifecycles — a file
can be fully uploaded and verified while its transcription/AI processing hasn't
started, failed, or is retrying. Conflating them (as a single ``status``) hides
where a meeting actually is.
"""
from __future__ import annotations

from django.db import models


class UploadStatus(models.TextChoices):
    """Lifecycle of a single uploaded file (a MeetingFile version)."""

    PENDING = "pending", "Pending"        # session opened, no bytes yet
    UPLOADING = "uploading", "Uploading"  # bytes arriving
    UPLOADED = "uploaded", "Uploaded"     # bytes received in full
    STORED = "stored", "Stored"           # persisted to storage
    VERIFIED = "verified", "Verified"     # validated + checksummed
    FAILED = "failed", "Failed"


class ProcessingStatus(models.TextChoices):
    """Lifecycle of the transcription/AI pipeline for a meeting."""

    PENDING = "pending", "Pending"        # nothing queued yet
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    RETRYING = "retrying", "Retrying"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


# Processing states that mean "a run is in flight" — used by the processing lock.
ACTIVE_PROCESSING_STATUSES = (
    ProcessingStatus.QUEUED,
    ProcessingStatus.RUNNING,
    ProcessingStatus.RETRYING,
)


class MeetingSource(models.TextChoices):
    """Where the recording originated. Stored now to ease future integrations."""

    MANUAL_UPLOAD = "manual_upload", "Manual Upload"
    LIVE = "live", "Live Recording"
    SCREEN_RECORDING = "screen_recording", "Screen Recording"
    WEBCAM_RECORDING = "webcam_recording", "Webcam Recording"
    ZOOM = "zoom", "Zoom"
    GOOGLE_MEET = "google_meet", "Google Meet"
    MS_TEAMS = "ms_teams", "Microsoft Teams"
    MOBILE_RECORDING = "mobile_recording", "Mobile Recording"
    VOICE_RECORDER = "voice_recorder", "Voice Recorder"
    # Phase 14 — universal media import. The concrete platform (YouTube/Vimeo/…)
    # is kept in Meeting.source_metadata so these stay generic, not per-site.
    PUBLIC_VIDEO = "public_video", "Public Video"
    PODCAST = "podcast", "Podcast"
    RSS_FEED = "rss_feed", "RSS Feed"
    DIRECT_URL = "direct_url", "Direct URL"
    BATCH_IMPORT = "batch_import", "Batch Import"
    OTHER = "other", "Other"


class MediaKind(models.TextChoices):
    AUDIO = "audio", "Audio"
    VIDEO = "video", "Video"


class UploadSessionStatus(models.TextChoices):
    """Lifecycle of an upload session (foundation for chunked/resumable uploads)."""

    INITIATED = "initiated", "Initiated"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    ABORTED = "aborted", "Aborted"
    EXPIRED = "expired", "Expired"


class EventSource(models.TextChoices):
    """Who/what produced a timeline event."""

    SYSTEM = "system", "System"
    USER = "user", "User"
    API = "api", "API"
    WORKER = "worker", "Worker"


class MeetingEventType(models.TextChoices):
    """Human-facing timeline entries, distinct from stage-level ProcessingLog."""

    UPLOAD_STARTED = "upload_started", "Upload started"
    UPLOAD_COMPLETED = "upload_completed", "Upload completed"
    FILE_STORED = "file_stored", "File stored"
    VALIDATION_STARTED = "validation_started", "Validation started"
    VALIDATION_COMPLETED = "validation_completed", "Validation completed"
    VALIDATION_FAILED = "validation_failed", "Validation failed"
    DUPLICATE_DETECTED = "duplicate_detected", "Duplicate detected"
    NEW_VERSION = "new_version", "New version uploaded"
    AUDIO_EXTRACTED = "audio_extracted", "Audio extracted"
    QUEUED = "queued", "Queued for processing"
    PROCESSING_STARTED = "processing_started", "Processing started"
    PROCESSING_COMPLETED = "processing_completed", "Processing completed"
    PROCESSING_FAILED = "processing_failed", "Processing failed"


class DuplicateAction(models.TextChoices):
    """What to do when an identical file (by checksum) already exists."""

    REJECT = "reject", "Reject"        # refuse and report (default)
    REPLACE = "replace", "Replace"     # add a new version to the existing meeting
    KEEP_BOTH = "keep_both", "Keep both"  # create a separate meeting anyway
    IGNORE = "ignore", "Ignore"        # no-op, return the existing meeting


class ProcessingStage(models.TextChoices):
    """The 12 pipeline stages described in the project brief."""

    UPLOAD = "upload", "Upload"
    FILE_VALIDATION = "file_validation", "File Validation"
    AUDIO_EXTRACTION = "audio_extraction", "Audio Extraction"
    AUDIO_CONVERSION = "audio_conversion", "Audio Conversion"
    SPEECH_RECOGNITION = "speech_recognition", "Speech Recognition"
    TRANSCRIPT_CLEANUP = "transcript_cleanup", "Transcript Cleanup"
    CHUNKING = "chunking", "Chunking"
    AI_SUMMARY = "ai_summary", "AI Summary"
    ACTION_ITEMS = "action_items", "Action Items"
    DECISIONS = "decisions", "Decisions"
    KEYWORDS = "keywords", "Keywords"
    EXPORT = "export", "Export"


class StageStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class AIOutputKind(models.TextChoices):
    EXECUTIVE_SUMMARY = "executive_summary", "Executive Summary"
    DETAILED_SUMMARY = "detailed_summary", "Detailed Summary"
    BULLET_SUMMARY = "bullet_summary", "Bullet Summary"
    MEETING_MINUTES = "meeting_minutes", "Meeting Minutes"
    ACTION_ITEMS = "action_items", "Action Items"
    DECISIONS = "decisions", "Decisions"
    RISKS = "risks", "Risks"
    FOLLOW_UPS = "follow_ups", "Follow Ups"
    DEADLINES = "deadlines", "Deadlines"
    KEYWORDS = "keywords", "Keywords"


class ChatRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class SpeakerEmbeddingKind(models.TextChoices):
    """Kinds of voice embedding persisted per speaker (Phase 15).

    All three are generated at processing time so Phase 15B VoicePerson matching
    never needs to re-embed audio:
      - ``segment``  — one embedding per contributing transcript segment
      - ``centroid`` — the L2-normalized mean (mirrors ``Speaker.embedding``)
      - ``best_n``   — the highest-quality representative segment embeddings
    """

    SEGMENT = "segment", "Segment"
    CENTROID = "centroid", "Centroid"
    BEST_N = "best_n", "Best-N Representative"
