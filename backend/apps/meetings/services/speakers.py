"""Speaker management (Phase 15) — rename/confirm/merge, cascading to segments.

Because `Speaker` is the source of truth and each segment carries a denormalized
`speaker` string cache, renaming a speaker updates the whole meeting with a single
bulk UPDATE. Downstream artifacts (tasks/decisions/etc.) reuse the existing
regenerate path if fresh attribution is wanted — no duplicated logic here.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.meetings.models import Speaker, TranscriptSegment

_EDITABLE = ("display_name", "role", "department", "email", "color", "avatar", "aliases")


def _cascade_label(speaker: Speaker) -> None:
    """Resync the denormalized `speaker` string on all of this speaker's segments."""
    TranscriptSegment.objects.filter(speaker_ref=speaker).update(
        speaker=speaker.name, updated_at=timezone.now()
    )


@transaction.atomic
def update_speaker(speaker: Speaker, *, changes: dict, confirmed: bool | None = None) -> Speaker:
    """Edit a speaker's identity fields; a name change cascades to every segment."""
    fields = []
    for key in _EDITABLE:
        if key in changes and changes[key] is not None:
            setattr(speaker, key, changes[key])
            fields.append(key)
    if confirmed is not None:
        speaker.confirmed = confirmed
        fields.append("confirmed")
    if fields:
        fields.append("updated_at")
        speaker.save(update_fields=fields)
    if "display_name" in fields:
        _cascade_label(speaker)
    return speaker


@transaction.atomic
def accept_suggestion(speaker: Speaker) -> Speaker:
    """Confirm the AI-suggested name (never applied automatically)."""
    if speaker.suggested_name:
        speaker.display_name = speaker.suggested_name
        speaker.confirmed = True
        speaker.save(update_fields=["display_name", "confirmed", "updated_at"])
        _cascade_label(speaker)
    return speaker


@transaction.atomic
def merge_speakers(target: Speaker, source: Speaker) -> Speaker:
    """Fold ``source`` into ``target``: reassign segments, merge aliases, recompute."""
    if target.pk == source.pk:
        return target
    TranscriptSegment.objects.filter(speaker_ref=source).update(
        speaker_ref=target, speaker=target.name, updated_at=timezone.now()
    )
    # Keep the source's display name as an alias so history isn't lost.
    aliases = list(target.aliases or [])
    for alias in [source.display_name, source.label, *(source.aliases or [])]:
        if alias and alias not in aliases and alias != target.name:
            aliases.append(alias)
    target.aliases = aliases

    # Recompute target analytics from its (now-combined) segments.
    segs = list(TranscriptSegment.objects.filter(speaker_ref=target))
    target.segment_count = len(segs)
    target.word_count = sum(s.word_count or 0 for s in segs)
    target.talk_time_seconds = round(sum((s.end_time - s.start_time) for s in segs), 2)
    confs = [s.confidence for s in segs if s.confidence is not None]
    target.avg_confidence = round(sum(confs) / len(confs), 4) if confs else None
    target.save(update_fields=[
        "aliases", "segment_count", "word_count", "talk_time_seconds", "avg_confidence", "updated_at",
    ])
    Speaker.all_objects.filter(pk=source.pk).hard_delete()
    return target
