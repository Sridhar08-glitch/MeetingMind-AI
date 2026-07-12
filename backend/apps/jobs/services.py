"""Engine-level operations for background jobs.

Domain-agnostic. Job creation/dispatch lives in :mod:`apps.jobs.manager`; this
module owns claiming and executing a job through the pipeline engine.
"""
from __future__ import annotations

import logging

from django.db import transaction

from apps.jobs.enums import JobStatus
from apps.jobs.models import BackgroundJob
from apps.jobs.pipeline.engine import PipelineEngine, PipelineOutcome

logger = logging.getLogger("meetingmind.processing")


def acquire(job_id: str, *, worker: str = "") -> BackgroundJob | None:
    """Atomically claim a job for execution (marks it RUNNING).

    Returns ``None`` if the job doesn't exist or isn't in a claimable state
    (already running, paused, cancelled, or finished) — preventing double-runs.
    """
    with transaction.atomic():
        job = BackgroundJob.objects.select_for_update().filter(id=job_id).first()
        if job is None:
            return None
        if job.status not in {JobStatus.QUEUED, JobStatus.RETRYING}:
            logger.info("Job %s not claimable (status=%s).", job_id, job.status)
            return None
        job.mark_running(worker=worker)
        return job


def execute_job(job_id: str, *, worker: str = "", config: dict | None = None) -> PipelineOutcome | None:
    """Claim and run a job through its pipeline. Safe to call more than once."""
    job = acquire(job_id, worker=worker)
    if job is None:
        return None
    engine = PipelineEngine()
    return engine.run(job, worker_id=worker, config=config)
