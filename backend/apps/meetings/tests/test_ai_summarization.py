"""Phase 7 tests: LLM providers, chunking, AI analysis, storage, API, versioning.

All tests run on the deterministic DummyLLMProvider (forced via conftest) — no
Ollama server, no model downloads.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.factories import UserFactory
from apps.jobs.services import execute_job
from apps.meetings.models import AIAnalysis
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.ai import AISummarizationService, AIValidationError, validate_analysis
from apps.meetings.services.chunking import chunk_text
from apps.meetings.services.llm import DummyLLMProvider, get_llm_provider
from apps.meetings.services.uploads import create_upload

pytestmark = pytest.mark.django_db


def make_wav_bytes(seconds: int = 40, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def _upload_and_run(user):
    f = SimpleUploadedFile("t.wav", make_wav_bytes(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Talk").meeting
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))
    meeting.refresh_from_db()
    return meeting


@pytest.fixture
def analyzed(user):
    return _upload_and_run(user)


# --- graceful degradation ---------------------------------------------------
def test_ai_failure_keeps_transcript_and_completes(user, monkeypatch):
    """If the model can't summarize (invalid JSON), the meeting still COMPLETES
    with the transcript + a fallback summary — it is not marked failed."""
    from apps.meetings.enums import ProcessingStatus
    from apps.meetings.models import Transcript
    from apps.meetings.services import ai as ai_module
    from apps.meetings.services.media import ProcessingError

    def boom(self, *a, **k):
        raise ProcessingError("LLM did not return valid JSON after retry: no summary produced",
                              code="ai_invalid_json", retryable=False)

    monkeypatch.setattr(ai_module.AISummarizationService, "analyze", boom)
    meeting = _upload_and_run(user)

    assert meeting.processing_status == ProcessingStatus.COMPLETED  # not FAILED
    assert Transcript.objects.filter(meeting=meeting).exists()      # transcript preserved
    analysis = meeting.analyses.filter(is_current=True).first()
    assert analysis is not None and analysis.executive_summary      # fallback summary stored


# --- provider selection -----------------------------------------------------
def test_dummy_llm_selected_in_tests():
    assert isinstance(get_llm_provider(), DummyLLMProvider)


def test_ollama_is_default(settings):
    settings.AI_PROVIDER = "ollama"
    from apps.meetings.services.llm import OllamaProvider

    assert isinstance(get_llm_provider(), OllamaProvider)


# --- prompts ----------------------------------------------------------------
def test_prompt_registry_versioned():
    p = prompt_registry.get("meeting_analysis")
    assert p.version
    assert "JSON" in p.system
    assert "meeting_analysis" in prompt_registry._prompts


# --- chunking ---------------------------------------------------------------
def test_short_text_single_chunk():
    assert chunk_text("hello world", size=100, overlap=10) == ["hello world"]


def test_long_text_chunks_with_overlap():
    text = ". ".join(f"Sentence number {i}" for i in range(400))
    chunks = chunk_text(text, size=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 700 for c in chunks)


# --- validation -------------------------------------------------------------
def test_validate_normalizes_partial_json():
    out = validate_analysis({"executive_summary": "Hi", "action_items": [{"task": "Do X"}], "keywords": {"topics": ["a"]}})
    assert out["executive_summary"] == "Hi"
    assert out["action_items"][0]["task"] == "Do X"
    assert out["action_items"][0]["owner"] == ""       # defaulted
    assert out["keywords"]["technologies"] == []       # defaulted bucket


def test_validate_rejects_missing_summary():
    with pytest.raises(AIValidationError):
        validate_analysis({"action_items": []})


# --- service ----------------------------------------------------------------
def test_service_produces_all_artifacts():
    result = AISummarizationService().analyze("A meeting transcript about migration and budget.")
    p = result.parsed
    assert result.provider == "dummy"
    assert p["executive_summary"]
    assert p["detailed_summary"]
    assert p["meeting_minutes"]
    assert len(p["action_items"]) >= 1
    assert len(p["decisions"]) >= 1
    assert len(p["risks"]) >= 1
    assert p["keywords"]["topics"]


# --- pipeline end-to-end ----------------------------------------------------
def test_pipeline_stores_ai_analysis(analyzed):
    a = AIAnalysis.objects.get(meeting=analyzed, is_current=True)
    assert a.version == 1
    assert a.provider == "dummy"
    assert a.prompt_version
    assert a.executive_summary
    assert a.action_items and a.decisions and a.keywords
    assert a.parsed_response  # full parsed JSON retained
    assert a.raw_response     # raw LLM response retained


def test_pipeline_logs_ai_stages(analyzed):
    job = analyzed.meeting_jobs.order_by("created_at").first().background_job
    stages = set(job.job_logs.exclude(stage="").values_list("stage", flat=True))
    assert {"ai_analysis", "store_ai_results"} <= stages


# --- versioning / regenerate ------------------------------------------------
def test_regenerate_creates_new_version_without_overwriting(analyzed):
    from apps.meetings.services.uploads import enqueue_ai_summarization

    v1 = AIAnalysis.objects.get(meeting=analyzed, is_current=True)
    enqueue_ai_summarization(analyzed, model=None)
    job = analyzed.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))

    assert AIAnalysis.all_objects.filter(meeting=analyzed).count() == 2
    v1.refresh_from_db()
    assert v1.is_current is False                      # previous result preserved, not overwritten
    current = AIAnalysis.objects.get(meeting=analyzed, is_current=True)
    assert current.version == 2


# --- API --------------------------------------------------------------------
def test_ai_api_endpoints(auth_client, user):
    meeting = _upload_and_run(user)

    resp = auth_client.get(f"/api/meetings/{meeting.id}/ai/")
    assert resp.status_code == 200
    assert resp.data["data"]["executive_summary"]
    assert resp.data["data"]["version"] == 1

    for field in ("action-items", "decisions", "risks", "keywords"):
        r = auth_client.get(f"/api/meetings/{meeting.id}/ai/{field}/")
        assert r.status_code == 200

    hist = auth_client.get(f"/api/meetings/{meeting.id}/ai/history/")
    assert hist.status_code == 200
    assert len(hist.data["data"]) == 1

    regen = auth_client.post(f"/api/meetings/{meeting.id}/ai/regenerate/", {}, format="json")
    assert regen.status_code == 200


def test_ai_not_owner_forbidden(auth_client, api_client, user):
    meeting = _upload_and_run(user)
    other = UserFactory()
    login = api_client.post(
        "/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api_client.get(f"/api/meetings/{meeting.id}/ai/").status_code in (403, 404)
