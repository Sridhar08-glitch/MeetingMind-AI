"""Keep the knowledge index fresh — re-index a meeting when its job completes."""
from __future__ import annotations

import logging

from apps.jobs.enums import JobEvent

logger = logging.getLogger("meetingmind.ai")


def on_job_completed(event: str, data: dict) -> None:
    from apps.meetings.models import MeetingJob

    link = (
        MeetingJob.objects.filter(background_job_id=data.get("job_id"))
        .select_related("meeting")
        .order_by("-created_at")
        .first()
    )
    if not link:
        return
    meeting = link.meeting
    try:
        from apps.knowledge.services.index import KnowledgeIndexService

        KnowledgeIndexService().index_meeting(meeting)
    except Exception:  # noqa: BLE001 — indexing must never break the job
        logger.exception("Knowledge indexing failed for meeting %s", link.meeting_id)
        return

    # Incremental, SCOPE-LIMITED executive materialization: only the affected
    # project snapshot + the org rollup are recomputed — never every project.
    try:
        from apps.knowledge.services import executive

        if meeting.project_id:
            executive.materialize_project(meeting.owner, meeting.project)
        executive.materialize_organization(meeting.owner)
    except Exception:  # noqa: BLE001 — materialization must never break the job
        logger.exception("Executive materialization failed for owner %s", meeting.owner_id)


def register(bus) -> None:
    bus.subscribe(JobEvent.JOB_COMPLETED, on_job_completed)
