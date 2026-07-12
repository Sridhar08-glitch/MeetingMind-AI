"""Phase 6 tests: transcription pipeline, editing, search, downloads, errors.

All tests run on the deterministic DummySpeechProvider (forced via conftest) — no
ffmpeg, no Faster-Whisper, no model downloads.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.factories import UserFactory
from apps.jobs.enums import JobStatus
from apps.jobs.services import execute_job
from apps.meetings.enums import ProcessingStatus
from apps.meetings.models import MediaMetadata, Transcript, TranscriptSegment
from apps.meetings.services import transcript_formats, transcripts
from apps.meetings.services.media import (
    AudioExtractionService,
    MediaInspectionService,
    ProcessingError,
)
from apps.meetings.services.stt import DummySpeechProvider, get_speech_provider
from apps.meetings.services.uploads import create_upload

pytestmark = pytest.mark.django_db


# --- helpers ---------------------------------------------------------------
def make_wav_bytes(seconds: int = 40, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def _upload(user, seconds: int = 40):
    f = SimpleUploadedFile("talk.wav", make_wav_bytes(seconds), content_type="audio/wav")
    return create_upload(owner=user, uploaded_file=f, title="Talk").meeting


def _run_pipeline(meeting):
    # Run the most recently queued job (retranscribe adds a newer one).
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))
    meeting.refresh_from_db()
    return job


@pytest.fixture
def transcribed(user):
    meeting = _upload(user)
    _run_pipeline(meeting)
    return meeting


# --- provider selection -----------------------------------------------------
def test_dummy_provider_selected_in_tests():
    provider = get_speech_provider()
    assert isinstance(provider, DummySpeechProvider)
    assert provider.requires_audio is False


def test_faster_whisper_falls_back_when_unavailable(settings, monkeypatch):
    settings.STT_PROVIDER = "faster_whisper"
    # Simulate the library being unavailable.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert isinstance(get_speech_provider(), DummySpeechProvider)


# --- pipeline end-to-end ----------------------------------------------------
def test_pipeline_produces_transcript_and_segments(transcribed):
    assert transcribed.processing_status == ProcessingStatus.COMPLETED
    transcript = Transcript.objects.get(meeting=transcribed)
    assert transcript.word_count > 0
    assert transcript.char_count > 0
    assert transcript.detected_language == "en"
    assert transcript.provider == "dummy"
    assert transcript.avg_confidence is not None
    # Segmented, never a single blob.
    segs = TranscriptSegment.objects.filter(meeting=transcribed).order_by("index")
    assert segs.count() >= 3
    assert all(s.word_count and s.word_count > 0 for s in segs)
    assert segs.first().start_time == 0.0


def test_media_inspection_populates_metadata(transcribed):
    cf = transcribed.current_file
    meta = MediaMetadata.objects.get(file=cf)
    # stdlib fallback reads the WAV header.
    assert meta.sample_rate == 16000
    assert meta.channels == 1


def test_pipeline_logs_all_stages(transcribed):
    job = transcribed.meeting_jobs.first().background_job
    stages = set(job.job_logs.exclude(stage="").values_list("stage", flat=True))
    assert {"validation", "media_inspection", "speech_to_text", "store_transcript", "finalize"} <= stages


# --- editing & restore ------------------------------------------------------
def test_edit_segment_preserves_original(transcribed):
    seg = transcribed.segments.first()
    original = seg.text
    transcripts.edit_segment(seg, text="Corrected text here.", speaker="Alice")
    seg.refresh_from_db()
    assert seg.text == "Corrected text here."
    assert seg.speaker == "Alice"
    assert seg.is_edited is True
    assert seg.original_text == original
    assert seg.word_count == 3
    # Transcript flagged as edited.
    assert Transcript.objects.get(meeting=transcribed).is_edited is True


def test_restore_segment(transcribed):
    seg = transcribed.segments.first()
    original = seg.text
    transcripts.edit_segment(seg, text="Wrong.")
    transcripts.restore_segment(seg)
    seg.refresh_from_db()
    assert seg.text == original
    assert seg.is_edited is False


def test_restore_whole_transcript(transcribed):
    for seg in transcribed.segments.all()[:2]:
        transcripts.edit_segment(seg, text="Edited.")
    restored = transcripts.restore_transcript(transcribed)
    assert restored == 2
    assert transcribed.segments.filter(is_edited=True).count() == 0


# --- retranscribe -----------------------------------------------------------
def test_retranscribe_replaces_segments(transcribed):
    first_ids = set(transcribed.segments.values_list("id", flat=True))
    transcripts.retranscribe(transcribed, model="small")
    transcribed.refresh_from_db()
    assert transcribed.processing_status == ProcessingStatus.QUEUED
    _run_pipeline(transcribed)
    # Same meeting, fresh segments (old ones replaced), still one transcript.
    assert Transcript.objects.filter(meeting=transcribed).count() == 1
    new_ids = set(transcribed.segments.values_list("id", flat=True))
    assert new_ids.isdisjoint(first_ids)


# --- search -----------------------------------------------------------------
def test_search_by_word(transcribed):
    results = transcripts.search_segments(transcribed, query="action")
    assert results.count() >= 1
    assert any("action" in s.text.lower() for s in results)


def test_search_by_timestamp(transcribed):
    results = transcripts.search_segments(transcribed, start=0, end=5)
    assert results.count() >= 1
    assert results.first().start_time <= 5


# --- downloads --------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["txt", "md", "json", "srt", "vtt"])
def test_download_formats(transcribed, fmt):
    transcript = transcribed.transcripts.first()
    segments = list(transcribed.segments.order_by("index"))
    content, mime, ext = transcript_formats.render(fmt, transcribed, transcript, segments)
    assert content.strip()
    assert ext == fmt
    if fmt == "srt":
        assert "-->" in content and "00:00:00,000" in content
    if fmt == "vtt":
        assert content.startswith("WEBVTT")


def test_download_rejects_unknown_format(transcribed):
    with pytest.raises(ValueError, match="Unsupported"):
        transcript_formats.render("pdf", transcribed, None, list(transcribed.segments.all()))


# --- structured error handling ---------------------------------------------
def test_extraction_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr("apps.meetings.services.media.ffmpeg_available", lambda: False)
    with pytest.raises(ProcessingError) as exc:
        AudioExtractionService().extract("/tmp/whatever.mp4")
    assert exc.value.code == "ffmpeg_missing"
    assert exc.value.retryable is False


def test_media_inspection_fallback_without_ffprobe(user, monkeypatch):
    monkeypatch.setattr("apps.meetings.services.media.ffprobe_available", lambda: False)
    meeting = _upload(user, seconds=5)
    info = MediaInspectionService().inspect(meeting.current_file.file.path)
    assert info.sample_rate == 16000
    assert info.channels == 1


# --- API + permissions ------------------------------------------------------
def test_transcript_api_and_edit(auth_client, user):
    meeting = _upload(user)
    _run_pipeline(meeting)

    resp = auth_client.get(f"/api/meetings/{meeting.id}/transcript/")
    assert resp.status_code == 200
    assert resp.data["data"]["transcript"]["word_count"] > 0
    seg_id = resp.data["data"]["segments"][0]["id"]

    edit = auth_client.patch(
        f"/api/meetings/{meeting.id}/segments/{seg_id}/", {"text": "New text."}, format="json"
    )
    assert edit.status_code == 200
    assert edit.data["data"]["is_edited"] is True

    restore = auth_client.post(f"/api/meetings/{meeting.id}/segments/{seg_id}/restore/")
    assert restore.status_code == 200
    assert restore.data["data"]["is_edited"] is False


def test_transcript_download_and_search_api(auth_client, user):
    meeting = _upload(user)
    _run_pipeline(meeting)

    dl = auth_client.get(f"/api/meetings/{meeting.id}/transcript/download/?fmt=srt")
    assert dl.status_code == 200
    assert dl["Content-Disposition"].startswith("attachment")
    assert b"-->" in dl.content

    search = auth_client.get(f"/api/meetings/{meeting.id}/transcript/search/?q=action")
    assert search.status_code == 200
    assert search.data["data"]["count"] >= 1


def test_stats_and_language_api(auth_client, user):
    meeting = _upload(user)
    _run_pipeline(meeting)
    stats = auth_client.get(f"/api/meetings/{meeting.id}/transcript/stats/")
    assert stats.status_code == 200
    assert stats.data["data"]["provider"] == "dummy"
    lang = auth_client.get(f"/api/meetings/{meeting.id}/transcript/language/")
    assert lang.status_code == 200
    assert lang.data["data"]["detected_language"] == "en"


def test_non_owner_cannot_access_transcript(auth_client, api_client, user):
    meeting = _upload(user)
    _run_pipeline(meeting)
    other = UserFactory()
    login = api_client.post(
        "/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api_client.get(f"/api/meetings/{meeting.id}/transcript/").status_code in (403, 404)


def test_retranscribe_api(auth_client, user):
    meeting = _upload(user)
    _run_pipeline(meeting)
    resp = auth_client.post(f"/api/meetings/{meeting.id}/retranscribe/", {"model": "base"}, format="json")
    assert resp.status_code == 200
    meeting.refresh_from_db()
    assert meeting.processing_status == JobStatus.QUEUED
