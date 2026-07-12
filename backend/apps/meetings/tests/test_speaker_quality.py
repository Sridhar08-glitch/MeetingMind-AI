"""Phase 15 tests: multiple voice embeddings + per-speaker quality signals.

Verifies that when diarization is on, every speaker gets SpeakerEmbedding rows
(centroid / segment / best-N) and a SpeakerQualitySignal — persisted at processing
time so Phase 15B never re-embeds — and that the default (diarization off) is
unchanged. Runs on the deterministic dummy provider (no torch/audio).
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.jobs.services import execute_job
from apps.meetings.enums import SpeakerEmbeddingKind
from apps.meetings.models import Speaker, SpeakerEmbedding, SpeakerQualitySignal
from apps.meetings.services.uploads import create_upload

pytestmark = pytest.mark.django_db


def _wav(seconds: int = 40, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def _upload_and_run(user):
    f = SimpleUploadedFile("talk.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Talk").meeting
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))
    meeting.refresh_from_db()
    return meeting


def _enable(settings, speakers: int):
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = speakers


def test_disabled_default_persists_no_quality_rows(user):
    meeting = _upload_and_run(user)
    assert SpeakerEmbedding.objects.filter(speaker__meeting=meeting).count() == 0
    assert SpeakerQualitySignal.objects.filter(speaker__meeting=meeting).count() == 0


@pytest.mark.parametrize("n", [1, 2, 3])
def test_embeddings_and_signals_persisted(user, settings, n):
    _enable(settings, n)
    meeting = _upload_and_run(user)

    speakers = list(Speaker.objects.filter(meeting=meeting))
    assert len(speakers) == n

    for sp in speakers:
        embs = list(SpeakerEmbedding.objects.filter(speaker=sp))
        kinds = {e.kind for e in embs}
        # Every speaker keeps exactly one centroid + at least one best-N + segments.
        assert SpeakerEmbeddingKind.CENTROID in kinds
        assert SpeakerEmbeddingKind.SEGMENT in kinds
        assert SpeakerEmbeddingKind.BEST_N in kinds
        for e in embs:
            assert e.vector and isinstance(e.vector, list)
            assert e.dimensions == len(e.vector)

        # Quality signal exists and is well-formed.
        q = SpeakerQualitySignal.objects.get(speaker=sp)
        assert q.total_segments == sp.segment_count
        assert q.speech_duration > 0
        assert 0.0 <= q.signal_quality <= 100.0
        assert 0.0 <= q.overlap_ratio <= 1.0
        assert 0.0 <= q.silence_ratio <= 1.0
        assert q.usable_segments <= q.total_segments
        assert q.approximate is True  # geometric/confidence proxies (req 8 honesty)


def test_best_n_capped_and_ranked(user, settings):
    settings.SPEAKER_BEST_N = 2
    _enable(settings, 1)
    meeting = _upload_and_run(user)
    sp = Speaker.objects.get(meeting=meeting)
    best = list(
        SpeakerEmbedding.objects.filter(speaker=sp, kind=SpeakerEmbeddingKind.BEST_N).order_by("rank")
    )
    assert 1 <= len(best) <= 2
    assert [b.rank for b in best] == list(range(1, len(best) + 1))


def test_segment_embeddings_toggle_off(user, settings):
    settings.SPEAKER_STORE_SEGMENT_EMBEDDINGS = False
    _enable(settings, 1)
    meeting = _upload_and_run(user)
    sp = Speaker.objects.get(meeting=meeting)
    assert not SpeakerEmbedding.objects.filter(speaker=sp, kind=SpeakerEmbeddingKind.SEGMENT).exists()
    # Centroid + best-N are still kept (they are the 15B-critical signatures).
    assert SpeakerEmbedding.objects.filter(speaker=sp, kind=SpeakerEmbeddingKind.CENTROID).exists()
    assert SpeakerEmbedding.objects.filter(speaker=sp, kind=SpeakerEmbeddingKind.BEST_N).exists()


def test_retranscribe_replaces_embeddings_and_signals(user, settings):
    """Re-running hard-replaces speakers → their embeddings/signals cascade-delete,
    so counts stay stable (no orphans, no doubling)."""
    _enable(settings, 2)
    meeting = _upload_and_run(user)
    first_emb = SpeakerEmbedding.objects.filter(speaker__meeting=meeting).count()
    first_sig = SpeakerQualitySignal.objects.filter(speaker__meeting=meeting).count()
    assert first_emb > 0 and first_sig == 2

    from apps.meetings.services.uploads import enqueue_meeting_processing
    job = enqueue_meeting_processing(meeting)
    execute_job(str(job.background_job_id))

    assert SpeakerEmbedding.objects.filter(speaker__meeting=meeting).count() == first_emb
    assert SpeakerQualitySignal.objects.filter(speaker__meeting=meeting).count() == 2
