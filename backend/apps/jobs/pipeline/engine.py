"""The pipeline engine.

Runs a job's pipeline stage-by-stage in dependency order, with:

* **progress** updates + structured logs per stage,
* **idempotent resume** — completed stages are recorded on the job and skipped on
  a re-run, so retries never redo committed work,
* **cooperative cancellation** — checked between stages (and by stages internally),
* a **retry engine** — transient stage failures retry with exponential backoff and
  a recorded history; non-retryable failures (e.g. validation) fail immediately,
* **events** — every transition is published on the bus for decoupled subscribers.

The engine is domain-agnostic: it knows pipelines and stages, not meetings.
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass

from django.utils import timezone

from apps.common.storage import get_storage_service
from apps.jobs.enums import JobEvent, JobLogLevel, JobStatus
from apps.jobs.events import EventBus, event_bus
from apps.jobs.models import BackgroundJob

from .base import Stage, StageResult
from .cancellation import CancellationToken, JobCancelled
from .context import ProcessingContext
from .definitions import pipeline_registry
from .registry import stage_registry

logger = logging.getLogger("meetingmind.processing")

_DEFAULT_BASE_DELAY = 2.0  # seconds; grows exponentially per retry


@dataclass
class PipelineOutcome:
    status: str
    completed_stages: list[str]
    message: str = ""


class _StageFailed(Exception):
    """Internal signal: a stage exhausted retries; the job is already marked failed."""


class PipelineEngine:
    def __init__(self, *, registry=stage_registry, events: EventBus = event_bus) -> None:
        self.registry = registry
        self.events = events

    def run(self, job: BackgroundJob, *, worker_id: str = "", config: dict | None = None) -> PipelineOutcome:
        config = config or {}
        pipeline = pipeline_registry.get(job.pipeline)
        ctx = ProcessingContext(
            job=job,
            payload=job.payload,
            config=config,
            pipeline=pipeline,
            storage=get_storage_service(),
            events=self.events,
            cancellation=CancellationToken(job),
        )

        order = pipeline.ordered()
        total = len(order) or 1
        completed = set(job.metadata.get("completed_stages", []))

        self.events.publish(JobEvent.JOB_STARTED, job_id=str(job.id), pipeline=pipeline.name)
        ctx.log(f"Pipeline '{pipeline.name}' started.", level=JobLogLevel.INFO)

        for index, key in enumerate(order):
            # Graceful cancellation between stages.
            if ctx.cancellation.is_cancelled:
                job.mark_cancelled()
                self.events.publish(JobEvent.JOB_CANCELLED, job_id=str(job.id), stage=key)
                ctx.log("Job cancelled.", stage=key, level=JobLogLevel.WARNING)
                return PipelineOutcome(JobStatus.CANCELED, sorted(completed), "cancelled")

            # Idempotent resume: never redo a committed stage.
            if key in completed:
                self.events.publish(JobEvent.STAGE_SKIPPED, job_id=str(job.id), stage=key)
                continue

            stage = self.registry.get(key)
            job.set_progress(round(index / total * 100), stage=key)

            try:
                self._run_stage_with_retry(stage, ctx, config)
            except JobCancelled:
                job.mark_cancelled()
                self.events.publish(JobEvent.JOB_CANCELLED, job_id=str(job.id), stage=key)
                return PipelineOutcome(JobStatus.CANCELED, sorted(completed), "cancelled")
            except _StageFailed as exc:
                self.events.publish(JobEvent.JOB_FAILED, job_id=str(job.id), stage=key, error=str(exc))
                return PipelineOutcome(JobStatus.FAILED, sorted(completed), str(exc))

            completed.add(key)
            job.metadata["completed_stages"] = sorted(completed)
            job.save(update_fields=["metadata", "updated_at"])

        job.set_progress(100)
        job.mark_succeeded(result={"stages": sorted(completed)})
        self.events.publish(JobEvent.JOB_COMPLETED, job_id=str(job.id), pipeline=pipeline.name)
        ctx.log(f"Pipeline '{pipeline.name}' completed.", level=JobLogLevel.INFO)
        return PipelineOutcome(JobStatus.SUCCEEDED, sorted(completed), "completed")

    # --- retry engine ----------------------------------------------------
    def _run_stage_with_retry(self, stage: Stage, ctx: ProcessingContext, config: dict) -> StageResult:
        attempt = 0
        base_delay = config.get("retry_base_delay", _DEFAULT_BASE_DELAY)
        sleep_between = config.get("sleep_between_retries", False)

        while True:
            attempt += 1
            ctx.cancellation.check()
            self.events.publish(JobEvent.STAGE_STARTED, job_id=str(ctx.job.id), stage=stage.key, attempt=attempt)
            started = timezone.now()
            try:
                result = stage.run(ctx)
                duration_ms = int((timezone.now() - started).total_seconds() * 1000)
                if result.skipped:
                    ctx.log(f"{stage.name}: {result.message or 'skipped'}", stage=stage.key,
                            duration_ms=duration_ms)
                    self.events.publish(JobEvent.STAGE_SKIPPED, job_id=str(ctx.job.id), stage=stage.key)
                else:
                    ctx.log(f"{stage.name} completed. {result.message}".strip(), stage=stage.key,
                            duration_ms=duration_ms)
                    self.events.publish(JobEvent.STAGE_COMPLETED, job_id=str(ctx.job.id),
                                        stage=stage.key, duration_ms=duration_ms)
                return result
            except JobCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 — engine converts to retry/fail
                duration_ms = int((timezone.now() - started).total_seconds() * 1000)
                retryable = stage.should_retry(exc) and attempt <= stage.max_retries
                self._record_retry(ctx.job, stage.key, attempt, exc, retryable)
                ctx.log(f"{stage.name} failed (attempt {attempt}): {exc}", stage=stage.key,
                        level=JobLogLevel.ERROR, duration_ms=duration_ms)
                self.events.publish(JobEvent.STAGE_FAILED, job_id=str(ctx.job.id), stage=stage.key,
                                    error=str(exc), attempt=attempt, retryable=retryable)

                if not retryable:
                    # Stage retries are exhausted within this run, so this run is
                    # terminal (→ FAILED). Operators can still manually Retry the
                    # job, which resumes idempotently from completed stages.
                    ctx.job.mark_failed(
                        error=f"{stage.name}: {exc}",
                        stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                        terminal=True,
                    )
                    raise _StageFailed(f"{stage.name}: {exc}") from exc

                delay = base_delay * (2 ** (attempt - 1))
                self.events.publish(JobEvent.JOB_RETRY, job_id=str(ctx.job.id), stage=stage.key,
                                    attempt=attempt, delay_seconds=delay)
                if sleep_between and delay > 0:
                    time.sleep(delay)

    @staticmethod
    def _record_retry(job: BackgroundJob, stage_key: str, attempt: int, exc: Exception, retryable: bool) -> None:
        history = job.metadata.setdefault("retries", [])
        history.append({
            "stage": stage_key,
            "attempt": attempt,
            "reason": str(exc),
            "retryable": retryable,
        })
        job.save(update_fields=["metadata", "updated_at"])
