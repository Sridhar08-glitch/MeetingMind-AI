"""Bridge generic job events → meeting processing status + timeline.

The engine is domain-agnostic; it publishes lifecycle events. These subscribers
translate them into `Meeting.processing_status` transitions and human-facing
`MeetingEvent`s — so the meetings domain reacts without the engine knowing it
exists. Other domains subscribe the same way.
"""
from __future__ import annotations

import logging

from apps.jobs.enums import JobEvent
from apps.meetings.enums import EventSource, MeetingEventType, ProcessingStatus

logger = logging.getLogger("meetingmind.processing")


def _meeting_for_job(job_id: str):
    from apps.meetings.models import MeetingJob

    link = (
        MeetingJob.objects.filter(background_job_id=job_id)
        .select_related("meeting")
        .order_by("-created_at")
        .first()
    )
    return link.meeting if link else None


def _set_status(meeting, status: str, event_type: str, message: str) -> None:
    from apps.meetings.services.uploads import record_event

    meeting.processing_status = status
    meeting.save(update_fields=["processing_status", "updated_at"])
    record_event(meeting, event_type, message, source=EventSource.WORKER)


def on_job_started(event: str, data: dict) -> None:
    meeting = _meeting_for_job(data.get("job_id"))
    if meeting:
        _set_status(meeting, ProcessingStatus.RUNNING,
                    MeetingEventType.PROCESSING_STARTED, "Processing started.")


def _resolve_import_session(meeting, status: str) -> None:
    """Flip a linked media-import session to its terminal state (Phase 14)."""
    from apps.meetings.models import MediaImportSession, MediaImportStatus

    (MediaImportSession.objects
        .filter(meeting=meeting, status=MediaImportStatus.PROCESSING)
        .update(status=status, updated_at=meeting.updated_at))


def on_job_completed(event: str, data: dict) -> None:
    meeting = _meeting_for_job(data.get("job_id"))
    if meeting:
        _set_status(meeting, ProcessingStatus.COMPLETED,
                    MeetingEventType.PROCESSING_COMPLETED, "Processing completed.")
        from apps.meetings.models import MediaImportStatus
        _resolve_import_session(meeting, MediaImportStatus.COMPLETED)


def on_job_failed(event: str, data: dict) -> None:
    meeting = _meeting_for_job(data.get("job_id"))
    if meeting:
        _set_status(meeting, ProcessingStatus.FAILED,
                    MeetingEventType.PROCESSING_FAILED,
                    f"Processing failed: {data.get('error', 'unknown error')}.")
        from apps.meetings.models import MediaImportStatus
        _resolve_import_session(meeting, MediaImportStatus.FAILED)


def on_job_cancelled(event: str, data: dict) -> None:
    meeting = _meeting_for_job(data.get("job_id"))
    if meeting:
        _set_status(meeting, ProcessingStatus.CANCELED,
                    MeetingEventType.PROCESSING_FAILED, "Processing cancelled.")


def register(bus) -> None:
    bus.subscribe(JobEvent.JOB_STARTED, on_job_started)
    bus.subscribe(JobEvent.JOB_COMPLETED, on_job_completed)
    bus.subscribe(JobEvent.JOB_FAILED, on_job_failed)
    bus.subscribe(JobEvent.JOB_CANCELLED, on_job_cancelled)
