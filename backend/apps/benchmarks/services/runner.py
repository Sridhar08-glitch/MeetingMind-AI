"""Benchmark runner + tuning harness (req 3, 6, 7).

Evaluates diarization quality by RE-CLUSTERING the segment embeddings persisted at
processing time (Phase 15) — no Whisper/ECAPA re-run — so a full threshold sweep
over a dataset is cheap. Each (recording × config) produces a BenchmarkResult with
the full req-3 metric set; the run records reproducibility provenance (req 7).

Ground-truth honesty is preserved end-to-end: each result echoes the recording's
``ground_truth_type`` so approximate public counts are never treated as exact.
"""
from __future__ import annotations

import time

from django.utils import timezone

from apps.meetings.models import SpeakerEmbedding, TranscriptSegment

from ..enums import BenchmarkRunStatus
from ..models import BenchmarkResult, BenchmarkRun
from . import clustering, metrics, versioning


def default_config() -> dict:
    from django.conf import settings

    return {
        "name": "default",
        "diarization_provider": getattr(settings, "DIARIZATION_PROVIDER", "embedding"),
        "cluster_threshold": float(getattr(settings, "DIARIZATION_CLUSTER_THRESHOLD", 0.5)),
        "merge_threshold": None,
        "min_speech_duration": 0.0,
        "min_segment_length": float(getattr(settings, "SPEAKER_MIN_EMBED_DURATION", 0.35)),
        "max_speakers": int(getattr(settings, "DIARIZATION_MAX_SPEAKERS", 10)),
        "overlap_handling": "longest",
    }


def _stored_segment_vectors(meeting):
    """(TranscriptSegment, vector) pairs in transcript order, from stored embeddings."""
    segs = list(TranscriptSegment.objects.filter(meeting=meeting).order_by("index"))
    emb = {
        e.segment_index: e.vector
        for e in SpeakerEmbedding.objects.filter(speaker__meeting=meeting, kind="segment")
        if e.segment_index is not None
    }
    return [(s, emb[s.index]) for s in segs if s.index in emb]


def evaluate_recording(recording, config: dict) -> dict:
    """Score one recording under one config. Returns a flat metric dict (+ ok/detail)."""
    base = {
        "ok": False, "detail": "", "expected_speaker_count": recording.expected_speaker_count,
        "detected_speaker_count": None, "correctly_clustered": None, "over_merged": 0,
        "over_split": 0, "cluster_purity": None, "der": None,
        "avg_embedding_confidence": None, "avg_speech_duration": None, "processing_time_ms": None,
    }
    meeting = recording.meeting
    if meeting is None:
        return {**base, "detail": "recording has no processed meeting"}

    pairs = _stored_segment_vectors(meeting)
    if not pairs:
        return {**base, "detail": "no stored segment embeddings (re-process with diarization on)"}

    min_seg = float(config.get("min_segment_length", 0.35) or 0.0)
    clusterable = [(s, v) for s, v in pairs if (s.end_time - s.start_time) >= min_seg]
    short = [(s, v) for s, v in pairs if (s.end_time - s.start_time) < min_seg]
    if not clusterable:  # everything is short — cluster them anyway rather than skip
        clusterable, short = pairs, []

    vectors = [v for _, v in clusterable]
    t0 = time.perf_counter()
    labels, confidence = clustering.cluster_vectors(
        vectors,
        threshold=float(config.get("cluster_threshold", 0.5)),
        max_speakers=int(config.get("max_speakers", 10)),
        merge_threshold=config.get("merge_threshold"),
    )
    cents = clustering.centroids_by_label(vectors, labels)
    short_labels = [clustering.assign_nearest(v, cents) for _, v in short]

    combined_segs = [s for s, _ in clusterable] + [s for s, _ in short]
    combined_vectors = vectors + [v for _, v in short]
    combined_labels = labels + short_labels
    durations = [s.end_time - s.start_time for s in combined_segs]

    msd = float(config.get("min_speech_duration", 0.0) or 0.0)
    if msd > 0:
        combined_labels = clustering.merge_small_speakers(
            combined_vectors, combined_labels, durations, msd
        )
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    detected = [(s.start_time, s.end_time, lbl) for s, lbl in zip(combined_segs, combined_labels)]
    detected_count = len({lbl for _, _, lbl in detected})

    reference = None
    if recording.reference_segments:
        try:
            reference = [
                (float(r["start"]), float(r["end"]), str(r["speaker"]))
                for r in recording.reference_segments
            ]
        except (KeyError, TypeError, ValueError):
            reference = None

    m = metrics.evaluate(
        recording.expected_speaker_count, detected_count, detected=detected, reference=reference
    )
    total_speech = sum(durations)
    avg_speech = round(total_speech / detected_count, 2) if detected_count else 0.0

    return {
        **base,
        "ok": True,
        "detected_speaker_count": detected_count,
        "correctly_clustered": m.get("correctly_clustered"),
        "over_merged": m.get("over_merged", 0),
        "over_split": m.get("over_split", 0),
        "cluster_purity": m.get("cluster_purity"),
        "der": m.get("der"),
        "avg_embedding_confidence": confidence,
        "avg_speech_duration": avg_speech,
        "processing_time_ms": elapsed_ms,
    }


