"""Phase 15 tests: AI name suggestions (suggest-only) + speaker management.

Runs on dummy diarization + dummy LLM. Verifies suggestions are stored but never
auto-applied, and that rename/confirm/merge cascade to segments.
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


@pytest.fixture(autouse=True)
def _enable_diarization(settings):
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = 2


def _run(user):
    f = SimpleUploadedFile("talk.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Talk").meeting
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))
    meeting.refresh_from_db()
    return meeting


# --- AI suggestions are stored but NOT applied ------------------------------
def test_ai_suggests_names_without_applying(user):
    meeting = _run(user)
    s1 = Speaker.objects.get(meeting=meeting, label="Speaker 1")
    assert s1.suggested_name == "Alex Test"      # dummy LLM suggested it
    assert s1.suggested_confidence == 90
    assert s1.display_name == ""                 # NEVER auto-applied
    assert s1.confirmed is False


# --- rename cascades to every segment ---------------------------------------
def test_rename_speaker_cascades(auth_client, user):
    meeting = _run(user)
    s1 = Speaker.objects.get(meeting=meeting, label="Speaker 1")
    resp = auth_client.patch(
        f"/api/meetings/{meeting.id}/speakers/{s1.id}/",
        {"display_name": "Alice", "role": "PM"}, format="json",
    )
    assert resp.status_code == 200
    s1.refresh_from_db()
    assert s1.display_name == "Alice" and s1.role == "PM" and s1.confirmed is False
    # Cached string on every one of Alice's segments updated.
    labels = set(TranscriptSegment.objects.filter(speaker_ref=s1).values_list("speaker", flat=True))
    assert labels == {"Alice"}


def test_accept_suggestion(auth_client, user):
    meeting = _run(user)
    s1 = Speaker.objects.get(meeting=meeting, label="Speaker 1")
    resp = auth_client.post(f"/api/meetings/{meeting.id}/speakers/{s1.id}/accept-suggestion/", {}, format="json")
    assert resp.status_code == 200
    s1.refresh_from_db()
    assert s1.display_name == "Alex Test" and s1.confirmed is True
    assert set(TranscriptSegment.objects.filter(speaker_ref=s1).values_list("speaker", flat=True)) == {"Alex Test"}


def test_merge_speakers(auth_client, user):
    meeting = _run(user)
    s1 = Speaker.objects.get(meeting=meeting, label="Speaker 1")
    s2 = Speaker.objects.get(meeting=meeting, label="Speaker 2")
    total = TranscriptSegment.objects.filter(meeting=meeting).count()
    resp = auth_client.post(
        f"/api/meetings/{meeting.id}/speakers/{s1.id}/merge/", {"from": str(s2.id)}, format="json",
    )
    assert resp.status_code == 200
    assert not Speaker.objects.filter(id=s2.id).exists()          # source gone
    s1.refresh_from_db()
    assert s1.segment_count == total                              # all segments now s1
    assert TranscriptSegment.objects.filter(speaker_ref=s1).count() == total


def test_speakers_endpoint(auth_client, user):
    meeting = _run(user)
    resp = auth_client.get(f"/api/meetings/{meeting.id}/speakers/")
    assert resp.status_code == 200
    speakers = resp.data["data"]["speakers"]
    assert len(speakers) == 2
    assert speakers[0]["suggested_name"] == "Alex Test"
    assert speakers[0]["talk_time_seconds"] > 0
