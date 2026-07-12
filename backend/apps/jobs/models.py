"""Generic background-job models.

Intentionally decoupled from any domain (meetings, OCR, exports…). A job carries
a ``job_type``/``pipeline`` and an opaque JSON ``payload``; domain apps link their
own rows to a job (see ``apps.meetings.models.MeetingJob``). One engine, many
workloads.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from .enums import (
    JobLogLevel,
    JobPriority,
    JobStatus,
    JobType,
    TERMINAL_JOB_STATUSES,
)


class BackgroundJob(BaseModel):
    job_type = models.CharField(max_length=48, choices=JobType.choices, db_index=True)
    # Name of the registered pipeline this job runs (see apps.jobs.pipeline).
    pipeline = models.CharField(max_length=64, blank=True, db_index=True)

    status = models.CharField(
        max_length=32, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True
    )
    priority = models.IntegerField(
        choices=JobPriority.choices, default=JobPriority.NORMAL, db_index=True
    )

    # Live progress (0–100) and the stage currently executing.
    progress = models.PositiveSmallIntegerField(default=0)
    current_stage = models.CharField(max_length=64, blank=True)

    # Routing + worker identity (production-ready even in eager mode).
    queue_name = models.CharField(max_length=64, default="default", db_index=True)
    worker_id = models.CharField(max_length=128, blank=True)

    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    error_message = models.TextField(blank=True)
    stack_trace = models.TextField(blank=True)

    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)

    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    # Cooperative lock: a worker stamps these when it picks the job up.
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=128, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["job_type", "status"]),
            models.Index(fields=["status", "priority", "created_at"]),
            models.Index(fields=["pipeline", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_type}:{self.status} ({self.id})"

    # --- spec aliases ----------------------------------------------------
    @property
    def retry_count(self) -> int:
        return self.attempts

    @property
    def max_retries(self) -> int:
        return self.max_attempts

    @property
    def is_active(self) -> bool:
        return self.status not in TERMINAL_JOB_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES

    def _compute_duration(self) -> None:
        if self.started_at:
            end = self.finished_at or self.cancelled_at or timezone.now()
            self.duration_ms = int((end - self.started_at).total_seconds() * 1000)

    # --- transitions -----------------------------------------------------
    def mark_running(self, *, worker: str = "") -> None:
        self.status = JobStatus.RUNNING
        self.attempts = self.attempts + 1
        self.started_at = self.started_at or timezone.now()
        self.locked_at = timezone.now()
        self.locked_by = worker
        self.worker_id = worker or self.worker_id
        self.save(update_fields=[
            "status", "attempts", "started_at", "locked_at", "locked_by",
            "worker_id", "updated_at",
        ])

    def set_progress(self, progress: int, *, stage: str | None = None) -> None:
        self.progress = max(0, min(100, int(progress)))
        fields = ["progress", "updated_at"]
        if stage is not None:
            self.current_stage = stage
            fields.append("current_stage")
        self.save(update_fields=fields)

    def mark_succeeded(self, *, result: dict | None = None) -> None:
        self.status = JobStatus.SUCCEEDED
        self.result = result or {}
        self.progress = 100
        self.finished_at = timezone.now()
        self._compute_duration()
        self.locked_at = None
        self.locked_by = ""
        self.save(update_fields=[
            "status", "result", "progress", "finished_at", "duration_ms",
            "locked_at", "locked_by", "updated_at",
        ])

    def mark_failed(self, *, error: str, stack_trace: str = "", terminal: bool = False) -> None:
        self.error_message = error
        self.stack_trace = stack_trace
        self.finished_at = timezone.now()
        self._compute_duration()
        self.locked_at = None
        self.locked_by = ""
        # Retry until we exhaust the attempt budget (unless the error is terminal).
        can_retry = not terminal and self.attempts < self.max_attempts
        self.status = JobStatus.RETRYING if can_retry else JobStatus.FAILED
        self.save(update_fields=[
            "status", "error_message", "stack_trace", "finished_at", "duration_ms",
            "locked_at", "locked_by", "updated_at",
        ])

    def request_cancellation(self) -> None:
        """Ask a running job to stop; a queued job is cancelled immediately."""
        if self.status in {JobStatus.QUEUED, JobStatus.WAITING, JobStatus.PAUSED}:
            self.mark_cancelled()
        elif self.status in {JobStatus.RUNNING, JobStatus.RETRYING}:
            self.status = JobStatus.CANCELLATION_REQUESTED
            self.save(update_fields=["status", "updated_at"])

    def mark_cancelled(self) -> None:
        self.status = JobStatus.CANCELED
        self.cancelled_at = timezone.now()
        self._compute_duration()
        self.locked_at = None
        self.locked_by = ""
        self.save(update_fields=[
            "status", "cancelled_at", "duration_ms", "locked_at", "locked_by", "updated_at",
        ])

    def pause(self) -> None:
        if self.status in {JobStatus.QUEUED, JobStatus.WAITING, JobStatus.RUNNING, JobStatus.RETRYING}:
            self.status = JobStatus.PAUSED
            self.save(update_fields=["status", "updated_at"])

    def resume(self) -> None:
        if self.status == JobStatus.PAUSED:
            self.status = JobStatus.QUEUED
            self.save(update_fields=["status", "updated_at"])

    def is_cancellation_requested(self) -> bool:
        # Re-read the row so long-running stages see a cancel issued elsewhere.
        return (
            type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            == JobStatus.CANCELLATION_REQUESTED
        )


class JobLog(BaseModel):
    """Structured, per-stage log line for a background job."""

    job = models.ForeignKey(BackgroundJob, on_delete=models.CASCADE, related_name="job_logs")
    stage = models.CharField(max_length=64, blank=True)
    level = models.CharField(max_length=16, choices=JobLogLevel.choices, default=JobLogLevel.INFO)
    message = models.TextField(blank=True)
    progress = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["job", "created_at"]),
            models.Index(fields=["job", "stage"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.stage}: {self.message[:40]}"