def _aggregate(run: BenchmarkRun, results: list[BenchmarkResult]) -> None:
    scored = [r for r in results if r.ok]
    with_truth = [r for r in scored if r.expected_speaker_count is not None]
    if with_truth:
        exact = sum(1 for r in with_truth if r.detected_speaker_count == r.expected_speaker_count)
        run.speaker_count_accuracy = round(100.0 * exact / len(with_truth), 2)
        run.avg_speaker_count_error = round(
            sum(abs((r.detected_speaker_count or 0) - r.expected_speaker_count) for r in with_truth)
            / len(with_truth), 3
        )
    run.total_over_merged = sum(r.over_merged for r in scored)
    run.total_over_split = sum(r.over_split for r in scored)
    confs = [r.avg_embedding_confidence for r in scored if r.avg_embedding_confidence is not None]
    if confs:
        run.avg_embedding_confidence = round(sum(confs) / len(confs), 2)
    times = [r.processing_time_ms for r in scored if r.processing_time_ms is not None]
    if times:
        run.avg_processing_ms = round(sum(times) / len(times), 2)


def run_benchmark(owner, *, dataset=None, recordings=None, configs=None, label="") -> BenchmarkRun:
    """Execute the harness over a dataset's recordings under one or more configs.

    ``configs`` is a list of config dicts (the tuning sweep, req 6). Synchronous:
    re-clustering is cheap, so a run completes in-process; large fresh imports run
    via the management command / import flow instead.
    """
    prov = versioning.provenance(owner)
    configs = configs or [default_config()]
    recs = list(recordings) if recordings is not None else list(dataset.recordings.all())

    run = BenchmarkRun.objects.create(
        owner=owner, dataset=dataset, label=label, status=BenchmarkRunStatus.RUNNING,
        started_at=timezone.now(), engine_version=prov["engine_version"],
        diarization_engine=prov["diarization_engine"], stt_provider=prov["stt_provider"],
        embedding_model=prov["embedding_model"], git_commit=prov["git_commit"],
        config={"configs": configs}, configs_count=len(configs), recordings_total=len(recs),
    )

    kv = prov["knowledge_version"]
    result_rows: list[BenchmarkResult] = []
    scored_recordings = set()
    for rec in recs:
        for cfg in configs:
            ev = evaluate_recording(rec, cfg)
            if ev["ok"]:
                scored_recordings.add(rec.id)
            result_rows.append(BenchmarkResult(
                run=run, recording=rec, owner=owner, recording_name=rec.name,
                config=cfg, config_label=cfg.get("name", ""),
                expected_speaker_count=rec.expected_speaker_count,
                detected_speaker_count=ev["detected_speaker_count"],
                correctly_clustered=ev["correctly_clustered"],
                over_merged=ev["over_merged"], over_split=ev["over_split"],
                avg_embedding_confidence=ev["avg_embedding_confidence"],
                avg_speech_duration=ev["avg_speech_duration"],
                processing_time_ms=ev["processing_time_ms"],
                diarization_engine=prov["diarization_engine"], stt_provider=prov["stt_provider"],
                embedding_model=prov["embedding_model"], knowledge_version=kv,
                ground_truth_type=rec.ground_truth_type, der=ev["der"],
                cluster_purity=ev["cluster_purity"], ok=ev["ok"], detail=ev["detail"],
            ))
    BenchmarkResult.objects.bulk_create(result_rows)

    _aggregate(run, result_rows)
    run.recordings_scored = len(scored_recordings)
    run.status = BenchmarkRunStatus.COMPLETED
    run.finished_at = timezone.now()
    run.save()
    return run


def compare_configs(run: BenchmarkRun) -> list[dict]:
    """Group a run's results by config → a comparison report (req 6)."""
    buckets: dict[str, list[BenchmarkResult]] = {}
    for r in run.results.all():
        buckets.setdefault(r.config_label or "default", []).append(r)

    report = []
    for label, rows in buckets.items():
        with_truth = [r for r in rows if r.ok and r.expected_speaker_count is not None]
        exact = sum(1 for r in with_truth if r.detected_speaker_count == r.expected_speaker_count)
        confs = [r.avg_embedding_confidence for r in rows if r.avg_embedding_confidence is not None]
        times = [r.processing_time_ms for r in rows if r.processing_time_ms is not None]
        report.append({
            "config_label": label,
            "config": rows[0].config if rows else {},
            "recordings": len(rows),
            "speaker_count_accuracy": round(100.0 * exact / len(with_truth), 2) if with_truth else None,
            "total_over_merged": sum(r.over_merged for r in rows),
            "total_over_split": sum(r.over_split for r in rows),
            "avg_embedding_confidence": round(sum(confs) / len(confs), 2) if confs else None,
            "avg_processing_ms": round(sum(times) / len(times), 2) if times else None,
        })
    report.sort(key=lambda x: (x["speaker_count_accuracy"] or -1), reverse=True)
    return report
