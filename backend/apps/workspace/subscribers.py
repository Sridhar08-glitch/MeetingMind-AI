"""Materialize workspace entities when an AI job completes.

Subscribes to the generic job Event Bus (no meetings-pipeline changes): whenever a
meeting-linked job finishes and a current AI analysis exists, its outputs are
turned into managed Task/Decision/Risk/Issue/FollowUp records.
"""
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
    analysis = meeting.analyses.filter(is_current=True).order_by("-version").first()
    if analysis is None:
        return
    try:
        from apps.workspace.services.materialize import materialize

        materialize(meeting, analysis)
    except Exception:  # noqa: BLE001 — never break the job on materialization
        logger.exception("Workspace materialization failed for meeting %s", meeting.id)


def register(bus) -> None:
    bus.subscribe(JobEvent.JOB_COMPLETED, on_job_completed)
