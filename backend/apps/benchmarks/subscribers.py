"""Keep benchmark recordings in sync with the meeting pipeline.

When a meeting linked to a benchmark recording finishes processing, the recording
becomes READY (its transcript + diarization are available to score); if it fails,
the recording is marked FAILED. Best-effort — never breaks the job.
"""
from __future__ import annotations

import logging

from apps.jobs.enums import JobEvent

from .enums import RecordingStatus

logger = logging.getLogger("meetingmind.ai")


def _update_recordings(job_id, status: str, detail: str = "") -> None:
    from apps.meetings.models import MeetingJob

    from .models import BenchmarkRecording

    link = (
        MeetingJob.objects.filter(background_job_id=job_id)
        .select_related("meeting")
        .order_by("-created_at")
        .first()
    )
    if not link:
        return
    meeting = link.meeting
    # Public recordings imported via Phase 14 don't know their meeting until the
    # import lands — backfill the link from the import session, then set status.
    BenchmarkRecording.objects.filter(import_session__meeting=meeting, meeting__isnull=True).update(
        meeting=meeting
    )
    BenchmarkRecording.objects.filter(meeting=meeting).update(status=status, status_detail=detail)


def on_job_completed(event: str, data: dict) -> None:
    try:
        _update_recordings(data.get("job_id"), RecordingStatus.READY)
    except Exception:  # noqa: BLE001 — must never break the job
        logger.exception("Benchmark recording sync (completed) failed")


def on_job_failed(event: str, data: dict) -> None:
    try:
        _update_recordings(data.get("job_id"), RecordingStatus.FAILED, "pipeline failed")
    except Exception:  # noqa: BLE001
        logger.exception("Benchmark recording sync (failed) failed")


def register(bus) -> None:
    bus.subscribe(JobEvent.JOB_COMPLETED, on_job_completed)
    if hasattr(JobEvent, "JOB_FAILED"):
        bus.subscribe(JobEvent.JOB_FAILED, on_job_failed)
