"""Runner + tuning-harness tests.

Processes a meeting through the dummy diarization pipeline (so real
SpeakerEmbedding rows exist), then benchmarks it by re-clustering those stored
embeddings — proving the harness needs no re-transcription.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.benchmarks.enums import BenchmarkDatasetKind, GroundTruthType, RecordingFormat
from apps.benchmarks.models import BenchmarkDataset, BenchmarkRecording, BenchmarkResult
from apps.benchmarks.services import runner
from apps.jobs.services import execute_job
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


def _processed_meeting(user, settings, speakers: int = 1):
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = speakers
    f = SimpleUploadedFile("talk.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Talk").meeting
    execute_job(str(meeting.meeting_jobs.order_by("-created_at").first().background_job_id))
    meeting.refresh_from_db()
    return meeting


def _recording(user, meeting, **kwargs):
    ds = BenchmarkDataset.objects.create(owner=user, kind=BenchmarkDatasetKind.USER, name="Set")
    defaults = dict(
        dataset=ds, owner=user, name="Rec", format=RecordingFormat.MEETING,
        ground_truth_type=GroundTruthType.USER_VERIFIED, meeting=meeting,
    )
    defaults.update(kwargs)
    return BenchmarkRecording.objects.create(**defaults)


def test_evaluate_recording_uses_stored_embeddings(user, settings):
    meeting = _processed_meeting(user, settings, speakers=1)
    rec = _recording(user, meeting, expected_speaker_count=1)
    ev = runner.evaluate_recording(rec, runner.default_config())
    assert ev["ok"] is True
    assert ev["detected_speaker_count"] == 1
    assert ev["over_merged"] == 0 and ev["over_split"] == 0
    assert ev["processing_time_ms"] is not None
    assert ev["avg_embedding_confidence"] is not None


def test_run_benchmark_creates_run_and_results(user, settings):
    meeting = _processed_meeting(user, settings, speakers=1)
    rec = _recording(user, meeting, expected_speaker_count=1)
    run = runner.run_benchmark(user, dataset=rec.dataset, label="t1")
    run.refresh_from_db()
    assert run.status == "completed"
    assert run.recordings_total == 1 and run.recordings_scored == 1
    assert run.speaker_count_accuracy == 100.0
    # Provenance captured (req 7).
    assert run.engine_version and run.diarization_engine == "dummy"
    assert run.stt_provider  # from settings
    results = BenchmarkResult.objects.filter(run=run)
    assert results.count() == 1
    r = results.first()
    assert r.detected_speaker_count == 1
    assert r.ground_truth_type == GroundTruthType.USER_VERIFIED


def test_tuning_harness_multiple_configs(user, settings):
    meeting = _processed_meeting(user, settings, speakers=1)
    rec = _recording(user, meeting, expected_speaker_count=1)
    base = runner.default_config()
    configs = [
        {**base, "name": "tight", "cluster_threshold": 0.3},
        {**base, "name": "loose", "cluster_threshold": 0.8},
    ]
    run = runner.run_benchmark(user, dataset=rec.dataset, configs=configs)
    assert run.configs_count == 2
    assert BenchmarkResult.objects.filter(run=run).count() == 2  # 1 recording × 2 configs

    report = runner.compare_configs(run)
    assert {row["config_label"] for row in report} == {"tight", "loose"}
    for row in report:
        assert row["recordings"] == 1


def test_reference_segments_yield_segment_level_metrics(user, settings):
    meeting = _processed_meeting(user, settings, speakers=1)
    # One reference speaker spanning the whole meeting → perfect purity for 1 cluster.
    rec = _recording(
        user, meeting, expected_speaker_count=1,
        reference_segments=[{"start": 0.0, "end": 40.0, "speaker": "A"}],
    )
    ev = runner.evaluate_recording(rec, runner.default_config())
    assert ev["cluster_purity"] is not None
    assert ev["der"] is not None


def test_recording_without_meeting_is_not_scored(user, settings):
    rec = _recording(user, None, expected_speaker_count=2)
    ev = runner.evaluate_recording(rec, runner.default_config())
    assert ev["ok"] is False
    assert "no processed meeting" in ev["detail"]


def test_run_via_api(auth_client, user, settings):
    meeting = _processed_meeting(user, settings, speakers=1)
    rec = _recording(user, meeting, expected_speaker_count=1)
    resp = auth_client.post(
        "/api/benchmarks/runs/run/", {"dataset": str(rec.dataset.id), "label": "api"}, format="json"
    )
    assert resp.status_code == 201
    run_id = resp.data["data"]["id"]
    cmp_resp = auth_client.get(f"/api/benchmarks/runs/{run_id}/compare/")
    assert cmp_resp.status_code == 200
    assert cmp_resp.data["data"]["comparison"]
