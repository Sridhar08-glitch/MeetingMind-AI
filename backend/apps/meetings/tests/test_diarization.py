"""Phase 15 tests: speaker diarization → first-class Speaker entities.

Runs on the deterministic DummyDiarizationProvider (no torch/audio). Verifies the
disabled default (unchanged), and 1/2/3-speaker cases producing real Speaker rows
linked to segments with per-speaker analytics + embeddings persisted.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.jobs.services import execute_job
from apps.meetings.models import Speaker, TranscriptSegment
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


# --- disabled default -------------------------------------------------------
def test_disabled_by_default_no_speakers(user):
    meeting = _upload_and_run(user)
    assert Speaker.objects.filter(meeting=meeting).count() == 0
    assert not TranscriptSegment.objects.filter(meeting=meeting).exclude(speaker="").exists()
    assert not TranscriptSegment.objects.filter(meeting=meeting, speaker_ref__isnull=False).exists()


# --- enabled: 1 / 2 / 3 speakers -------------------------------------------
@pytest.mark.parametrize("n", [1, 2, 3])
def test_diarization_creates_speaker_entities(user, settings, n):
    _enable(settings, n)
    meeting = _upload_and_run(user)

    speakers = list(Speaker.objects.filter(meeting=meeting).order_by("label"))
    assert len(speakers) == n
    assert [s.label for s in speakers] == [f"Speaker {i}" for i in range(1, n + 1)]

    # Every segment is linked to a Speaker + carries the cached label string.
    segs = TranscriptSegment.objects.filter(meeting=meeting)
    assert segs.filter(speaker_ref__isnull=True).count() == 0
    for seg in segs:
        assert seg.speaker == seg.speaker_ref.label

    # Embeddings persisted now (for Phase 15B); analytics computed.
    total_segs = 0
    for s in speakers:
        assert s.embedding and isinstance(s.embedding, list)
        assert s.color.startswith("#")
        assert s.segment_count >= 1
        assert s.talk_time_seconds > 0
        total_segs += s.segment_count
    assert total_segs == segs.count()


def test_speakers_exposed_in_transcript_api(auth_client, user, settings):
    _enable(settings, 2)
    meeting = _upload_and_run(user)
    resp = auth_client.get(f"/api/meetings/{meeting.id}/transcript/")
    assert resp.status_code == 200
    data = resp.data["data"]
    assert len(data["speakers"]) == 2
    assert data["speakers"][0]["label"] == "Speaker 1"
    assert data["speakers"][0]["name"]  # display_name or label
    # segments carry speaker_id
    assert all(seg["speaker_id"] for seg in data["segments"])


def test_retranscribe_replaces_speakers(user, settings):
    """Re-running is idempotent — old Speaker rows are hard-replaced, not doubled."""
    _enable(settings, 2)
    meeting = _upload_and_run(user)
    assert Speaker.objects.filter(meeting=meeting).count() == 2

    # Re-run the pipeline (retranscribe) — still exactly 2 speakers.
    from apps.meetings.services.uploads import enqueue_meeting_processing
    job = enqueue_meeting_processing(meeting)
    execute_job(str(job.background_job_id))
    assert Speaker.objects.filter(meeting=meeting).count() == 2
