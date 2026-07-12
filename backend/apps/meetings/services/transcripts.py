"""Transcript editing, restore, retranscription, and search.

Editing never destroys the machine transcription: the first edit preserves the
original text on the segment so it can be restored. Retranscription re-runs the
existing pipeline (idempotent store stage replaces prior segments).
"""
from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.meetings.models import Meeting, Transcript, TranscriptSegment
from apps.meetings.services.uploads import (
    UploadError,
    _cancel_active_processing,
    enqueue_meeting_processing,
)


def _touch_transcript(meeting: Meeting) -> None:
    Transcript.objects.filter(meeting=meeting).update(is_edited=True, edited_at=timezone.now())


def edit_segment(segment: TranscriptSegment, *, text: str, speaker: str | None = None,
                 actor: User | None = None) -> TranscriptSegment:
    """Edit a segment's text/speaker, preserving the original for restore."""
    if not segment.original_text:
        segment.original_text = segment.text  # preserve machine output on first edit
    segment.text = text.strip()
    if speaker is not None:
        segment.speaker = speaker.strip()
    segment.word_count = len(segment.text.split())
    segment.is_edited = True
    segment.edited_at = timezone.now()
    if actor is not None:
        segment.set_acting_user(actor)
    segment.save(update_fields=[
        "original_text", "text", "speaker", "word_count", "is_edited", "edited_at", "updated_at",
    ])
    _touch_transcript(segment.meeting)
    return segment


def restore_segment(segment: TranscriptSegment) -> TranscriptSegment:
    """Restore a segment to its original machine transcription."""
    if segment.is_edited and segment.original_text:
        segment.text = segment.original_text
        segment.original_text = ""
        segment.word_count = len(segment.text.split())
        segment.is_edited = False
        segment.edited_at = None
        segment.save(update_fields=[
            "original_text", "text", "word_count", "is_edited", "edited_at", "updated_at",
        ])
    return segment


def restore_transcript(meeting: Meeting) -> int:
    """Restore every edited segment in a meeting. Returns the count restored."""
    edited = TranscriptSegment.objects.filter(meeting=meeting, is_edited=True)
    count = 0
    for seg in edited:
        restore_segment(seg)
        count += 1
    Transcript.objects.filter(meeting=meeting).update(is_edited=False, edited_at=None)
    return count


def retranscribe(meeting: Meeting, *, actor: User | None = None,
                 model: str | None = None, language: str | None = None):
    """Re-run transcription (optionally with a different model/language).

    Supersedes any in-flight run, then queues a fresh job. No re-upload needed.
    """
    if meeting.current_file is None:
        raise UploadError("This meeting has no file to transcribe.", code="no_file", status=409)
    _cancel_active_processing(meeting)
    return enqueue_meeting_processing(
        meeting, actor=actor, options={"model": model, "language": language}
    )


def search_segments(meeting: Meeting, *, query: str = "", speaker: str = "",
                    start: float | None = None, end: float | None = None) -> QuerySet[TranscriptSegment]:
    """Search a meeting's transcript by word/phrase, speaker and/or time range."""
    qs = TranscriptSegment.objects.filter(meeting=meeting)
    if query:
        qs = qs.filter(Q(text__icontains=query) | Q(speaker__icontains=query))
    if speaker:
        qs = qs.filter(speaker__iexact=speaker)
    if start is not None:
        qs = qs.filter(end_time__gte=start)
    if end is not None:
        qs = qs.filter(start_time__lte=end)
    return qs.order_by("index")
