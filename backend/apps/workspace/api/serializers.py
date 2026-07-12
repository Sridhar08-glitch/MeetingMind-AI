"""Serializers for the workspace API."""
from __future__ import annotations

from rest_framework import serializers

from apps.workspace.models import (
    ActivityLog,
    AISuggestion,
    Decision,
    FollowUp,
    Issue,
    Milestone,
    Note,
    Notification,
    Project,
    Report,
    Risk,
    Task,
    TaskComment,
    VoicePerson,
    VoicePersonEvent,
    Workspace,
)

# Explainability fields shared by AI-sourced entities.
EXPLAIN_FIELDS = (
    "confidence", "confidence_score", "source_segment_index", "source_start_time",
    "source_speaker", "source_quote", "source_reason", "suggestion",
)


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ("id", "name", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class VoicePersonSerializer(serializers.ModelSerializer):
    """Cross-meeting voice identity (Phase 15B). Excludes the raw embedding vectors
    (internal signature) — only identity + rolled-up analytics are exposed."""

    class Meta:
        model = VoicePerson
        fields = (
            "id", "workspace", "display_name", "aliases", "avatar", "email", "department",
            "role", "confirmed", "confidence", "embedding_dimensions", "meeting_count",
            "speaker_count", "total_talk_time", "total_word_count", "avg_embedding_quality",
            "last_seen", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "confidence", "embedding_dimensions", "meeting_count", "speaker_count",
            "total_talk_time", "total_word_count", "avg_embedding_quality", "last_seen",
            "created_at", "updated_at",
        )


class VoicePersonEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoicePersonEvent
        fields = ("id", "event_type", "speaker_id", "meeting_id", "confidence", "tier",
                  "detail", "created_at")
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "workspace", "name", "description", "status", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ("id", "project", "name", "description", "target_date", "completion_percentage", "created_at")
        read_only_fields = ("id", "created_at")


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = (
            "id", "project", "meeting", "milestone", "title", "description", "assignee",
            "priority", "status", "category", "tags", "labels", "watchers", "checklist",
            "due_date", "estimated_minutes", "dependencies", "completion_notes", "order",
            "created_by_ai", "manual_override", "source_analysis_version", "created_at", "updated_at",
        ) + EXPLAIN_FIELDS
        read_only_fields = ("id", "created_by_ai", "source_analysis_version", "created_at", "updated_at") + EXPLAIN_FIELDS


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = (
            "id", "project", "meeting", "title", "description", "issue_type", "severity",
            "priority", "status", "assignee", "related_tasks", "created_by_ai", "created_at", "updated_at",
        ) + EXPLAIN_FIELDS
        read_only_fields = ("id", "created_by_ai", "created_at", "updated_at") + EXPLAIN_FIELDS


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = (
            "id", "project", "meeting", "decision", "reason", "participants", "impact",
            "status", "decided_at", "created_by_ai", "created_at",
        ) + EXPLAIN_FIELDS
        read_only_fields = ("id", "created_by_ai", "created_at") + EXPLAIN_FIELDS


class RiskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Risk
        fields = (
            "id", "project", "meeting", "risk", "severity", "probability", "mitigation",
            "assignee", "status", "created_by_ai", "created_at",
        ) + EXPLAIN_FIELDS
        read_only_fields = ("id", "created_by_ai", "created_at") + EXPLAIN_FIELDS


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = ("id", "project", "meeting", "item", "assignee", "due_date", "status",
                  "created_by_ai", "created_at") + EXPLAIN_FIELDS
        read_only_fields = ("id", "created_by_ai", "created_at") + EXPLAIN_FIELDS


class AISuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AISuggestion
        fields = (
            "id", "meeting", "suggestion_type", "status", "title", "generated_json",
            "original_json", "edited_json", "confidence", "confidence_score", "reason",
            "source_segment_index", "source_start_time", "source_speaker", "quote",
            "reviewer_notes", "converted_to_type", "converted_to_id", "approved_at", "created_at",
        )
        read_only_fields = fields


class ApproveSuggestionSerializer(serializers.Serializer):
    edited = serializers.JSONField(required=False, default=dict)
    reviewer_notes = serializers.CharField(required=False, allow_blank=True, default="")
    on_duplicate = serializers.ChoiceField(
        choices=["create", "merge", "update"], required=False, default="create"
    )


class RejectSuggestionSerializer(serializers.Serializer):
    reviewer_notes = serializers.CharField(required=False, allow_blank=True, default="")


class BulkActionSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    action = serializers.ChoiceField(choices=["approve", "reject", "archive"])


class TaskCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ("id", "task", "body", "author", "created_at")
        read_only_fields = ("id", "author", "created_at")

    def get_author(self, obj):
        return obj.owner.email if obj.owner_id else None


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ("id", "verb", "entity_type", "entity_id", "summary", "meeting", "metadata", "created_at")
        read_only_fields = fields


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ("id", "project", "meeting", "title", "content", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = (
            "id", "project", "meeting", "report_type", "title", "content", "version",
            "is_current", "model_used", "provider", "prompt_version", "inference_ms", "created_at",
        )
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "notification_type", "title", "message", "is_read", "meeting", "task", "created_at")
        read_only_fields = ("id", "notification_type", "title", "message", "meeting", "task", "created_at")


class TaskMoveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Task._meta.get_field("status").choices)
    order = serializers.IntegerField(required=False, default=0)


class GenerateReportSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=Report._meta.get_field("report_type").choices)
    meeting = serializers.UUIDField(required=False, allow_null=True)
    project = serializers.UUIDField(required=False, allow_null=True)
