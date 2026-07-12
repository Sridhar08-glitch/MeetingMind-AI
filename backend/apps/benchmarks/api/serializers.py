"""DRF serializers for the benchmarking suite."""
from __future__ import annotations

from rest_framework import serializers

from apps.benchmarks.enums import BenchmarkDatasetKind, GroundTruthType
from apps.benchmarks.models import (
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkRecording,
    BenchmarkResult,
    BenchmarkRun,
)


class BenchmarkDatasetSerializer(serializers.ModelSerializer):
    recording_count = serializers.SerializerMethodField()

    class Meta:
        model = BenchmarkDataset
        fields = ("id", "kind", "name", "slug", "description", "recording_count", "created_at")
        read_only_fields = ("id", "slug", "recording_count", "created_at")

    def get_recording_count(self, obj) -> int:
        return getattr(obj, "recording_count", None) or obj.recordings.count()


class BenchmarkRecordingSerializer(serializers.ModelSerializer):
    ground_truth_is_exact = serializers.SerializerMethodField()
    meeting_id = serializers.UUIDField(source="meeting.id", read_only=True, allow_null=True)

    class Meta:
        model = BenchmarkRecording
        fields = (
            "id", "dataset", "name", "format", "language", "source_url", "source_kind",
            "ground_truth_type", "expected_speaker_count", "known_participants",
            "meeting_type", "notes", "reference_segments",
            "meeting_id", "status", "status_detail", "ground_truth_is_exact", "created_at",
        )
        read_only_fields = ("id", "meeting_id", "status", "status_detail", "created_at")

    def get_ground_truth_is_exact(self, obj) -> bool:
        # Only user-verified counts may be presented as exact (req 8).
        return obj.ground_truth_type == GroundTruthType.USER_VERIFIED

    def validate(self, attrs):
        # Default the ground-truth type from the dataset kind if the caller omitted it.
        dataset = attrs.get("dataset") or getattr(self.instance, "dataset", None)
        if dataset and not attrs.get("ground_truth_type") and not getattr(self.instance, "ground_truth_type", ""):
            attrs["ground_truth_type"] = (
                GroundTruthType.PUBLIC_APPROXIMATE
                if dataset.kind == BenchmarkDatasetKind.PUBLIC
                else GroundTruthType.USER_VERIFIED
            )
        return attrs


class BenchmarkConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenchmarkConfig
        fields = (
            "id", "name", "diarization_provider", "cluster_threshold", "merge_threshold",
            "min_speech_duration", "min_segment_length", "max_speakers", "overlap_handling",
            "is_default", "created_at",
        )
        read_only_fields = ("id", "created_at")


class BenchmarkResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenchmarkResult
        fields = (
            "id", "run", "recording", "recording_name", "config_label", "config",
            "expected_speaker_count", "detected_speaker_count", "correctly_clustered",
            "over_merged", "over_split", "avg_embedding_confidence", "avg_speech_duration",
            "processing_time_ms", "diarization_engine", "stt_provider", "embedding_model",
            "knowledge_version", "ground_truth_type", "der", "cluster_purity", "ok", "detail",
            "created_at",
        )
        read_only_fields = fields


class BenchmarkRunSerializer(serializers.ModelSerializer):
    result_count = serializers.SerializerMethodField()

    class Meta:
        model = BenchmarkRun
        fields = (
            "id", "dataset", "label", "status", "engine_version", "diarization_engine",
            "stt_provider", "embedding_model", "git_commit", "config",
            "recordings_total", "recordings_scored", "configs_count",
            "speaker_count_accuracy", "avg_speaker_count_error", "total_over_merged",
            "total_over_split", "avg_embedding_confidence", "avg_processing_ms",
            "error_message", "started_at", "finished_at", "result_count", "created_at",
        )
        read_only_fields = fields

    def get_result_count(self, obj) -> int:
        return getattr(obj, "result_count", None) or obj.results.count()


class BenchmarkRunDetailSerializer(BenchmarkRunSerializer):
    results = BenchmarkResultSerializer(many=True, read_only=True)

    class Meta(BenchmarkRunSerializer.Meta):
        fields = BenchmarkRunSerializer.Meta.fields + ("results",)
