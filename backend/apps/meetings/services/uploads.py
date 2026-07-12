"""Meeting upload orchestration.

Owns the whole upload workflow and every state change. The view validates the
request shape and translates the typed :class:`UploadError` this module raises.

Happy path (single-shot upload)::

    open UploadSession → validate → [duplicate policy] → create/target Meeting
      → store MeetingFile version (storage service) → probe metadata
      → record timeline → acquire processing lock → enqueue BackgroundJob
      → close UploadSession

Transcription is NOT run here — we enqueue a job and return immediately.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.common.storage import get_storage_service
from apps.jobs.enums import ACTIVE_JOB_STATUSES, JobType
from apps.jobs.manager import job_manager
from apps.meetings.enums import (
    ACTIVE_PROCESSING_STATUSES,
    DuplicateAction,
    EventSource,
    MeetingEventType,
    MeetingSource,
    ProcessingStatus,
    UploadSessionStatus,
    UploadStatus,
)
from apps.meetings.models import (
    MediaMetadata,
    Meeting,
    MeetingEvent,
    MeetingFile,
    MeetingJob,
    UploadSession,
)
from apps.meetings.services.validators import (
    ValidationReport,
    probe_duration_seconds,
    probe_media_metadata,
    validate_upload,
)

logger = logging.getLogger("meetingmind")
processing_logger = logging.getLogger("meetingmind.processing")


class UploadError(Exception):
    """A typed upload failure the view renders into the standard error envelope."""

    def __init__(self, message: str, *, code: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}


@dataclass
class UploadOutcome:
    meeting: Meeting
    file: MeetingFile | None
    report: ValidationReport
    session: UploadSession
    created: bool  # False when an IGNORE no-op returned an existing meeting


# --- timeline ---------------------------------------------------------------
def record_event(
    meeting: Meeting,
    event_type: str,
    message: str = "",
    *,
    source: str = EventSource.SYSTEM,
    actor: User | None = None,
    duration_ms: int | None = None,
    **details,
) -> MeetingEvent:
    event = MeetingEvent(
        meeting=meeting,
        event_type=event_type,
        source=source,
        message=message,
        details=details or {},
        duration_ms=duration_ms,
    )
    if actor is not None:
        event.set_acting_user(actor)
    event.save()
    return event


# --- duplicate detection ----------------------------------------------------
def find_duplicate_file(owner: User, checksum: str) -> MeetingFile | None:
    """Return the owner's existing *current* file with this checksum, if any."""
    if not checksum:
        return None
    return (
        MeetingFile.objects.filter(
            meeting__owner=owner, checksum_sha256=checksum, is_current=True
        )
        .select_related("meeting")
        .order_by("created_at")
        .first()
    )


# --- processing lock --------------------------------------------------------
def has_active_job(meeting: Meeting) -> bool:
    return MeetingJob.objects.filter(
        meeting=meeting, background_job__status__in=ACTIVE_JOB_STATUSES
    ).exists()


@transaction.atomic
def enqueue_meeting_processing(
    meeting: Meeting, *, actor: User | None = None, options: dict | None = None
) -> MeetingJob:
    """Queue processing for a meeting, enforcing a one-run-at-a-time lock.

    ``options`` are merged into the job payload (e.g. ``model``/``language`` for
    retranscription). Raises :class:`UploadError` (409) if a run is already
    active. Uses ``select_for_update`` on the meeting row so concurrent requests
    can't both slip a job past the check.
    """
    locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
    if locked.processing_status in ACTIVE_PROCESSING_STATUSES or has_active_job(locked):
        raise UploadError(
            "This meeting is already queued or being processed.",
            code="already_processing",
            status=409,
            details={"processing_status": locked.processing_status},
        )

    payload = {"meeting_id": str(locked.id)}
    payload.update({k: v for k, v in (options or {}).items() if v})

    # Create + dispatch the job through the generic JobManager (Celery seam).
    job = job_manager.enqueue(
        JobType.MEETING_PROCESSING,
        pipeline="meeting_processing",
        payload=payload,
        actor=actor,
    )
    meeting_job = MeetingJob(meeting=locked, background_job=job)
    if actor is not None:
        meeting_job.set_acting_user(actor)
    meeting_job.save()

    locked.processing_status = ProcessingStatus.QUEUED
    locked.save(update_fields=["processing_status", "updated_at"])
    meeting.processing_status = ProcessingStatus.QUEUED
    record_event(
        locked, MeetingEventType.QUEUED, "Queued for processing.",
        source=EventSource.SYSTEM, actor=actor, job_id=str(job.id),
    )
    processing_logger.info("Meeting %s queued (job %s).", locked.id, job.id)
    return meeting_job


