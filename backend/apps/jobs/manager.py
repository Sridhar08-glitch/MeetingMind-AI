"""JobManager — the single seam for all Celery interaction.

Every enqueue/dispatch/cancel/retry goes through here, so switching from eager
mode to a real Redis-backed worker is a *configuration* change only
(``CELERY_TASK_ALWAYS_EAGER=False`` + broker settings) — no code changes. Task
signatures, queue names and broker priorities are already production-shaped.
"""
from __future__ import annotations

import logging

from django.db import transaction

from apps.jobs.enums import JobEvent, JobPriority, JobStatus, JobType
from apps.jobs.events import event_bus
from apps.jobs.models import BackgroundJob

logger = logging.getLogger("meetingmind.processing")

# Map our semantic priority (lower = more important) to a Celery/Redis broker
# priority (0–9, higher = more important).
_BROKER_PRIORITY = {
    JobPriority.CRITICAL: 9,
    JobPriority.HIGH: 7,
    JobPriority.NORMAL: 5,
    JobPriority.LOW: 2,
}

# Default queue routing per job type (real queues once Redis is enabled).
_QUEUE_FOR_TYPE = {
    JobType.MEETING_PROCESSING: "media",
    JobType.AI_SUMMARIZATION: "ai",
    JobType.VIDEO_PROCESSING: "media",
    JobType.THUMBNAIL: "media",
    JobType.OCR: "media",
    JobType.IMAGE_GENERATION: "ai",
    JobType.REPORT_EXPORT: "exports",
    JobType.EMAIL: "notifications",
    JobType.CLEANUP: "maintenance",
}


class JobManager:
    def __init__(self, *, events=event_bus) -> None:
        self.events = events

    def broker_priority(self, priority: int) -> int:
        return _BROKER_PRIORITY.get(priority, 5)

    def queue_for(self, job_type: str) -> str:
        return _QUEUE_FOR_TYPE.get(job_type, "default")

    # --- create + dispatch ----------------------------------------------
    def enqueue(
        self,
        job_type: str,
        *,
        pipeline: str = "",
        payload: dict | None = None,
        priority: int = JobPriority.NORMAL,
        queue: str | None = None,
        max_attempts: int = 3,
        actor=None,
        dispatch: bool = True,
    ) -> BackgroundJob:
        job = BackgroundJob(
            job_type=job_type,
            pipeline=pipeline or job_type,
            payload=payload or {},
            priority=priority,
            queue_name=queue or self.queue_for(job_type),
            max_attempts=max_attempts,
            status=JobStatus.QUEUED,
        )
        if actor is not None:
            job.set_acting_user(actor)
        job.save()

        self.events.publish(JobEvent.JOB_CREATED, job_id=str(job.id), job_type=job_type)
        self.events.publish(JobEvent.JOB_QUEUED, job_id=str(job.id), queue=job.queue_name)
        logger.info("Enqueued job %s (%s -> queue %s, priority %s).",
                    job.id, job_type, job.queue_name, job.get_priority_display())
        if dispatch:
            self.dispatch(job)
        return job

    def dispatch(self, job: BackgroundJob) -> None:
        """Send the job to a worker. Deferred to on_commit so the row is visible.

        In eager mode ``apply_async`` runs synchronously *after* the surrounding
        transaction commits; with Redis it hands off to a real worker. Same call.
        """
        from apps.jobs.tasks import run_pipeline_job

        job_id = str(job.id)
        queue = job.queue_name
        priority = self.broker_priority(job.priority)

        def _send():
            run_pipeline_job.apply_async(args=[job_id], queue=queue, priority=priority)

        transaction.on_commit(_send)

    # --- controls --------------------------------------------------------
    def cancel(self, job: BackgroundJob) -> None:
        job.request_cancellation()

    def pause(self, job: BackgroundJob) -> None:
        job.pause()

    def resume(self, job: BackgroundJob) -> None:
        job.resume()
        if job.status == JobStatus.QUEUED:
            self.dispatch(job)

    def retry(self, job: BackgroundJob) -> None:
        """Re-queue a failed/cancelled job. Idempotent resume skips done stages."""
        job.status = JobStatus.QUEUED
        job.error_message = ""
        job.stack_trace = ""
        job.finished_at = None
        job.cancelled_at = None
        job.save(update_fields=["status", "error_message", "stack_trace", "finished_at", "cancelled_at", "updated_at"])
        self.events.publish(JobEvent.JOB_QUEUED, job_id=str(job.id), queue=job.queue_name)
        self.dispatch(job)

    def requeue(self, job: BackgroundJob) -> None:
        """Full re-run from scratch (clears completed-stage bookkeeping)."""
        job.metadata.pop("completed_stages", None)
        job.progress = 0
        job.save(update_fields=["metadata", "progress", "updated_at"])
        self.retry(job)


job_manager = JobManager()
