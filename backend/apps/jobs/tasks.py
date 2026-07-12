"""Celery task entry points for the job engine.

There is a single generic task — :func:`run_pipeline_job` — that every pipeline
(meeting processing, and later OCR/exports/email/…) flows through. Retries are
handled by the engine's retry layer, so the Celery task itself does not retry
(``max_retries=0``); ``acks_late`` gives at-least-once delivery once a real
broker is enabled.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("meetingmind.processing")


@shared_task(
    bind=True,
    name="jobs.run_pipeline_job",
    acks_late=True,
    max_retries=0,
    ignore_result=True,
)
def run_pipeline_job(self, job_id: str) -> None:
    """Execute a queued job through the pipeline engine."""
    from apps.jobs.services import execute_job

    worker = getattr(self.request, "hostname", "") or "eager"
    execute_job(job_id, worker=worker)