# --- main upload flow -------------------------------------------------------
@transaction.atomic
def create_upload(
    *,
    owner: User,
    uploaded_file,
    title: str = "",
    description: str = "",
    language: str = "en",
    source: str = MeetingSource.MANUAL_UPLOAD,
    tags: list | None = None,
    on_duplicate: str = DuplicateAction.REJECT,
) -> UploadOutcome:
    """Validate, store and queue an uploaded recording. See module docstring."""
    started = timezone.now()
    session = UploadSession.objects.create(
        user=owner,
        status=UploadSessionStatus.IN_PROGRESS,
        original_filename=getattr(uploaded_file, "name", "")[:255],
        content_type=getattr(uploaded_file, "content_type", "") or "",
        declared_size=int(getattr(uploaded_file, "size", 0) or 0),
    )

    # 1. Validate — always produce a full report.
    report = validate_upload(uploaded_file)
    session.original_filename = report.original_filename
    session.checksum_sha256 = report.checksum_sha256
    session.received_bytes = report.size_bytes
    if not report.ok:
        session.status = UploadSessionStatus.ABORTED
        failure = report.first_failure
        session.error_message = failure.message if failure else "Validation failed."
        session.save()
        raise UploadError(
            failure.message if failure else "Validation failed.",
            code="validation_error",
            details={"report": report.as_dict()},
        )

    # 2. Duplicate policy.
    duplicate = find_duplicate_file(owner, report.checksum_sha256)
    target_meeting: Meeting | None = None
    if duplicate is not None:
        if on_duplicate == DuplicateAction.REJECT:
            session.status = UploadSessionStatus.ABORTED
            session.error_message = "Duplicate file."
            session.save()
            raise UploadError(
                f'You already uploaded this file as "{duplicate.meeting.title}".',
                code="duplicate_upload",
                status=409,
                details={
                    "existing_meeting_id": str(duplicate.meeting_id),
                    "existing_title": duplicate.meeting.title,
                    "actions": [
                        DuplicateAction.REPLACE, DuplicateAction.KEEP_BOTH, DuplicateAction.IGNORE,
                    ],
                    "report": report.as_dict(),
                },
            )
        if on_duplicate == DuplicateAction.IGNORE:
            session.status = UploadSessionStatus.COMPLETED
            session.meeting = duplicate.meeting
            session.save()
            return UploadOutcome(duplicate.meeting, duplicate, report, session, created=False)
        if on_duplicate == DuplicateAction.REPLACE:
            target_meeting = duplicate.meeting
        # KEEP_BOTH falls through to create a brand-new meeting.

    # 3. Resolve target meeting (new or the one we're re-versioning).
    is_new_meeting = target_meeting is None
    if is_new_meeting:
        resolved_title = (title or "").strip() or Path(report.original_filename).stem or "Untitled meeting"
        target_meeting = Meeting(
            owner=owner,
            title=resolved_title[:255],
            description=description or "",
            language=language or "en",
            source=source or MeetingSource.MANUAL_UPLOAD,
            tags=tags or [],
            processing_status=ProcessingStatus.PENDING,
        )
        target_meeting.set_acting_user(owner)
        target_meeting.save()
    record_event(
        target_meeting, MeetingEventType.UPLOAD_STARTED, "Upload started.",
        source=EventSource.USER, actor=owner, filename=report.original_filename,
    )

    # 4. Store the bytes via the storage service and create a new version.
    #    Files live under a private prefix that is never served via MEDIA_URL.
    storage = get_storage_service()
    key = storage.save("private/meetings", report.original_filename, uploaded_file)

    next_version = 1
    if not is_new_meeting:
        next_version = (
            target_meeting.files.aggregate(m=Max("version"))["m"] or 0
        ) + 1
        target_meeting.files.update(is_current=False)

    meeting_file = MeetingFile(
        meeting=target_meeting,
        version=next_version,
        is_current=True,
        storage_key=key,
        original_filename=report.original_filename,
        stored_filename=Path(key).name,
        file_extension=report.extension,
        content_type=report.content_type,
        media_kind=report.media_kind,
        size_bytes=report.size_bytes,
        checksum_sha256=report.checksum_sha256,
        upload_status=UploadStatus.STORED,
        validation_report=report.as_dict(),
        uploaded_at=timezone.now(),
    )
    meeting_file.file.name = key
    meeting_file.set_acting_user(owner)
    meeting_file.save()
    record_event(
        target_meeting, MeetingEventType.UPLOAD_COMPLETED, "Upload completed.",
        source=EventSource.USER, actor=owner, version=next_version,
    )
    record_event(
        target_meeting, MeetingEventType.FILE_STORED, "File stored securely.",
        source=EventSource.SYSTEM, actor=owner,
    )
    if not is_new_meeting:
        record_event(
            target_meeting, MeetingEventType.NEW_VERSION,
            f"Uploaded as version {next_version} (replaces previous recording).",
            source=EventSource.USER, actor=owner, version=next_version,
        )

    # 5. Probe duration + technical metadata (best-effort), enforce max duration.
    local_path = storage.path(key)
    if local_path:
        duration = probe_duration_seconds(local_path, report.extension)
        if duration is not None:
            from django.conf import settings

            if duration > settings.MAX_AUDIO_DURATION_SECONDS:
                meeting_file.upload_status = UploadStatus.FAILED
                meeting_file.save(update_fields=["upload_status", "updated_at"])
                record_event(
                    target_meeting, MeetingEventType.VALIDATION_FAILED,
                    "Recording exceeds the maximum allowed duration.",
                    source=EventSource.SYSTEM, actor=owner,
                )
                raise UploadError(
                    "The recording is longer than the allowed maximum duration.",
                    code="duration_exceeded",
                    details={"duration_seconds": duration},
                )
            target_meeting.duration_seconds = duration
            target_meeting.save(update_fields=["duration_seconds", "updated_at"])

        _store_media_metadata(meeting_file, probe_media_metadata(local_path, report.extension))

    # 6. Mark verified.
    meeting_file.upload_status = UploadStatus.VERIFIED
    meeting_file.save(update_fields=["upload_status", "updated_at"])
    elapsed_ms = int((timezone.now() - started).total_seconds() * 1000)
    record_event(
        target_meeting, MeetingEventType.VALIDATION_COMPLETED, "Validation passed.",
        source=EventSource.SYSTEM, actor=owner, duration_ms=elapsed_ms,
    )

    # 7. Queue processing (lock-protected). A replacement version supersedes any
    #    in-flight run for the old recording, so cancel it before re-queuing.
    if not is_new_meeting:
        _cancel_active_processing(target_meeting)
    enqueue_meeting_processing(target_meeting, actor=owner)

    session.status = UploadSessionStatus.COMPLETED
    session.storage_key = key
    session.meeting = target_meeting
    session.save()

    return UploadOutcome(target_meeting, meeting_file, report, session, created=True)


