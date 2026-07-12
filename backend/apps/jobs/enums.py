"""Enumerations for the generic background-job engine."""
from __future__ import annotations

from django.db import models


class JobType(models.TextChoices):
    """The kind of work a job represents.

    Deliberately open-ended: the engine is domain-agnostic so the same table can
    later drive OCR, image generation, report exports, email sending, etc.
    """

    MEETING_PROCESSING = "meeting_processing", "Meeting Processing"
    AI_SUMMARIZATION = "ai_summarization", "AI Summarization"
    # Reserved for future reuse (no handlers yet):
    OCR = "ocr", "OCR"
    IMAGE_GENERATION = "image_generation", "Image Generation"
    REPORT_EXPORT = "report_export", "Report Export"
    EMAIL = "email", "Email"
    VIDEO_PROCESSING = "video_processing", "Video Processing"
    THUMBNAIL = "thumbnail", "Thumbnail Generation"
    CLEANUP = "cleanup", "Cleanup"


class JobStatus(models.TextChoices):
    """Lifecycle of a background job (distinct from any upload lifecycle).

    Existing values (queued/running/retrying/succeeded/failed/canceled) are kept
    stable for backward compatibility; the ``succeeded`` label reads as
    "Completed" per the Phase 5 spec.
    """

    QUEUED = "queued", "Queued"
    WAITING = "waiting", "Waiting"                                  # blocked on a dependency
    RUNNING = "running", "Running"
    RETRYING = "retrying", "Retrying"
    PAUSED = "paused", "Paused"
    CANCELLATION_REQUESTED = "cancellation_requested", "Cancellation Requested"
    CANCELED = "canceled", "Cancelled"
    SUCCEEDED = "succeeded", "Completed"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class JobPriority(models.IntegerChoices):
    """Lower value = higher priority (runs first / higher broker priority)."""

    CRITICAL = 10, "Critical"
    HIGH = 50, "High"
    NORMAL = 100, "Normal"
    LOW = 200, "Low"


# Terminal states — the job is done and holds no slot.
TERMINAL_JOB_STATUSES = (
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.EXPIRED,
)

# Active states — the job is in flight and blocks a second run for the same target.
ACTIVE_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.WAITING,
    JobStatus.RUNNING,
    JobStatus.RETRYING,
    JobStatus.PAUSED,
    JobStatus.CANCELLATION_REQUESTED,
)


class JobLogLevel(models.TextChoices):
    DEBUG = "debug", "Debug"
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class JobEvent(models.TextChoices):
    """Event-bus topics published across the job lifecycle."""

    JOB_CREATED = "job_created", "Job created"
    JOB_QUEUED = "job_queued", "Job queued"
    JOB_STARTED = "job_started", "Job started"
    STAGE_STARTED = "stage_started", "Stage started"
    STAGE_COMPLETED = "stage_completed", "Stage completed"
    STAGE_FAILED = "stage_failed", "Stage failed"
    STAGE_SKIPPED = "stage_skipped", "Stage skipped"
    JOB_RETRY = "job_retry", "Job retry"
    JOB_CANCELLED = "job_cancelled", "Job cancelled"
    JOB_COMPLETED = "job_completed", "Job completed"
    JOB_FAILED = "job_failed", "Job failed"
