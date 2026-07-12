"""Serializers for the background-jobs API."""
from __future__ import annotations

from rest_framework import serializers

from apps.jobs.models import BackgroundJob, JobLog


class JobLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobLog
        fields = ("id", "stage", "level", "message", "progress", "duration_ms", "metadata", "created_at")
        read_only_fields = fields


class JobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    retry_count = serializers.IntegerField(read_only=True)
    max_retries = serializers.IntegerField(read_only=True)

    class Meta:
        model = BackgroundJob
        fields = (
            "id", "job_type", "job_type_display", "pipeline",
            "status", "status_display", "priority", "priority_display",
            "progress", "current_stage", "queue_name", "worker_id",
            "retry_count", "max_retries", "error_message",
            "duration_ms", "scheduled_at", "started_at", "finished_at",
            "cancelled_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class JobDetailSerializer(JobSerializer):
    logs = JobLogSerializer(source="job_logs", many=True, read_only=True)

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + ("payload", "result", "metadata", "stack_trace", "logs")
        read_only_fields = fields
