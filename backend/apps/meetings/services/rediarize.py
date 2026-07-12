"""Re-run diarization on an ALREADY-transcribed meeting, in place.

Adds/refreshes Speaker entities + voice embeddings + quality signals for a meeting
that was processed before diarization was enabled — WITHOUT re-transcribing or
re-running AI/materialization (so it never disturbs existing tasks/decisions/
knowledge). Reuses the transcript segments already stored; only the diarization
provider runs. Useful for back-filling historical meetings and for demos.
"""
from __future__ import annotations

import logging
import os

from django.core.files.storage import default_storage
from django.db import transaction

logger = logging.getLogger("meetingmind.processing")


def rediarize_meeting(meeting, *, provider=None) -> int:
    """Diarize ``meeting`` from its stored audio + existing transcript segments.
    Returns the number of speakers created (0 if it couldn't run)."""
    from apps.meetings.models import Speaker, TranscriptSegment
    from apps.meetings.pipeline import _SPEAKER_COLORS
    from apps.meetings.services.diarization import DiarizationError, get_diarization_provider
    from apps.meetings.services.media import (
        AudioExtractionService,
        AudioNormalizationService,
        ProcessingError,
    )
    from apps.meetings.services.speaker_quality import persist_speaker_signals

    cf = meeting.current_file
    if not cf:
        return 0
    segs = list(TranscriptSegment.objects.filter(meeting=meeting).order_by("index"))
    if not segs:
        return 0

    src = default_storage.path(cf.file.name)
    if not os.path.exists(src):
        logger.warning("rediarize: source file missing for meeting %s", meeting.id)
        return 0

    # Extract (if needed) + normalize to 16 kHz mono, like the pipeline does.
    try:
        try:
            extracted = AudioExtractionService().extract(src)
        except ProcessingError:
            extracted = src
        audio_path = AudioNormalizationService().normalize(extracted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rediarize: audio prep failed for %s: %s", meeting.id, exc)
        return 0

    provider = provider or get_diarization_provider()
    spans = [(s.start_time, s.end_time) for s in segs]
    try:
        diar = provider.diarize(audio_path, segments=spans, duration=meeting.duration_seconds)
    except DiarizationError as exc:
        logger.warning("rediarize: diarization failed for %s: %s", meeting.id, exc)
        return 0

    rows = [{
        "index": s.index, "start_time": s.start_time, "end_time": s.end_time,
        "word_count": s.word_count or 0, "confidence": s.confidence,
        "speaker": s.speaker, "text": s.text,
    } for s in segs]

    with transaction.atomic():
        Speaker.all_objects.filter(meeting=meeting).hard_delete()

        distinct: list[str] = []
        for lbl in diar.segment_labels:
            if lbl and lbl not in distinct:
                distinct.append(lbl)
        speaker_by_label: dict[str, Speaker] = {}
        for n, lbl in enumerate(distinct, start=1):
            speaker_by_label[lbl] = Speaker.objects.create(
                meeting=meeting, label=f"Speaker {n}", diarization_label=lbl,
                color=_SPEAKER_COLORS[(n - 1) % len(_SPEAKER_COLORS)],
                embedding=diar.embeddings.get(lbl),
            )

        updated = []
        for i, s in enumerate(segs):
            lbl = diar.segment_labels[i] if i < len(diar.segment_labels) else ""
            sp = speaker_by_label.get(lbl)
            s.speaker_ref = sp
            if sp:
                s.speaker = sp.label
            updated.append(s)
        TranscriptSegment.objects.bulk_update(updated, ["speaker_ref", "speaker"])

        for lbl, sp in speaker_by_label.items():
            idx = [i for i, l in enumerate(diar.segment_labels) if l == lbl]
            talk = sum(rows[i]["end_time"] - rows[i]["start_time"] for i in idx)
            words = sum(rows[i]["word_count"] for i in idx)
            confs = [rows[i]["confidence"] for i in idx if rows[i]["confidence"] is not None]
            sp.talk_time_seconds = round(talk, 2)
            sp.segment_count = len(idx)
            sp.word_count = words
            sp.avg_confidence = round(sum(confs) / len(confs), 4) if confs else None
            sp.save(update_fields=[
                "talk_time_seconds", "segment_count", "word_count", "avg_confidence", "updated_at",
            ])

        if speaker_by_label:
            try:
                persist_speaker_signals(meeting, speaker_by_label, diar, rows)
            except Exception:  # noqa: BLE001
                logger.warning("rediarize: quality signals skipped for %s", meeting.id, exc_info=True)

    return len(speaker_by_label)