@transaction.atomic
def enqueue_ai_summarization(meeting: Meeting, *, actor: User | None = None,
                            model: str | None = None) -> MeetingJob:
    """Queue a standalone AI (re)summarization job over the existing transcript."""
    locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
    if has_active_job(locked):
        raise UploadError(
            "A processing job is already running for this meeting.",
            code="already_processing", status=409,
        )
    payload = {"meeting_id": str(locked.id)}
    if model:
        payload["ai_model"] = model
    job = job_manager.enqueue(
        JobType.AI_SUMMARIZATION, pipeline="ai_summarization", payload=payload, actor=actor,
    )
    meeting_job = MeetingJob(meeting=locked, background_job=job)
    if actor is not None:
        meeting_job.set_acting_user(actor)
    meeting_job.save()
    record_event(locked, MeetingEventType.QUEUED, "AI summary generation queued.",
                 source=EventSource.SYSTEM, actor=actor, job_id=str(job.id))
    processing_logger.info("Meeting %s AI summarization queued (job %s).", locked.id, job.id)
    return meeting_job


def _cancel_active_processing(meeting: Meeting) -> None:
    """Cancel any in-flight jobs for a meeting and reset it to PENDING."""
    active = MeetingJob.objects.filter(
        meeting=meeting, background_job__status__in=ACTIVE_JOB_STATUSES
    ).select_related("background_job")
    for mj in active:
        mj.background_job.mark_cancelled()
    meeting.processing_status = ProcessingStatus.PENDING
    meeting.save(update_fields=["processing_status", "updated_at"])


def _store_media_metadata(meeting_file: MeetingFile, probed: dict) -> None:
    known = {"container", "audio_codec", "video_codec", "bitrate", "sample_rate", "channels", "frame_rate"}
    fields = {k: v for k, v in probed.items() if k in known and v is not None}
    extra = {k: v for k, v in probed.items() if k not in known}
    MediaMetadata.objects.update_or_create(
        file=meeting_file, defaults={**fields, "extra": extra},
    )
