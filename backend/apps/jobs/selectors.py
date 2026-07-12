"""Read-side helpers + metrics for background jobs."""
from __future__ import annotations

from django.db.models import Avg, Count, Max, Q, QuerySet

from apps.jobs.enums import ACTIVE_JOB_STATUSES, JobStatus
from apps.jobs.models import BackgroundJob


def jobs_for_user(user) -> QuerySet[BackgroundJob]:
    """Jobs a user may see: their own, or everything for staff/admins."""
    qs = BackgroundJob.objects.all()
    if not getattr(user, "is_staff", False):
        qs = qs.filter(created_by=user)
    return qs


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def job_metrics(user) -> dict:
    """Aggregate job metrics scoped to what ``user`` may see."""
    qs = jobs_for_user(user)

    by_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
    total = sum(by_status.values())
    completed = by_status.get(JobStatus.SUCCEEDED, 0)
    failed = by_status.get(JobStatus.FAILED, 0)
    cancelled = by_status.get(JobStatus.CANCELED, 0)
    running = by_status.get(JobStatus.RUNNING, 0)
    queued = by_status.get(JobStatus.QUEUED, 0) + by_status.get(JobStatus.WAITING, 0)

    finished = qs.filter(status__in=[JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED])
    duration = finished.aggregate(avg=Avg("duration_ms"), longest=Max("duration_ms"))
    retried = qs.filter(attempts__gt=1).count()

    # Per-pipeline breakdown.
    pipelines = []
    for row in (
        qs.values("pipeline")
        .annotate(
            total=Count("id"),
            succeeded=Count("id", filter=Q(status=JobStatus.SUCCEEDED)),
            failed=Count("id", filter=Q(status=JobStatus.FAILED)),
            avg_ms=Avg("duration_ms"),
        )
        .order_by("-total")
    ):
        pipelines.append({
            "pipeline": row["pipeline"] or "(none)",
            "total": row["total"],
            "succeeded": row["succeeded"],
            "failed": row["failed"],
            "avg_runtime_ms": round(row["avg_ms"] or 0),
            "success_rate": _rate(row["succeeded"], row["succeeded"] + row["failed"]),
        })

    return {
        "total_jobs": total,
        "queued_jobs": queued,
        "running_jobs": running,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "cancelled_jobs": cancelled,
        "active_jobs": qs.filter(status__in=ACTIVE_JOB_STATUSES).count(),
        "success_rate": _rate(completed, completed + failed),
        "failure_rate": _rate(failed, completed + failed),
        "retry_rate": _rate(retried, total),
        "average_runtime_ms": round(duration["avg"] or 0),
        "longest_runtime_ms": duration["longest"] or 0,
        "status_breakdown": by_status,
        "pipelines": pipelines,
    }
