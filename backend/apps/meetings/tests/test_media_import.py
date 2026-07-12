"""Phase 14 — media import session → create_upload → existing pipeline.

Uses the no-network DummyMediaProvider (``dummy://`` URLs). Proves that an import
becomes a real, source-tagged Meeting that runs the SAME pipeline as an upload,
plus duplicate detection and the capabilities/API surface. No provider does any
AI work — it only produces a file and hands off to create_upload.
"""
from __future__ import annotations

import pytest

from apps.jobs.services import execute_job
from apps.meetings.enums import DuplicateAction, MeetingSource, ProcessingStatus
from apps.meetings.ingest import service as ingest
from apps.meetings.ingest.models import MediaImportStatus
from apps.meetings.models import Meeting, Transcript

pytestmark = pytest.mark.django_db


def _run_meeting_pipeline(meeting):
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))
    meeting.refresh_from_db()
    return job


# --- end-to-end: import → pipeline ------------------------------------------
def test_dummy_import_becomes_meeting_and_runs_pipeline(user):
    session = ingest.create_import(
        user, url="dummy://cc-clip", requested_media="audio",
        transcript_language="original", ai_language="", on_duplicate=DuplicateAction.KEEP_BOTH,
    )
    ingest.run_import(str(session.id))  # Celery bypassed in tests
    session.refresh_from_db()

    assert session.status == MediaImportStatus.PROCESSING
    meeting = session.meeting
    assert meeting is not None
    assert meeting.source == MeetingSource.PUBLIC_VIDEO
    assert meeting.source_url == "dummy://cc-clip"
    assert meeting.source_metadata.get("platform") == "Dummy"
    assert meeting.source_metadata.get("importer_version")
    assert meeting.source_metadata.get("imported_at")

    # Same pipeline as an upload → transcript + completed status.
    _run_meeting_pipeline(meeting)
    assert meeting.processing_status == ProcessingStatus.COMPLETED
    assert Transcript.objects.get(meeting=meeting).word_count > 0

    # Subscriber flips the import session to COMPLETED when processing finishes.
    session.refresh_from_db()
    assert session.status == MediaImportStatus.COMPLETED


def test_import_carries_language_config(user):
    session = ingest.create_import(
        user, url="dummy://multilingual", requested_media="audio",
        meeting_language="en", transcript_language="ar", ai_language="ar",
        on_duplicate=DuplicateAction.KEEP_BOTH,
    )
    ingest.run_import(str(session.id))
    meeting = Meeting.objects.get(import_session=session)
    assert meeting.transcript_language == "ar"
    assert meeting.ai_language == "ar"


# --- duplicate detection ----------------------------------------------------
def test_url_duplicate_is_detected_before_download(user):
    first = ingest.create_import(user, url="dummy://same", on_duplicate=DuplicateAction.KEEP_BOTH)
    ingest.run_import(str(first.id))
    first.refresh_from_db()

    # Second import of the SAME url, default reject → flagged as duplicate, no meeting.
    second = ingest.create_import(user, url="dummy://same", on_duplicate=DuplicateAction.REJECT)
    second.refresh_from_db()
    assert second.status == MediaImportStatus.FAILED
    assert second.error_code == "duplicate_import"
    assert second.duplicate_meeting_id == first.meeting_id


def test_duplicate_skip_links_existing(user):
    first = ingest.create_import(user, url="dummy://skip", on_duplicate=DuplicateAction.KEEP_BOTH)
    ingest.run_import(str(first.id))
    first.refresh_from_db()

    skip = ingest.create_import(user, url="dummy://skip", on_duplicate=DuplicateAction.IGNORE)
    skip.refresh_from_db()
    assert skip.status == MediaImportStatus.COMPLETED
    assert skip.meeting_id == first.meeting_id


# --- API surface ------------------------------------------------------------
def test_media_sources_endpoint(auth_client):
    resp = auth_client.get("/api/media/sources/")
    assert resp.status_code == 200
    assert resp.data["import_available"] is True
    ids = {p["id"] for p in resp.data["providers"]}
    assert {"public_video", "direct_url", "podcast_rss"} <= ids
    assert "dummy" not in ids  # test provider hidden


def test_import_analyze_endpoint(auth_client):
    resp = auth_client.post("/api/meetings/import/analyze/", {"url": "dummy://preview"}, format="json")
    assert resp.status_code == 200
    result = resp.data["data"]["results"][0]
    assert result["ok"] is True
    assert result["info"]["platform"] == "Dummy"


def test_import_create_endpoint_returns_session(auth_client):
    resp = auth_client.post(
        "/api/meetings/import/",
        {"url": "dummy://api", "requested_media": "audio", "on_duplicate": "keep_both"},
        format="json",
    )
    assert resp.status_code == 201
    imports = resp.data["data"]["imports"]
    assert len(imports) == 1
    assert imports[0]["source_url"] == "dummy://api"


def test_import_rejects_private_url(auth_client):
    resp = auth_client.post(
        "/api/meetings/import/", {"url": "http://127.0.0.1/evil.mp4"}, format="json",
    )
    assert resp.status_code == 201  # per-item outcome, not a request error
    item = resp.data["data"]["imports"][0]
    assert item["status"] == "blocked"


def test_batch_import_isolates_failures(auth_client):
    resp = auth_client.post(
        "/api/meetings/import/",
        {"urls": ["dummy://a", "ftp://bad/x", "dummy://b"], "on_duplicate": "keep_both"},
        format="json",
    )
    assert resp.status_code == 201
    imports = resp.data["data"]["imports"]
    assert len(imports) == 3
    blocked = [i for i in imports if i.get("status") == "blocked"]
    assert len(blocked) == 1  # only the ftp:// one; the two dummies proceed
