"""Read-side helpers for the meetings domain."""
from __future__ import annotations

from django.db.models import Avg, Count, QuerySet, Sum

from apps.accounts.models import User
from apps.jobs.enums import ACTIVE_JOB_STATUSES
from apps.meetings.enums import ProcessingStatus
from apps.meetings.models import Meeting, MeetingJob


def meetings_for_owner(owner: User) -> QuerySet[Meeting]:
    """All non-deleted meetings owned by ``owner`` (prefetch files for list/detail)."""
    return (
        Meeting.objects.filter(owner=owner)
        .select_related("owner")
        .prefetch_related("files", "files__media_metadata")
    )


def dashboard_stats(owner: User) -> dict:
    """Aggregate metrics for the owner's dashboard."""
    qs = Meeting.objects.filter(owner=owner)
    aggregates = qs.aggregate(
        total=Count("id"),
        total_seconds=Sum("duration_seconds"),
        avg_seconds=Avg("duration_seconds"),
    )
    by_status = {
        row["processing_status"]: row["n"]
        for row in qs.values("processing_status").annotate(n=Count("id"))
    }

    active_jobs = MeetingJob.objects.filter(
        meeting__owner=owner, background_job__status__in=ACTIVE_JOB_STATUSES
    ).count()

    total_seconds = aggregates["total_seconds"] or 0
    avg_seconds = aggregates["avg_seconds"] or 0
    return {
        "total_meetings": aggregates["total"] or 0,
        "completed_meetings": by_status.get(ProcessingStatus.COMPLETED, 0),
        "processing_meetings": (
            by_status.get(ProcessingStatus.RUNNING, 0)
            + by_status.get(ProcessingStatus.QUEUED, 0)
            + by_status.get(ProcessingStatus.RETRYING, 0)
        ),
        "failed_meetings": by_status.get(ProcessingStatus.FAILED, 0),
        "active_jobs": active_jobs,
        "total_hours_processed": round(total_seconds / 3600, 2),
        "average_duration_minutes": round(avg_seconds / 60, 2),
        "status_breakdown": by_status,
    }
