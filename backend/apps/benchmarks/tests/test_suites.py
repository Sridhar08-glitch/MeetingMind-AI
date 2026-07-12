"""Public + user benchmark suite tests (req 1, 2, 8).

The public-import path is exercised fully offline via the Phase 14 ``dummy://``
media provider (writes a tiny WAV, no network), proving a public recording flows
through the real import + pipeline and becomes benchmarkable.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.benchmarks.enums import GroundTruthType, RecordingStatus
from apps.benchmarks.models import BenchmarkDataset, BenchmarkRecording
from apps.benchmarks.services import imports, runner
from apps.jobs.services import execute_job
from apps.meetings.services.uploads import create_upload

pytestmark = pytest.mark.django_db


def _wav(seconds: int = 30, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


# --- public suite -----------------------------------------------------------
def test_seed_public_dataset_creates_approximate_recordings(user):
    dataset = imports.seed_public_dataset(user, limit=4)
    assert dataset.kind == "public"
    recs = list(dataset.recordings.all())
    assert len(recs) == 4
    # Every public recording is approximate + pending, never exact (req 8).
    for r in recs:
        assert r.ground_truth_type == GroundTruthType.PUBLIC_APPROXIMATE
        assert r.status == RecordingStatus.PENDING
    # Formats/languages span the catalogue (multi-format, multi-language, req 1).
    assert len({r.format for r in recs}) >= 2


def test_seed_public_dataset_is_idempotent(user):
    imports.seed_public_dataset(user, limit=3)
    imports.seed_public_dataset(user, limit=3)
    assert BenchmarkRecording.objects.filter(owner=user).count() == 3


def test_seed_public_via_api(auth_client):
    resp = auth_client.post("/api/benchmarks/datasets/seed-public/", {"limit": 2}, format="json")
    assert resp.status_code == 201
    assert resp.data["data"]["recording_count"] == 2


# --- user suite -------------------------------------------------------------
def _processed_meeting(user, settings, speakers=2):
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = speakers
    f = SimpleUploadedFile("m.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Standup").meeting
    execute_job(str(meeting.meeting_jobs.order_by("-created_at").first().background_job_id))
    meeting.refresh_from_db()
    return meeting


def test_create_user_recording_from_meeting(user, settings):
    meeting = _processed_meeting(user, settings)
    rec = imports.create_user_recording_from_meeting(
        user, meeting=meeting, expected_speaker_count=2,
        known_participants=["Alice", "Bob"], meeting_type="standup",
    )
    assert rec.ground_truth_type == GroundTruthType.USER_VERIFIED
    assert rec.meeting_id == meeting.id
    assert rec.status == RecordingStatus.READY  # meeting already completed
    assert rec.dataset.kind == "user"


def test_from_meeting_rejects_foreign_meeting(user, settings):
    from apps.accounts.models import User

    bob = User.objects.create_user(email="bob@example.com", password="x")
    meeting = _processed_meeting(user, settings)
    with pytest.raises(PermissionError):
        imports.create_user_recording_from_meeting(bob, meeting=meeting, expected_speaker_count=2)


def test_from_meeting_via_api(auth_client, user, settings):
    meeting = _processed_meeting(user, settings)
    resp = auth_client.post(
        "/api/benchmarks/recordings/from-meeting/",
        {"meeting": str(meeting.id), "expected_speaker_count": 2, "known_participants": ["A", "B"]},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["data"]["ground_truth_type"] == GroundTruthType.USER_VERIFIED


# --- full public-import → benchmark path (offline, dummy media provider) -----
def test_public_import_flows_through_pipeline_and_is_benchmarkable(user, settings):
    settings.MEDIA_IMPORT_ENABLED = True
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = 1

    dataset = BenchmarkDataset.objects.create(owner=user, kind="public", name="Offline")
    rec = BenchmarkRecording.objects.create(
        dataset=dataset, owner=user, name="Dummy clip", source_url="dummy://benchmark-clip",
        ground_truth_type=GroundTruthType.PUBLIC_APPROXIMATE, expected_speaker_count=1,
    )

    # Kick off the import (create_import defers dispatch to on_commit, which does
    # not fire inside the test transaction) then run it synchronously.
    session = imports.import_recording(rec)
    assert session is not None
    rec.refresh_from_db()
    assert rec.status == RecordingStatus.IMPORTING

    from apps.meetings.ingest.service import run_import

    run_import(str(session.id))

    # run_import created the meeting + queued its pipeline job, but dispatch is
    # deferred to on_commit (never fires in-transaction) — run it synchronously.
    session.refresh_from_db()
    assert session.meeting_id is not None
    meeting = session.meeting
    execute_job(str(meeting.meeting_jobs.order_by("-created_at").first().background_job_id))

    rec.refresh_from_db()
    # Subscriber backfilled the meeting link + marked READY when the pipeline finished.
    assert rec.meeting_id == meeting.id
    assert rec.status == RecordingStatus.READY

    run = runner.run_benchmark(user, dataset=dataset)
    assert run.recordings_scored == 1
    result = run.results.first()
    assert result.ok is True
    assert result.detected_speaker_count == 1
    assert result.ground_truth_type == GroundTruthType.PUBLIC_APPROXIMATE
