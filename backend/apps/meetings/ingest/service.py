"""Media-import lifecycle — analyze → dedup → download → create_upload.

This is the ONLY place import orchestration lives. It never transcribes,
summarizes, or indexes; once a local file exists it calls ``create_upload()`` and
the existing Phase 6–13 pipeline takes over. Duplicate detection runs in three
layers: original URL (sync), platform id / episode GUID (post-analyze,
pre-download), and file hash (inside create_upload, post-download).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.meetings.enums import DuplicateAction, MediaKind
from apps.meetings.services import media_sources as ms
from apps.meetings.services.media_sources.base import MediaProviderError

from .models import MediaImportSession, MediaImportStatus

logger = logging.getLogger("meetingmind.ingest")

_S = MediaImportStatus


# ─────────────────────────── analyze (for the UI preview) ───────────────────
def analyze_url(url: str):
    """Return MediaSourceInfo for a URL without downloading (raises on refusal)."""
    provider = ms.resolve_provider(url)
    return provider.analyze(url)


# ─────────────────────────── duplicate detection ───────────────────────────
def find_url_duplicate(owner, *, source_url="", platform="", platform_id="", episode_guid=""):
    """Existing Meeting for this origin, by URL → platform+id → episode GUID."""
    from apps.meetings.models import Meeting

    qs = Meeting.objects.filter(owner=owner)
    if source_url:
        hit = qs.filter(source_url=source_url).order_by("-created_at").first()
        if hit:
            return hit
    if platform and platform_id:
        hit = (
            qs.filter(source_metadata__platform=platform, source_metadata__platform_id=platform_id)
            .order_by("-created_at").first()
        )
        if hit:
            return hit
    if episode_guid:
        hit = qs.filter(source_metadata__episode_guid=episode_guid).order_by("-created_at").first()
        if hit:
            return hit
    return None


# ─────────────────────────── create + dispatch ─────────────────────────────
def create_import(owner, *, url, requested_media="video", meeting_language="",
                  transcript_language="original", ai_language="", on_duplicate=DuplicateAction.REJECT,
                  episode_id="", title="") -> MediaImportSession:
    """Create a session and dispatch the download task. Cheap, non-blocking.

    Synchronous URL-level dedup happens here; the deeper checks (platform id /
    GUID / hash) run in the task so a slow ``analyze`` never blocks the request.
    """
    provider = ms.resolve_provider(url)  # raises MediaProviderError if unsupported
    # Fail fast on unsafe/unsupported URLs before creating a session or dispatching.
    if getattr(provider, "requires_public_url", True):
        ms.assert_public_url(url)
    session = MediaImportSession.objects.create(
        owner=owner, source_url=url, provider_id=provider.id, source_type=provider.source_type,
        requested_media=requested_media or "video", episode_id=episode_id or "",
        meeting_language=meeting_language or "", transcript_language=transcript_language or "original",
        ai_language=ai_language or "", on_duplicate=on_duplicate or DuplicateAction.REJECT,
        title=title or "", status=_S.PENDING,
        importer_version=getattr(settings, "MEDIA_IMPORTER_VERSION", "1.0"),
    )

    # Sync URL-level dedup — the cheapest signal, before any network work.
    dup = find_url_duplicate(owner, source_url=url)
    if dup is not None and _reject(on_duplicate):
        session.duplicate_meeting = dup
        _set(session, _S.FAILED, error_code="duplicate_import",
             error_message=f'Already imported as "{dup.title}".')
        return session
    if dup is not None and on_duplicate == DuplicateAction.IGNORE:
        session.meeting = dup
        _set(session, _S.COMPLETED)
        return session

    _dispatch(session.id)
    return session


def _dispatch(session_id) -> None:
    from .tasks import run_media_import

    def _send():
        run_media_import.apply_async(args=[str(session_id)], queue="media")

    transaction.on_commit(_send)


def cancel_import(session: MediaImportSession) -> None:
    if session.status in ms_active():
        _set(session, _S.CANCELLED)


def ms_active():
    from .models import ACTIVE_IMPORT_STATUSES
    return ACTIVE_IMPORT_STATUSES


# ─────────────────────────── the worker body ───────────────────────────────
def run_import(session_id: str) -> None:
    session = MediaImportSession.objects.filter(id=session_id).first()
    if session is None or session.status in (_S.CANCELLED, _S.COMPLETED, _S.BLOCKED):
        return
    provider = ms.provider_by_id(session.provider_id)
    if provider is None:
        try:
            provider = ms.resolve_provider(session.source_url)
        except MediaProviderError as exc:
            _fail(session, exc)
            return

    work_dir = os.path.join(settings.PRIVATE_MEDIA_ROOT, "imports", str(session.id))
    os.makedirs(work_dir, exist_ok=True)
    try:
        _set(session, _S.ANALYZING, progress=0)
        info = provider.analyze(session.source_url)
        _apply_info(session, info)

        # Deep dedup (post-analyze, pre-download): platform id + episode GUID.
        dup = find_url_duplicate(
            session.owner, platform=info.platform, platform_id=info.platform_id,
            episode_guid=session.episode_guid,
        )
        if dup is not None and _reject(session.on_duplicate):
            session.duplicate_meeting = dup
            _set(session, _S.FAILED, error_code="duplicate_import",
                 error_message=f'Already imported as "{dup.title}".')
            _cleanup(work_dir)
            return
        if dup is not None and session.on_duplicate == DuplicateAction.IGNORE:
            session.meeting = dup
            _set(session, _S.COMPLETED)
            _cleanup(work_dir)
            return

        # Download (resumable — work_dir persists across task retries).
        _set(session, _S.DOWNLOADING)
        result = provider.fetch(
            session.source_url, work_dir,
            requested_media=session.requested_media or "video",
            episode_id=session.episode_id or None,
            progress_cb=_progress(session),
        )
        _set(session, _S.DOWNLOADED, progress=100)

        # Hand off to the existing pipeline.
        meeting = _import_file(session, result, info)
        session.meeting = meeting
        _set(session, _S.PROCESSING)
        _cleanup(work_dir)
    except MediaProviderError as exc:
        _fail(session, exc)
        # Keep work_dir on a retryable (non-blocked) failure so a retry can resume.
        if exc.blocked:
            _cleanup(work_dir)
    except _UploadDuplicate as exc:
        session.duplicate_meeting = exc.meeting
        _set(session, _S.FAILED, error_code="duplicate_import", error_message=exc.message)
        _cleanup(work_dir)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Media import %s failed", session.id)
        _set(session, _S.FAILED, error_code="import_error", error_message=str(exc))


def _import_file(session: MediaImportSession, result, info):
    """Checksum → create_upload → stamp provenance/languages onto the Meeting."""
    from apps.meetings.models import Meeting
    from apps.meetings.services.uploads import UploadError, create_upload

    _set(session, _S.VALIDATING)
    session.checksum_sha256 = _sha256(result.file_path)
    session.save(update_fields=["checksum_sha256", "updated_at"])

    _set(session, _S.IMPORTING)
    with open(result.file_path, "rb") as fh:
        django_file = File(fh, name=result.filename)
        try:
            outcome = create_upload(
                owner=session.owner,
                uploaded_file=django_file,
                title=session.title or info.title or "",
                language=session.meeting_language or "en",
                source=info.source_type,
                on_duplicate=session.on_duplicate or DuplicateAction.REJECT,
            )
        except UploadError as exc:
            if exc.code == "duplicate_upload":
                mid = (exc.details or {}).get("existing_meeting_id")
                existing = Meeting.objects.filter(pk=mid).first() if mid else None
                raise _UploadDuplicate(existing, exc.message) from exc
            raise MediaProviderError(exc.message, code=exc.code) from exc

    meeting = outcome.meeting
    provenance = dict(result.metadata or info.provenance())
    provenance.setdefault("source_type", info.source_type)
    provenance["imported_at"] = timezone.now().isoformat()
    provenance["importer_version"] = session.importer_version
    Meeting.objects.filter(pk=meeting.pk).update(
        source_url=info.webpage_url or session.source_url,
        source_metadata=provenance,
        meeting_language=session.meeting_language or "",
        transcript_language=session.transcript_language or "original",
        ai_language=session.ai_language or "",
    )
    return meeting


# ─────────────────────────── helpers ───────────────────────────────────────
class _UploadDuplicate(Exception):
    def __init__(self, meeting, message):
        super().__init__(message)
        self.meeting = meeting
        self.message = message


def _reject(action: str) -> bool:
    return (action or DuplicateAction.REJECT) == DuplicateAction.REJECT


def _apply_info(session: MediaImportSession, info) -> None:
    session.platform = info.platform or ""
    session.platform_id = info.platform_id or ""
    session.title = session.title or info.title or ""
    session.author = info.author or ""
    session.thumbnail_url = info.thumbnail_url or ""
    session.published_at = info.published_at or ""
    session.license = info.license or ""
    session.duration_seconds = info.duration
    session.media_kind = info.media_kind or MediaKind.VIDEO
    # Record the chosen episode's GUID (podcasts) for dedup.
    if info.episodes and session.episode_id:
        ep = next((e for e in info.episodes if e.episode_id == session.episode_id), None)
        if ep:
            session.episode_guid = ep.guid or ""
            session.title = session.title or ep.title
    if info.is_playlist:
        session.playlist = info.title or ""
    session.save(update_fields=[
        "platform", "platform_id", "title", "author", "thumbnail_url", "published_at",
        "license", "duration_seconds", "media_kind", "episode_guid", "playlist", "updated_at",
    ])


def _progress(session: MediaImportSession):
    state = {"t": 0.0}

    def cb(pct: float, done: int, total):
        now = time.monotonic()
        if now - state["t"] < 1.0 and pct < 100.0:  # throttle DB writes to ~1/s
            return
        state["t"] = now
        session.progress = int(max(0, min(100, pct)))
        session.bytes_downloaded = int(done or 0)
        session.total_bytes = int(total) if total else None
        session.save(update_fields=["progress", "bytes_downloaded", "total_bytes", "updated_at"])

    return cb


def _set(session: MediaImportSession, status: str, **fields) -> None:
    session.status = status
    for k, v in fields.items():
        setattr(session, k, v)
    update = ["status", "updated_at", *fields.keys()]
    if session.duplicate_meeting_id is not None and "duplicate_meeting" not in fields:
        update.append("duplicate_meeting")
    if session.meeting_id is not None and "meeting" not in fields:
        update.append("meeting")
    session.save(update_fields=list(dict.fromkeys(update)))


def _fail(session: MediaImportSession, exc: MediaProviderError) -> None:
    _set(session, _S.BLOCKED if exc.blocked else _S.FAILED,
         error_code=exc.code, error_message=exc.message)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cleanup(work_dir: str) -> None:
    shutil.rmtree(work_dir, ignore_errors=True)
