"""MeetingMind workspace models — native productivity suite (Phase 9).

Hierarchy: Workspace → Project → Meeting → Tasks/Issues/Reports. Everything is
owner-scoped for future team workspaces.

**Human-in-the-loop:** AI never silently creates live records. It creates
:class:`AISuggestion` rows (pending) with a confidence score and full
explainability (source meeting, speaker, timestamp, quote, reason). A user
approves/edits/rejects; only on approval is a real Task/Issue/Decision/Risk
created — with the same evidence carried over. Nothing is lost (full audit
trail). The versioned AI history stays in ``meetings.AIAnalysis``.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from .enums import (
    ActivityVerb,
    ApprovalStatus,
    Confidence,
    DecisionStatus,
    FollowUpStatus,
    IssueStatus,
    IssueType,
    NotificationType,
    Priority,
    ProjectStatus,
    ReportType,
    RiskStatus,
    Severity,
    SuggestionType,
    TaskCategory,
    TaskStatus,
    VoiceMatchTier,
    VoicePersonEventType,
)


class OwnedModel(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss"
    )

    class Meta(BaseModel.Meta):
        abstract = True


class AISourcedModel(OwnedModel):
    """Base for entities that AI can create — carries confidence + explainability."""

    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)ss",
    )
    created_by_ai = models.BooleanField(default=False)
    source_analysis_version = models.PositiveIntegerField(null=True, blank=True)
    # Explainability — why/where AI created it.
    confidence = models.CharField(max_length=8, choices=Confidence.choices, blank=True)
    confidence_score = models.PositiveSmallIntegerField(null=True, blank=True)   # 0–100
    source_segment_index = models.PositiveIntegerField(null=True, blank=True)
    source_start_time = models.FloatField(null=True, blank=True)
    source_speaker = models.CharField(max_length=255, blank=True)
    source_quote = models.TextField(blank=True)
    source_reason = models.TextField(blank=True)
    suggestion = models.ForeignKey(
        "AISuggestion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta(OwnedModel.Meta):
        abstract = True


class Workspace(OwnedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class VoicePerson(OwnedModel):
    """A cross-meeting voice identity (Phase 15B).

    Represents ONE real human across MANY meetings, and links the per-meeting
    ``Speaker`` rows that are that person. Kept deliberately SEPARATE from Speaker
    (which is meeting-local and owns transcript segments) so a wrong guess never
    propagates an identity into transcripts. Linking is always user-confirmed —
    nothing is auto-linked. The voice signature (centroid + best-N embeddings) and
    analytics are aggregated from the linked speakers' already-persisted
    embeddings, so no transcript/embedding reprocessing is ever needed.
    """

    workspace = models.ForeignKey(
        Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name="voice_people"
    )
    display_name = models.CharField(max_length=120)
    aliases = models.JSONField(default=list, blank=True)
    avatar = models.URLField(max_length=512, blank=True)
    email = models.EmailField(blank=True)
    department = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=120, blank=True)
    confirmed = models.BooleanField(default=False)
    # Last match confidence (0-100) that linked a speaker to this identity.
    confidence = models.FloatField(null=True, blank=True)

    # Voice signature — aggregated from linked speakers (no reprocessing).
    voice_centroid_embedding = models.JSONField(null=True, blank=True)  # list[float]
    best_embeddings = models.JSONField(default=list, blank=True)  # [{vector, quality, meeting_id, speaker_id}]
    embedding_dimensions = models.PositiveIntegerField(default=0)

    # Aggregate analytics (rolled up from linked speakers → Executive later).
    meeting_count = models.PositiveIntegerField(default=0)
    speaker_count = models.PositiveIntegerField(default=0)
    total_talk_time = models.FloatField(default=0.0)
    total_word_count = models.PositiveIntegerField(default=0)
    avg_embedding_quality = models.FloatField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta(OwnedModel.Meta):
        indexes = [models.Index(fields=["owner", "-last_seen"])]

    def __str__(self) -> str:
        return self.display_name


class VoicePersonEvent(OwnedModel):
    """Immutable audit trail for a VoicePerson (create/link/unlink/merge/split…)."""

    voice_person = models.ForeignKey(
        VoicePerson, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=16, choices=VoicePersonEventType.choices)
    speaker_id = models.UUIDField(null=True, blank=True)   # the meeting Speaker involved
    meeting_id = models.UUIDField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    tier = models.CharField(max_length=16, choices=VoiceMatchTier.choices, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    detail = models.JSONField(default=dict, blank=True)

    class Meta(OwnedModel.Meta):
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["voice_person", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} · {self.voice_person_id}"


class Project(OwnedModel):
    workspace = models.ForeignKey(
        Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE)

    def __str__(self) -> str:
        return self.name


class Milestone(OwnedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    completion_percentage = models.PositiveSmallIntegerField(default=0)

    def __str__(self) -> str:
        return self.name


class Task(AISourcedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    assignee = models.CharField(max_length=255, blank=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO, db_index=True)
    category = models.CharField(max_length=16, choices=TaskCategory.choices, default=TaskCategory.GENERAL)
    tags = models.JSONField(default=list, blank=True)
    labels = models.JSONField(default=list, blank=True)
    watchers = models.JSONField(default=list, blank=True)
    checklist = models.JSONField(default=list, blank=True)   # [{id, text, done}]
    due_date = models.DateField(null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(null=True, blank=True)
    dependencies = models.JSONField(default=list, blank=True)
    completion_notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    manual_override = models.BooleanField(default=False)

    class Meta(AISourcedModel.Meta):
        indexes = [models.Index(fields=["owner", "status"]), models.Index(fields=["meeting"])]

    def __str__(self) -> str:
        return self.title[:60]


class Issue(AISourcedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    issue_type = models.CharField(max_length=16, choices=IssueType.choices, default=IssueType.PROBLEM)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=IssueStatus.choices, default=IssueStatus.OPEN, db_index=True)
    assignee = models.CharField(max_length=255, blank=True)
    related_tasks = models.JSONField(default=list, blank=True)

    def __str__(self) -> str:
        return self.title[:60]


class Decision(AISourcedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions")
    decision = models.TextField()
    reason = models.TextField(blank=True)
    participants = models.JSONField(default=list, blank=True)
    impact = models.CharField(max_length=16, choices=Severity.choices, blank=True)
    status = models.CharField(max_length=16, choices=DecisionStatus.choices, default=DecisionStatus.ACCEPTED, db_index=True)
    decided_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.decision[:60]


class Risk(AISourcedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="risks")
    risk = models.TextField()
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    probability = models.CharField(max_length=16, choices=Severity.choices, blank=True)
    mitigation = models.TextField(blank=True)
    assignee = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=RiskStatus.choices, default=RiskStatus.OPEN, db_index=True)

    def __str__(self) -> str:
        return self.risk[:60]


class FollowUp(AISourcedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="follow_ups")
    item = models.TextField()
    assignee = models.CharField(max_length=255, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=FollowUpStatus.choices, default=FollowUpStatus.PENDING, db_index=True)

    def __str__(self) -> str:
        return self.item[:60]


class Note(OwnedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    meeting = models.ForeignKey("meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.title or self.content[:40]


class Report(OwnedModel):
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    meeting = models.ForeignKey("meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    report_type = models.CharField(max_length=24, choices=ReportType.choices, db_index=True)
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    model_used = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=32, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    inference_ms = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(OwnedModel.Meta):
        indexes = [models.Index(fields=["owner", "report_type"])]

    def __str__(self) -> str:
        return f"{self.report_type} v{self.version}: {self.title[:40]}"


class Notification(OwnedModel):
    notification_type = models.CharField(max_length=24, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    meeting = models.ForeignKey("meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(OwnedModel.Meta):
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["owner", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.notification_type}: {self.title[:40]}"


class AISuggestion(OwnedModel):
    """A pending AI-extracted item awaiting human approval (the review queue).

    On approve → a real Task/Issue/Decision/Risk/FollowUp is created from
    ``generated_json`` carrying the evidence. On reject → status REJECTED. Nothing
    is deleted, so there's a full audit trail of what the AI proposed.
    """

    meeting = models.ForeignKey("meetings.Meeting", on_delete=models.CASCADE, related_name="ai_suggestions")
    suggestion_type = models.CharField(max_length=16, choices=SuggestionType.choices, db_index=True)
    status = models.CharField(max_length=12, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING, db_index=True)

    title = models.CharField(max_length=500)                 # short label of the suggestion
    generated_json = models.JSONField(default=dict)          # working copy (may be edited)
    original_json = models.JSONField(default=dict, blank=True)   # immutable original AI output
    edited_json = models.JSONField(default=dict, blank=True)     # final edited version (if edited)

    confidence = models.CharField(max_length=8, choices=Confidence.choices, default=Confidence.MEDIUM)
    confidence_score = models.PositiveSmallIntegerField(default=50)   # 0–100
    reason = models.TextField(blank=True)                    # why AI created it

    # Evidence.
    source_segment_index = models.PositiveIntegerField(null=True, blank=True)
    source_start_time = models.FloatField(null=True, blank=True)
    source_speaker = models.CharField(max_length=255, blank=True)
    quote = models.TextField(blank=True)
    source_analysis_version = models.PositiveIntegerField(null=True, blank=True)

    # Traceability.
    reviewer_notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Link to the record it became.
    converted_to_type = models.CharField(max_length=16, blank=True)
    converted_to_id = models.UUIDField(null=True, blank=True)

    class Meta(OwnedModel.Meta):
        ordering = ("-confidence_score", "-created_at")
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["meeting", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.suggestion_type}({self.status}): {self.title[:40]}"


def task_attachment_path(instance, filename):
    import uuid
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    return f"private/attachments/{instance.task_id}/{uuid.uuid4().hex}{ext}"


class TaskComment(OwnedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()

    class Meta(OwnedModel.Meta):
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.body[:40]


class TaskAttachment(OwnedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=task_attachment_path)
    filename = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:
        return self.filename


class ActivityLog(OwnedModel):
    """A workspace-wide activity feed / audit trail (Phase 9 readiness)."""

    verb = models.CharField(max_length=24, choices=ActivityVerb.choices)
    entity_type = models.CharField(max_length=24)       # task/issue/decision/risk/suggestion
    entity_id = models.UUIDField(null=True, blank=True)
    summary = models.CharField(max_length=500)
    meeting = models.ForeignKey("meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(OwnedModel.Meta):
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.verb} {self.entity_type}: {self.summary[:40]}"
