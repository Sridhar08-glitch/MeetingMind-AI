"""Live-session lifecycle + near-real-time preview transcription.

Isolated from ``Meeting`` until :func:`finalize`, which reuses the EXISTING upload
+ pipeline path (``create_upload`` → ``meeting_processing``) so there is zero
duplicate processing logic. Preview transcription decodes the growing recording
with ffmpeg and runs the configured STT provider on the newly-arrived tail only.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from apps.meetings.enums import MeetingSource
from apps.meetings.live.models import (
    LiveMeetingSession,
    LiveSessionStatus,
    LiveTranscriptSegment,
)

logger = logging.getLogger("meetingmind.processing")

# Only transcribe once this many seconds of NEW audio have accrued.
_MIN_NEW_AUDIO = 6.0
_OVERLAP = 0.4  # re-decode a little before the checkpoint to avoid clipping words


def _live_dir() -> str:
    path = os.path.join(settings.PRIVATE_MEDIA_ROOT, "live")
    os.makedirs(path, exist_ok=True)
    return path


def session_path(session: LiveMeetingSession) -> str:
    return os.path.join(_live_dir(), f"{session.id}.{session.file_extension or 'webm'}")


# ─────────────────────────── lifecycle ───────────────────────────
def create_session(owner, *, source: str, media_kind: str, title: str,
                    meeting_language: str, transcript_language: str, ai_language: str,
                    file_extension: str = "webm") -> LiveMeetingSession:
    session = LiveMeetingSession.objects.create(
        owner=owner, source=source or "", media_kind=media_kind or "audio",
        title=title or "", file_extension=file_extension or "webm",
        meeting_language=meeting_language or "", transcript_language=transcript_language or "original",
        ai_language=ai_language or "", status=LiveSessionStatus.RECORDING,
    )
    # Touch the file so appends have a target.
    open(session_path(session), "wb").close()
    return session


def append_chunk(session: LiveMeetingSession, data: bytes) -> None:
    with open(session_path(session), "ab") as fh:
        fh.write(data)
    session.chunk_count += 1
    session.bytes_received += len(data)
    session.save(update_fields=["chunk_count", "bytes_received", "updated_at"])


def set_status(session: LiveMeetingSession, status: str) -> None:
    session.status = status
    session.save(update_fields=["status", "updated_at"])


# ─────────────────────────── preview transcription ───────────────────────────
def _ffmpeg() -> str:
    return settings.FFMPEG_BINARY


def _decode_tail(src_webm: str, start: float) -> tuple[str | None, float]:
    """Decode the growing recording to a 16 kHz mono WAV of audio AFTER ``start``.

    Returns (wav_path, total_duration). ``wav_path`` is None if there is nothing
    new yet. Caller deletes the temp file.
    """
    full = tempfile.NamedTemporaryFile(suffix=".full.wav", delete=False)
    full.close()
    try:
        subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-i", src_webm,
             "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", full.name],
            capture_output=True, timeout=120,
        )
    except Exception:  # noqa: BLE001 — partial/locked file; try again next cycle
        os.unlink(full.name)
        return None, start
    total = _wav_duration(full.name)
    if total - start < _MIN_NEW_AUDIO:
        os.unlink(full.name)
        return None, total
    tail = tempfile.NamedTemporaryFile(suffix=".tail.wav", delete=False)
    tail.close()
    ss = max(0.0, start - _OVERLAP)
    try:
        subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-i", full.name,
             "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", tail.name],
            capture_output=True, timeout=120,
        )
    finally:
        os.unlink(full.name)
    return tail.name, total


def _wav_duration(path: str) -> float:
    import wave

    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate() or 16000
            return w.getnframes() / rate
    except Exception:  # noqa: BLE001
        return 0.0


def transcribe_new(session: LiveMeetingSession) -> list[dict]:
    """Transcribe newly-arrived audio into preview segments. Returns new rows.

    Blocking (ffmpeg + Whisper) — the consumer runs it in a thread executor.
    """
    from apps.meetings.services.transcription import SpeechToTextService

    src = session_path(session)
    if not os.path.exists(src) or os.path.getsize(src) == 0:
        return []
    service = SpeechToTextService()
    start = session.last_committed_time
    hint = session.meeting_language or None

    if not service.requires_audio:
        # Dummy/dev provider — synthesize a growing preview without ffmpeg/Whisper.
        total = max(start + _MIN_NEW_AUDIO, session.bytes_received / 4000.0)
        if total - start < _MIN_NEW_AUDIO:
            return []
        result = service.transcribe(None, language=hint, duration=(total - start))
        offset = start
    else:
        wav, total = _decode_tail(src, start)
        if wav is None:
            return []
        try:
            result = service.transcribe(
                wav, language=hint, duration=(total - max(0.0, start - _OVERLAP)),
            )
        except Exception:  # noqa: BLE001 — preview is best-effort
            logger.debug("Live transcription failed", exc_info=True)
            return []
        finally:
            if os.path.exists(wav):
                os.unlink(wav)
        offset = max(0.0, start - _OVERLAP)
    new_rows: list[dict] = []
    with transaction.atomic():
        idx = LiveTranscriptSegment.objects.filter(session=session).count()
        last_end = start
        for seg in result.segments:
            seg_start = round(offset + seg.start, 2)
            seg_end = round(offset + seg.end, 2)
            # Only commit audio strictly past the checkpoint (dedupe the overlap).
            if seg_end <= start + 0.05 or not seg.text.strip():
                continue
            row = LiveTranscriptSegment.objects.create(
                session=session, index=idx, start_time=seg_start, end_time=seg_end,
                speaker="", text=seg.text.strip(), confidence=seg.confidence,
            )
            new_rows.append({
                "index": idx, "start": seg_start, "end": seg_end,
                "text": row.text, "speaker": "", "confidence": seg.confidence,
            })
            idx += 1
            last_end = max(last_end, seg_end)
        session.last_committed_time = max(session.last_committed_time, last_end, total - 0.5)
        session.duration_seconds = total
        session.save(update_fields=["last_committed_time", "duration_seconds", "updated_at"])

    _translate_live(session, new_rows)
    return new_rows


def _translate_live(session: LiveMeetingSession, rows: list[dict]) -> None:
    """Translate the new preview rows if a transcript target is set (best-effort)."""
    target = session.transcript_language
    if not rows or not target or target in ("original", "source"):
        return
    try:
        from apps.meetings.services.translation import get_translation_provider

        provider = get_translation_provider()
        res = provider.translate([r["text"] for r in rows], target_language=target)
        ids = list(
            LiveTranscriptSegment.objects.filter(
                session=session, index__in=[r["index"] for r in rows]
            ).order_by("index")
        )
        for seg, txt, row in zip(ids, res.segments, rows):
            seg.translated_text = txt or ""
            row["translated_text"] = txt or ""
        LiveTranscriptSegment.objects.bulk_update(ids, ["translated_text"])
    except Exception:  # noqa: BLE001 — never block the live stream on translation
        logger.debug("Live translation failed", exc_info=True)


def update_live_ai(session: LiveMeetingSession) -> dict:
    """Throttled live AI preview over the accrued transcript (best-effort)."""
    if not getattr(settings, "LIVE_AI_ENABLED", True):
        return {}
    segments = list(LiveTranscriptSegment.objects.filter(session=session).order_by("index"))
    text = " ".join(s.text for s in segments).strip()
    if len(text) < 120:
        return {}
    try:
        from apps.meetings.services.ai import AISummarizationService

        result = AISummarizationService().analyze(text, output_language=session.ai_language or None)
        p = result.parsed
        live = {
            "executive_summary": p["executive_summary"],
            "action_items": p["action_items"],
            "decisions": p["decisions"],
            "risks": p["risks"],
            "keywords": p.get("keywords", {}),
        }
        session.live_summary = p["executive_summary"]
        session.live_ai = live
        session.save(update_fields=["live_summary", "live_ai", "updated_at"])
        return live
    except Exception:  # noqa: BLE001 — preview only
        logger.debug("Live AI preview failed", exc_info=True)
        return {}


# ─────────────────────────── finalize (reuse the real pipeline) ───────────────────────────
def finalize(session: LiveMeetingSession, *, actor=None):
    """Turn the recording into a real Meeting and run the EXISTING pipeline."""
    from apps.meetings.models import Meeting
    from apps.meetings.services.uploads import UploadError, create_upload

    set_status(session, LiveSessionStatus.FINALIZING)
    src = session_path(session)
    if not os.path.exists(src) or os.path.getsize(src) < 1024:
        set_status(session, LiveSessionStatus.FAILED)
        session.error_message = "Recording was empty."
        session.save(update_fields=["error_message", "updated_at"])
        raise ValueError("Recording was empty.")

    title = session.title or f"Live meeting — {timezone.now():%b %d, %H:%M}"
    filename = f"live_{session.id}.{session.file_extension or 'webm'}"
    with open(src, "rb") as fh:
        django_file = File(fh, name=filename)
        try:
            outcome = create_upload(
                owner=session.owner,
                uploaded_file=django_file,
                title=title,
                # meeting.language becomes the STT hint ("en" => auto-detect).
                language=session.meeting_language or "en",
                source=MeetingSource.LIVE,
            )
        except UploadError:
            set_status(session, LiveSessionStatus.FAILED)
            raise

    meeting = outcome.meeting
    # Carry the three language settings onto the Meeting so the existing pipeline
    # stages (translation + AI) pick them up — no new payload plumbing needed.
    Meeting.objects.filter(pk=meeting.pk).update(
        meeting_language=session.meeting_language or "",
        transcript_language=session.transcript_language or "original",
        ai_language=session.ai_language or "",
    )
    session.meeting = meeting
    session.status = LiveSessionStatus.COMPLETED
    session.save(update_fields=["meeting", "status", "updated_at"])
    logger.info("Live session %s finalized → meeting %s", session.id, meeting.id)
    return meeting


def open_sessions_for(owner):
    from apps.meetings.live.models import ACTIVE_LIVE_STATUSES

    return LiveMeetingSession.objects.filter(owner=owner, status__in=ACTIVE_LIVE_STATUSES).order_by("-created_at")


# Below this the recording is too short to be worth processing (accidental start).
_MIN_FINALIZE_BYTES = 12_000


def finalize_on_disconnect(session: LiveMeetingSession):
    """Queue the recording if the client drops mid-recording — so it is never lost.

    Idempotent: skips if the session is already stopping/finished (e.g. the user
    pressed Stop). A trivially-short recording is abandoned rather than queued.
    """
    session.refresh_from_db()
    if session.status not in (LiveSessionStatus.RECORDING, LiveSessionStatus.PAUSED):
        return None  # a real Stop is already handling finalization
    if session.bytes_received < _MIN_FINALIZE_BYTES:
        set_status(session, LiveSessionStatus.ABANDONED)
        return None
    try:
        return finalize(session)
    except Exception:  # noqa: BLE001 — never raise out of a disconnect handler
        logger.exception("Auto-finalize on disconnect failed for session %s", session.id)
        return None
