"""Speaker-diarization benchmarking & evaluation framework (Phase 15).

A reproducible evaluation harness — NOT a one-off test. Datasets group recordings
(public, imported via Phase 14; or a user's own meetings). A BenchmarkRun executes
the diarization engine under one or more configurations against a dataset and
records a BenchmarkResult per recording × configuration, plus reproducibility
provenance (engine version, providers, git commit, config). Every run is retained
so accuracy can be tracked across engine/config changes over time (req 7).

Honesty is modelled, not just documented: each recording carries a
``ground_truth_type`` and each result echoes it, so approximate public counts are
never rendered as exact measurements (req 8).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel

from .enums import (
    BenchmarkDatasetKind,
    BenchmarkRunStatus,
    GroundTruthType,
    OverlapHandling,
    RecordingFormat,
    RecordingStatus,
)


class BenchmarkDataset(BaseModel):
    """A named collection of recordings to benchmark. Owner-scoped; a ``public``
    dataset uses legally-accessible recordings (approximate truth) while a ``user``
    dataset holds the owner's own meetings (higher-confidence truth)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="benchmark_datasets"
    )
    kind = models.CharField(max_length=16, choices=BenchmarkDatasetKind.choices)
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=80, blank=True, db_index=True)  # public-catalog identity
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "kind"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"

    @property
    def default_ground_truth_type(self) -> str:
        return (
            GroundTruthType.PUBLIC_APPROXIMATE
            if self.kind == BenchmarkDatasetKind.PUBLIC
            else GroundTruthType.USER_VERIFIED
        )


class BenchmarkRecording(BaseModel):
    """One recording in a dataset, with its ground truth and a link into the real
    pipeline (a processed Meeting). Public recordings are imported via Phase 14;
    user recordings point at the user's own uploaded meeting."""

    dataset = models.ForeignKey(BenchmarkDataset, on_delete=models.CASCADE, related_name="recordings")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="benchmark_recordings"
    )
    name = models.CharField(max_length=255)
    format = models.CharField(max_length=16, choices=RecordingFormat.choices, default=RecordingFormat.OTHER)
    language = models.CharField(max_length=16, blank=True)  # expected language code
    source_url = models.URLField(max_length=1024, blank=True)
    source_kind = models.CharField(max_length=32, blank=True)  # public_video/podcast/direct_url/upload

    # --- ground truth (honesty is first-class) ---------------------------
    ground_truth_type = models.CharField(
        max_length=24, choices=GroundTruthType.choices, default=GroundTruthType.UNKNOWN
    )
    expected_speaker_count = models.PositiveSmallIntegerField(null=True, blank=True)
    known_participants = models.JSONField(default=list, blank=True)  # list[str]
    meeting_type = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    # Optional per-segment reference labels (RTTM-style) for high-confidence eval:
    # [{"start": float, "end": float, "speaker": str}]. Enables cluster-purity/DER.
    reference_segments = models.JSONField(default=list, blank=True)

    # --- linkage into the real pipeline ----------------------------------
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="benchmark_recordings",
    )
    import_session = models.ForeignKey(
        "meetings.MediaImportSession", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="benchmark_recordings",
    )
    status = models.CharField(
        max_length=16, choices=RecordingStatus.choices, default=RecordingStatus.PENDING, db_index=True
    )
    status_detail = models.CharField(max_length=255, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["dataset", "status"]), models.Index(fields=["owner"])]

    def __str__(self) -> str:
        return self.name

    @property
    def has_reference_segments(self) -> bool:
        return bool(self.reference_segments)


