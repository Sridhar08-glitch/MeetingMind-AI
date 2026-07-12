"""Tests for the Phase 4 upload workflow after the pre-Phase-5 redesign.

Covers valid uploads, validation reports, unsupported/oversized/empty/corrupted
files, extension/content mismatch, duplicate policies (reject/replace/keep_both/
ignore), file versioning, the processing lock, upload sessions, authentication,
owner permissions, metadata extraction, and status transitions.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.factories import UserFactory
from apps.jobs.models import BackgroundJob
from apps.meetings.enums import MeetingSource, ProcessingStatus, UploadStatus
from apps.meetings.models import Meeting, MeetingEvent, MeetingFile, MeetingJob, UploadSession

pytestmark = pytest.mark.django_db

UPLOAD_URL = "/api/meetings/upload/"


# --- helpers ---------------------------------------------------------------
def make_wav_bytes(seconds: int = 1, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def make_mp3_bytes(size: int = 4096) -> bytes:
    body = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    return body + b"\x00" * (size - len(body))


def make_mp4_bytes(size: int = 4096) -> bytes:
    body = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    return body + b"\x00" * (size - len(body))


def wav_upload(name: str = "meeting.wav", **kw) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, make_wav_bytes(**kw), content_type="audio/wav")


# --- valid upload ----------------------------------------------------------
def test_valid_upload_stores_metadata_and_queues(auth_client, user):
    resp = auth_client.post(
        UPLOAD_URL,
        {"file": wav_upload(), "title": "Standup", "source": MeetingSource.ZOOM},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    data = resp.data["data"]
    assert data["title"] == "Standup"
    assert data["source"] == MeetingSource.ZOOM
    assert data["processing_status"] == ProcessingStatus.QUEUED
    assert data["upload_status"] == UploadStatus.VERIFIED
    assert data["duration_seconds"] == 1

    cf = data["current_file"]
    assert cf["media_kind"] == "audio"
    assert cf["original_filename"] == "meeting.wav"
    assert cf["stored_filename"] != "meeting.wav"
    assert len(cf["checksum_sha256"]) == 64
    assert cf["version"] == 1
    # WAV media metadata is probed from the stdlib.
    assert cf["media_metadata"]["sample_rate"] == 8000
    assert cf["media_metadata"]["channels"] == 1

    # Validation report is returned in full.
    report = resp.data["data"]["validation_report"]
    assert report["ok"] is True
    names = {c["name"] for c in report["checks"]}
    assert {"extension", "size", "integrity", "virus"} <= names

    meeting = Meeting.objects.get(id=data["id"])
    assert "private/meetings/" in meeting.current_file.file.name
    assert MeetingJob.objects.filter(meeting=meeting).count() == 1
    assert BackgroundJob.objects.count() == 1
    # An upload session was recorded and completed.
    assert UploadSession.objects.filter(meeting=meeting, status="completed").exists()


def test_mp3_and_mp4_signatures_accepted(auth_client):
    mp3 = SimpleUploadedFile("a.mp3", make_mp3_bytes(), content_type="audio/mpeg")
    r1 = auth_client.post(UPLOAD_URL, {"file": mp3}, format="multipart")
    assert r1.status_code == 201, r1.data
    assert r1.data["data"]["current_file"]["media_kind"] == "audio"

    mp4 = SimpleUploadedFile("b.mp4", make_mp4_bytes(), content_type="video/mp4")
    r2 = auth_client.post(UPLOAD_URL, {"file": mp4}, format="multipart")
    assert r2.status_code == 201, r2.data
    assert r2.data["data"]["current_file"]["media_kind"] == "video"


# --- rejection paths (with validation report) ------------------------------
def test_unsupported_extension_rejected_with_report(auth_client):
    bad = SimpleUploadedFile("notes.txt", b"hello world" * 200, content_type="text/plain")
    resp = auth_client.post(UPLOAD_URL, {"file": bad}, format="multipart")
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.data["error"]["message"]
    report = resp.data["error"]["details"]["report"]
    assert report["ok"] is False
    assert any(c["name"] == "extension" and not c["passed"] for c in report["checks"])
    assert Meeting.objects.count() == 0


def test_empty_file_rejected(auth_client):
    tiny = SimpleUploadedFile("empty.wav", b"RIFF", content_type="audio/wav")
    resp = auth_client.post(UPLOAD_URL, {"file": tiny}, format="multipart")
    assert resp.status_code == 400
    assert "empty or too small" in resp.data["error"]["message"]


def test_oversized_file_rejected(auth_client, settings):
    settings.MAX_UPLOAD_SIZE_MB = 0
    resp = auth_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    assert resp.status_code == 400
    assert "exceeding" in resp.data["error"]["message"]


def test_corrupted_content_rejected(auth_client):
    corrupt = SimpleUploadedFile("clip.wav", b"NOT_REAL_MEDIA" * 200, content_type="audio/wav")
    resp = auth_client.post(UPLOAD_URL, {"file": corrupt}, format="multipart")
    assert resp.status_code == 400
    assert "corrupted" in resp.data["error"]["message"].lower()


def test_extension_content_mismatch_rejected(auth_client):
    disguised = SimpleUploadedFile("song.mp3", make_mp4_bytes(), content_type="audio/mpeg")
    resp = auth_client.post(UPLOAD_URL, {"file": disguised}, format="multipart")
    assert resp.status_code == 400
    assert "do not match" in resp.data["error"]["message"]


# --- duplicate policies -----------------------------------------------------
def _upload_same(auth_client, payload, **extra):
    return auth_client.post(
        UPLOAD_URL,
        {"file": SimpleUploadedFile("a.wav", payload, "audio/wav"), **extra},
        format="multipart",
    )


def test_duplicate_rejected_by_default_with_actions(auth_client):
    payload = make_wav_bytes()
    assert _upload_same(auth_client, payload).status_code == 201
    dup = _upload_same(auth_client, payload)
    assert dup.status_code == 409
    assert dup.data["error"]["code"] == "duplicate_upload"
    details = dup.data["error"]["details"]
    assert set(details["actions"]) == {"replace", "keep_both", "ignore"}
    assert "existing_meeting_id" in details


def test_duplicate_replace_creates_new_version(auth_client):
    payload = make_wav_bytes()
    first = _upload_same(auth_client, payload)
    meeting_id = first.data["data"]["id"]

    replaced = _upload_same(auth_client, payload, on_duplicate="replace")
    assert replaced.status_code == 201
    assert replaced.data["data"]["id"] == meeting_id  # same meeting
    assert Meeting.objects.count() == 1
    files = MeetingFile.objects.filter(meeting_id=meeting_id).order_by("version")
    assert [f.version for f in files] == [1, 2]
    assert [f.is_current for f in files] == [False, True]


def test_duplicate_keep_both_creates_second_meeting(auth_client):
    payload = make_wav_bytes()
    _upload_same(auth_client, payload)
    both = _upload_same(auth_client, payload, on_duplicate="keep_both")
    assert both.status_code == 201
    assert Meeting.objects.count() == 2


def test_duplicate_ignore_returns_existing(auth_client):
    payload = make_wav_bytes()
    first = _upload_same(auth_client, payload)
    ignored = _upload_same(auth_client, payload, on_duplicate="ignore")
    assert ignored.status_code == 200
    assert ignored.data["data"]["id"] == first.data["data"]["id"]
    assert Meeting.objects.count() == 1


# --- processing lock --------------------------------------------------------
def test_reprocess_blocked_while_active(auth_client):
    resp = auth_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    meeting_id = resp.data["data"]["id"]
    # Freshly uploaded meeting is QUEUED (active) → reprocess must be rejected.
    again = auth_client.post(f"/api/meetings/{meeting_id}/reprocess/")
    assert again.status_code == 409
    assert again.data["error"]["code"] == "already_processing"


# --- auth & permissions ----------------------------------------------------
def test_upload_requires_authentication(api_client):
    resp = api_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    assert resp.status_code == 401


def test_owner_can_download_own_file(auth_client):
    resp = auth_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    meeting_id = resp.data["data"]["id"]
    dl = auth_client.get(f"/api/meetings/{meeting_id}/download/")
    assert dl.status_code == 200
    assert dl["Content-Disposition"].startswith("attachment")


def test_non_owner_cannot_download_or_view(auth_client, api_client):
    resp = auth_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    meeting_id = resp.data["data"]["id"]

    other = UserFactory()
    login = api_client.post(
        "/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    assert api_client.get(f"/api/meetings/{meeting_id}/download/").status_code in (403, 404)
    assert api_client.get(f"/api/meetings/{meeting_id}/status/").status_code in (403, 404)


# --- status & timeline -----------------------------------------------------
def test_status_and_rich_timeline(auth_client):
    resp = auth_client.post(UPLOAD_URL, {"file": wav_upload()}, format="multipart")
    meeting_id = resp.data["data"]["id"]

    status_resp = auth_client.get(f"/api/meetings/{meeting_id}/status/")
    assert status_resp.status_code == 200
    body = status_resp.data["data"]
    assert body["processing_status"] == ProcessingStatus.QUEUED
    assert body["upload_status"] == UploadStatus.VERIFIED

    events = MeetingEvent.objects.filter(meeting_id=meeting_id).order_by("created_at")
    types = [e.event_type for e in events]
    assert types == [
        "upload_started", "upload_completed", "file_stored",
        "validation_completed", "queued",
    ]
    # Events carry structured fields, not just text.
    validation = events.get(event_type="validation_completed")
    assert validation.source == "system"
    assert validation.duration_ms is not None
