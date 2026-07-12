"""Unit tests for the job engine, pipeline engine, retry, cancellation, events."""
import pytest

from apps.jobs.enums import JobEvent, JobPriority, JobStatus, JobType
from apps.jobs.events import event_bus
from apps.jobs.manager import job_manager
from apps.jobs.models import BackgroundJob, JobLog
from apps.jobs.pipeline.definitions import PipelineDefinition, pipeline_registry
from apps.jobs.services import acquire, execute_job

from . import stages as S

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_counts():
    S.reset_counts()
    yield


def _job(pipeline: str, **kw) -> BackgroundJob:
    return job_manager.enqueue(
        JobType.MEETING_PROCESSING, pipeline=pipeline, dispatch=False, **kw
    )


# --- registry & definitions -------------------------------------------------
def test_registry_discovers_stages_and_pipeline():
    from apps.jobs.pipeline import stage_registry

    assert stage_registry.has("t_a")
    assert pipeline_registry.has("t_linear")


def test_pipeline_topological_order_with_branching():
    defn = pipeline_registry.get("t_branch")
    order = defn.ordered()
    # a first; d after both b and c; e last.
    assert order[0] == "t_a"
    assert order.index("t_d") > order.index("t_b")
    assert order.index("t_d") > order.index("t_c")
    assert order[-1] == "t_e"


def test_cycle_is_rejected():
    with pytest.raises(ValueError, match="cycle"):
        PipelineDefinition("bad", ["x", "y"], {"x": ["y"], "y": ["x"]}).ordered()


# --- engine happy path ------------------------------------------------------
def test_linear_pipeline_completes_and_logs():
    job = _job("t_linear")
    outcome = execute_job(str(job.id), worker="w1")
    job.refresh_from_db()
    assert outcome.status == JobStatus.SUCCEEDED
    assert job.status == JobStatus.SUCCEEDED
    assert job.progress == 100
    assert job.metadata["completed_stages"] == ["t_a", "t_b", "t_c"]
    assert job.duration_ms is not None
    # A structured log line per stage plus start/finish.
    assert JobLog.objects.filter(job=job).count() >= 3


def test_branching_pipeline_runs_all_stages():
    job = _job("t_branch")
    execute_job(str(job.id))
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert set(job.metadata["completed_stages"]) == {"t_a", "t_b", "t_c", "t_d", "t_e"}


# --- retry engine -----------------------------------------------------------
def test_transient_failure_retries_then_succeeds():
    job = _job("t_flaky")
    execute_job(str(job.id), config={"flaky_fail_times": 2})
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    # Flaky ran 3 times (2 failures + 1 success); retries recorded.
    assert S.RUN_COUNTS["t_flaky"] == 3
    assert len(job.metadata.get("retries", [])) == 2


def test_transient_failure_exhausts_retries_and_fails():
    job = _job("t_flaky")
    execute_job(str(job.id), config={"flaky_fail_times": 99})
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert "t_a" in job.metadata["completed_stages"]
    assert "t_flaky" not in job.metadata["completed_stages"]


def test_non_retryable_failure_is_not_retried():
    job = _job("t_fatal")
    execute_job(str(job.id))
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert S.RUN_COUNTS["t_fatal"] == 1  # never retried
    assert job.stack_trace


# --- idempotent resume ------------------------------------------------------
def test_retry_resumes_without_rerunning_completed_stages():
    job = _job("t_flaky")
    execute_job(str(job.id), config={"flaky_fail_times": 99})  # fails at t_flaky
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert S.RUN_COUNTS["t_a"] == 1

    # Re-queue and run again with the flaky stage now healthy.
    job.status = JobStatus.QUEUED
    job.save(update_fields=["status"])
    execute_job(str(job.id), config={"flaky_fail_times": 0})
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    # t_a was already complete → not re-run on resume.
    assert S.RUN_COUNTS["t_a"] == 1


# --- cancellation -----------------------------------------------------------
def test_running_job_cancels_mid_pipeline():
    job = _job("t_cancel")
    outcome = execute_job(str(job.id))
    job.refresh_from_db()
    assert outcome.status == JobStatus.CANCELED
    assert job.status == JobStatus.CANCELED
    assert job.cancelled_at is not None
    assert "t_a" in job.metadata["completed_stages"]
    assert "t_c" not in job.metadata["completed_stages"]


def test_cancel_queued_job_is_immediate():
    job = _job("t_linear")
    job_manager.cancel(job)
    job.refresh_from_db()
    assert job.status == JobStatus.CANCELED


# --- concurrency lock -------------------------------------------------------
def test_acquire_prevents_double_run():
    job = _job("t_linear")
    claimed = acquire(str(job.id), worker="w1")
    assert claimed is not None and claimed.status == JobStatus.RUNNING
    assert acquire(str(job.id)) is None  # already running


# --- event bus --------------------------------------------------------------
def test_event_bus_publishes_lifecycle_events():
    seen = []
    handler = lambda event, data: seen.append(event)  # noqa: E731
    for ev in (JobEvent.JOB_STARTED, JobEvent.STAGE_COMPLETED, JobEvent.JOB_COMPLETED):
        event_bus.subscribe(ev, handler)

    job = _job("t_linear")
    execute_job(str(job.id))
    assert JobEvent.JOB_STARTED in seen
    assert JobEvent.STAGE_COMPLETED in seen
    assert JobEvent.JOB_COMPLETED in seen


# --- manager priority/queue routing ----------------------------------------
def test_enqueue_sets_queue_and_priority():
    job = job_manager.enqueue(
        JobType.MEETING_PROCESSING, pipeline="t_linear", priority=JobPriority.CRITICAL, dispatch=False
    )
    assert job.queue_name == "media"  # meeting_processing routes to media
    assert job_manager.broker_priority(job.priority) == 9