class BenchmarkConfig(BaseModel):
    """A named tuning configuration — the knobs the harness sweeps (req 6)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="benchmark_configs"
    )
    name = models.CharField(max_length=120)
    diarization_provider = models.CharField(max_length=32, default="embedding")
    cluster_threshold = models.FloatField(default=0.5)
    # Post-clustering merge of near-identical centroids (VoicePerson-style); null = off.
    merge_threshold = models.FloatField(null=True, blank=True)
    min_speech_duration = models.FloatField(default=0.0)   # drop/merge speakers below this (secs)
    min_segment_length = models.FloatField(default=0.35)   # segments shorter excluded from clustering
    max_speakers = models.PositiveSmallIntegerField(default=10)
    overlap_handling = models.CharField(
        max_length=12, choices=OverlapHandling.choices, default=OverlapHandling.LONGEST
    )
    is_default = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "is_default"])]

    def __str__(self) -> str:
        return f"{self.name} (thr={self.cluster_threshold})"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "diarization_provider": self.diarization_provider,
            "cluster_threshold": self.cluster_threshold,
            "merge_threshold": self.merge_threshold,
            "min_speech_duration": self.min_speech_duration,
            "min_segment_length": self.min_segment_length,
            "max_speakers": self.max_speakers,
            "overlap_handling": self.overlap_handling,
        }


class BenchmarkRun(BaseModel):
    """One execution of the harness over a dataset. Retained forever for
    regression tracking (req 7). ``config`` snapshots the configuration(s) used."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="benchmark_runs"
    )
    dataset = models.ForeignKey(
        BenchmarkDataset, on_delete=models.SET_NULL, null=True, blank=True, related_name="runs"
    )
    label = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=16, choices=BenchmarkRunStatus.choices, default=BenchmarkRunStatus.PENDING
    )

    # --- reproducibility / provenance (req 7) ----------------------------
    engine_version = models.CharField(max_length=32, blank=True)   # benchmark engine version
    diarization_engine = models.CharField(max_length=64, blank=True)
    stt_provider = models.CharField(max_length=64, blank=True)
    embedding_model = models.CharField(max_length=128, blank=True)
    git_commit = models.CharField(max_length=64, blank=True)       # "" when not a git repo
    config = models.JSONField(default=dict, blank=True)            # snapshot of config(s) swept

    # --- aggregate metrics -----------------------------------------------
    recordings_total = models.PositiveIntegerField(default=0)
    recordings_scored = models.PositiveIntegerField(default=0)
    configs_count = models.PositiveIntegerField(default=1)
    speaker_count_accuracy = models.FloatField(null=True, blank=True)  # % detected==expected
    avg_speaker_count_error = models.FloatField(null=True, blank=True)  # mean |detected-expected|
    total_over_merged = models.PositiveIntegerField(default=0)
    total_over_split = models.PositiveIntegerField(default=0)
    avg_embedding_confidence = models.FloatField(null=True, blank=True)
    avg_processing_ms = models.FloatField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return self.label or f"Benchmark run {self.id}"


class BenchmarkResult(BaseModel):
    """Per-recording × per-configuration metrics (req 3). ``ground_truth_type``
    is echoed here so a report never presents approximate counts as exact."""

    run = models.ForeignKey(BenchmarkRun, on_delete=models.CASCADE, related_name="results")
    recording = models.ForeignKey(
        BenchmarkRecording, on_delete=models.SET_NULL, null=True, blank=True, related_name="results"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="benchmark_results"
    )
    recording_name = models.CharField(max_length=255, blank=True)  # denormalized for reports
    config = models.JSONField(default=dict, blank=True)            # the exact config for this row
    config_label = models.CharField(max_length=120, blank=True)

    # --- required metrics (req 3) ----------------------------------------
    expected_speaker_count = models.PositiveSmallIntegerField(null=True, blank=True)
    detected_speaker_count = models.PositiveSmallIntegerField(null=True, blank=True)
    correctly_clustered = models.IntegerField(null=True, blank=True)
    over_merged = models.IntegerField(default=0)
    over_split = models.IntegerField(default=0)
    avg_embedding_confidence = models.FloatField(null=True, blank=True)
    avg_speech_duration = models.FloatField(null=True, blank=True)
    processing_time_ms = models.FloatField(null=True, blank=True)
    diarization_engine = models.CharField(max_length=64, blank=True)
    stt_provider = models.CharField(max_length=64, blank=True)
    embedding_model = models.CharField(max_length=128, blank=True)
    knowledge_version = models.IntegerField(null=True, blank=True)

    # --- honesty + optional high-confidence segment metrics --------------
    ground_truth_type = models.CharField(
        max_length=24, choices=GroundTruthType.choices, default=GroundTruthType.UNKNOWN
    )
    der = models.FloatField(null=True, blank=True)            # diarization error rate (if reference)
    cluster_purity = models.FloatField(null=True, blank=True)  # 0-1 (if reference segments)
    ok = models.BooleanField(default=True)                    # False if this recording errored
    detail = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["run", "config_label"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.recording_name}: {self.detected_speaker_count}/{self.expected_speaker_count}"

    @property
    def exact_speaker_count(self) -> bool:
        """True only when the expected count is user-verified — reports must not
        present a public-approximate expected count as an exact measurement."""
        return self.ground_truth_type == GroundTruthType.USER_VERIFIED
