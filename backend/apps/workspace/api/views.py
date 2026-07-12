"""Workspace API: tasks, issues, risks, decisions, projects, reports, etc."""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.meetings.models import Meeting
from apps.workspace.api.serializers import (
    ActivityLogSerializer,
    AISuggestionSerializer,
    ApproveSuggestionSerializer,
    BulkActionSerializer,
    DecisionSerializer,
    FollowUpSerializer,
    GenerateReportSerializer,
    IssueSerializer,
    MilestoneSerializer,
    NoteSerializer,
    NotificationSerializer,
    ProjectSerializer,
     RejectSuggestionSerializer,
    ReportSerializer,
    RiskSerializer,
    TaskCommentSerializer,
    TaskMoveSerializer,
    TaskSerializer,
    VoicePersonEventSerializer,
    VoicePersonSerializer,
    WorkspaceSerializer,
)
from apps.workspace.enums import ApprovalStatus, OPEN_SUGGESTION_STATUSES, TASK_BOARD_COLUMNS
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
    Workspace,
)
from apps.workspace.services.activity import find_duplicate_tasks, log_activity
from apps.workspace.services.materialize import approve_suggestion, reject_suggestion
from apps.workspace.selectors import (
    dashboard,
    meeting_timeline,
    semantic_search,
    unified_search,
    workspace_analytics,
)
from apps.workspace.services.reports import generate_report


class OwnerScopedViewSet(viewsets.ModelViewSet):
    """Base viewset: everything is scoped to (and created for) the current user."""

    permission_classes = [IsAuthenticated]
    model = None
    filterset_fields: list[str] = []
    ordering = ("-created_at",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return self.model.objects.none()
        return self.model.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class WorkspaceViewSet(OwnerScopedViewSet):
    model = Workspace
    serializer_class = WorkspaceSerializer


class VoicePersonViewSet(OwnerScopedViewSet):
    """Cross-meeting voice identities (Phase 15B). Matching is suggestion-only —
    linking always goes through an explicit, user-driven action; nothing is
    auto-linked. All operations are owner-scoped."""

    model = VoicePerson
    serializer_class = VoicePersonSerializer
    filterset_fields = ["workspace", "confirmed"]
    ordering = ("-last_seen",)

    def perform_update(self, serializer):
        from apps.workspace.services import voice_identity

        voice_identity.update_identity(
            serializer.instance, serializer.validated_data, actor=self.request.user
        )

    def _speaker(self, request):
        from apps.meetings.models import Speaker

        return Speaker.objects.filter(
            id=request.data.get("speaker") or request.query_params.get("speaker"),
            meeting__owner=request.user,
        ).select_related("meeting").first()

    @action(detail=False, methods=["get"])
    def candidates(self, request: Request):
        """Ranked identity candidates for a meeting speaker (suggestion-only)."""
        from apps.workspace.services import voice_identity

        speaker = self._speaker(request)
        if not speaker:
            return error_response("Speaker not found.", code="not_found", status=404)
        cands = voice_identity.find_candidates(speaker)
        return success_response(data={
            "speaker_id": str(speaker.id),
            "candidates": [
                {"voice_person": VoicePersonSerializer(c["voice_person"]).data,
                 "score": c["score"], "tier": c["tier"]}
                for c in cands
            ],
        })

    @action(detail=False, methods=["get"])
    def suggest(self, request: Request):
        """Per-speaker candidates for every unlinked speaker in a meeting."""
        from apps.workspace.services import voice_identity

        meeting = Meeting.objects.filter(
            id=request.query_params.get("meeting"), owner=request.user
        ).first()
        if not meeting:
            return error_response("Meeting not found.", code="not_found", status=404)
        rows = voice_identity.suggest_for_meeting(meeting)
        return success_response(data={"suggestions": [
            {"speaker_id": str(r["speaker"].id), "speaker_label": r["speaker"].label,
             "candidates": [
                 {"voice_person": VoicePersonSerializer(c["voice_person"]).data,
                  "score": c["score"], "tier": c["tier"]}
                 for c in r["candidates"]
             ]}
            for r in rows
        ]})

    @action(detail=False, methods=["post"], url_path="from-speaker")
    def from_speaker(self, request: Request):
        """Create a NEW identity seeded from a speaker + link it."""
        from apps.workspace.services import voice_identity

        speaker = self._speaker(request)
        if not speaker:
            return error_response("Speaker not found.", code="not_found", status=404)
        person = voice_identity.create_from_speaker(
            speaker, display_name=request.data.get("display_name", ""), actor=request.user
        )
        return success_response(data=VoicePersonSerializer(person).data,
                                message="Voice identity created.", status=201)

    @action(detail=True, methods=["post"])
    def link(self, request: Request, pk=None):
        """Link a meeting speaker to THIS identity (user-confirmed)."""
        from apps.workspace.services import voice_identity

        speaker = self._speaker(request)
        if not speaker:
            return error_response("Speaker not found.", code="not_found", status=404)
        person = voice_identity.link_speaker(
            self.get_object(), speaker, actor=request.user,
            confidence=request.data.get("confidence"), tier=request.data.get("tier", ""),
        )
        return success_response(data=VoicePersonSerializer(person).data, message="Speaker linked.")

    @action(detail=False, methods=["post"])
    def unlink(self, request: Request):
        """Detach a speaker from its identity."""
        from apps.workspace.services import voice_identity

        speaker = self._speaker(request)
        if not speaker:
            return error_response("Speaker not found.", code="not_found", status=404)
        voice_identity.unlink_speaker(speaker, actor=request.user)
        return success_response(message="Speaker unlinked.")

    @action(detail=True, methods=["post"])
    def confirm(self, request: Request, pk=None):
        from apps.workspace.services import voice_identity

        person = voice_identity.confirm(self.get_object(), actor=request.user)
        return success_response(data=VoicePersonSerializer(person).data, message="Identity confirmed.")

    @action(detail=True, methods=["post"])
    def merge(self, request: Request, pk=None):
        from apps.workspace.services import voice_identity

        source = self.get_queryset().filter(id=request.data.get("source")).first()
        if not source:
            return error_response("Source identity not found.", code="not_found", status=404)
        person = voice_identity.merge(self.get_object(), source, actor=request.user)
        return success_response(data=VoicePersonSerializer(person).data, message="Identities merged.")

    @action(detail=True, methods=["post"])
    def split(self, request: Request, pk=None):
        from apps.workspace.services import voice_identity

        try:
            new_person = voice_identity.split(
                self.get_object(), request.data.get("speaker_ids", []),
                new_name=request.data.get("name", ""), actor=request.user,
            )
        except ValueError as exc:
            return error_response(str(exc), code="invalid", status=400)
        return success_response(data=VoicePersonSerializer(new_person).data,
                                message="Identity split.", status=201)

    @action(detail=True, methods=["get"])
    def events(self, request: Request, pk=None):
        person = self.get_object()
        return success_response(data=VoicePersonEventSerializer(
            person.events.all(), many=True).data)


class ProjectViewSet(OwnerScopedViewSet):
    model = Project
    serializer_class = ProjectSerializer
    filterset_fields = ["status", "workspace"]


class AISuggestionViewSet(OwnerScopedViewSet):
    """The AI review queue — pending suggestions with confidence + evidence."""

    model = AISuggestion
    serializer_class = AISuggestionSerializer
    filterset_fields = ["status", "suggestion_type", "meeting"]
    http_method_names = ["get", "post", "head", "options"]  # no direct create/update

    def create(self, request, *args, **kwargs):  # suggestions come from AI, not manually
        return error_response("Suggestions are created by AI.", code="not_allowed", status=405)

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk=None):
        suggestion = self.get_object()
        serializer = ApproveSuggestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        created = approve_suggestion(
            suggestion, actor=request.user, edited=d.get("edited") or None,
            reviewer_notes=d.get("reviewer_notes", ""), on_duplicate=d.get("on_duplicate", "create"),
        )
        return success_response(
            data={"suggestion": AISuggestionSerializer(suggestion).data,
                  "created_id": str(created.id) if created else None},
            message="Suggestion approved.",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk=None):
        suggestion = self.get_object()
        serializer = RejectSuggestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reject_suggestion(suggestion, actor=request.user,
                          reviewer_notes=serializer.validated_data.get("reviewer_notes", ""))
        return success_response(data=AISuggestionSerializer(suggestion).data, message="Suggestion rejected.")

    @action(detail=True, methods=["get"])
    def duplicates(self, request: Request, pk=None):
        suggestion = self.get_object()
        return success_response(data=find_duplicate_tasks(request.user, suggestion.title))

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request: Request):
        serializer = BulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids, act = serializer.validated_data["ids"], serializer.validated_data["action"]
        qs = self.get_queryset().filter(id__in=ids)
        n = 0
        for s in qs:
            if act == "approve":
                approve_suggestion(s, actor=request.user)
            elif act == "reject":
                reject_suggestion(s, actor=request.user)
            elif act == "archive":
                s.status = ApprovalStatus.ARCHIVED
                s.save(update_fields=["status", "updated_at"])
            n += 1
        return success_response(message=f"{act.title()}d {n} suggestion(s).", data={"count": n})

    @action(detail=False, methods=["get"])
    def stats(self, request: Request):
        """AI approval dashboard — pending count, avg confidence, approval/rejection rate."""
        qs = self.get_queryset()
        from django.db.models import Avg, Count

        by_status = {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))}
        approved = by_status.get(ApprovalStatus.CONVERTED, 0) + by_status.get(ApprovalStatus.APPROVED, 0)
        rejected = by_status.get(ApprovalStatus.REJECTED, 0)
        reviewed = approved + rejected
        pending = sum(by_status.get(s, 0) for s in OPEN_SUGGESTION_STATUSES)
        return success_response(data={
            "pending": pending,
            "needs_review": by_status.get(ApprovalStatus.NEEDS_REVIEW, 0),
            "approved": approved,
            "rejected": rejected,
            "total": sum(by_status.values()),
            "average_confidence": round(qs.aggregate(a=Avg("confidence_score"))["a"] or 0, 1),
            "approval_rate": round(approved / reviewed * 100, 1) if reviewed else 0.0,
            "rejection_rate": round(rejected / reviewed * 100, 1) if reviewed else 0.0,
            "status_breakdown": by_status,
        })


class MilestoneViewSet(OwnerScopedViewSet):
    model = Milestone
    serializer_class = MilestoneSerializer
    filterset_fields = ["project"]


class TaskViewSet(OwnerScopedViewSet):
    model = Task
    serializer_class = TaskSerializer
    filterset_fields = ["status", "priority", "category", "project", "meeting", "created_by_ai"]

    @action(detail=False, methods=["get"])
    def board(self, request: Request):
        """Kanban board: tasks grouped by status column."""
        tasks = self.filter_queryset(self.get_queryset())
        by_status = {col: [] for col in TASK_BOARD_COLUMNS}
        for t in tasks.order_by("order", "-created_at"):
            by_status.setdefault(t.status, []).append(TaskSerializer(t).data)
        return success_response(data=[{"status": col, "tasks": by_status.get(col, [])} for col in TASK_BOARD_COLUMNS])

    def perform_create(self, serializer):
        task = serializer.save(owner=self.request.user)
        log_activity(self.request.user, "created", task, summary=f"Created task: {task.title[:60]}")

    @action(detail=True, methods=["patch", "post"])
    def move(self, request: Request, pk=None):
        """Drag-and-drop: update a task's kanban status (and order)."""
        task = self.get_object()
        serializer = TaskMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old = task.status
        task.status = serializer.validated_data["status"]
        task.order = serializer.validated_data.get("order", task.order)
        task.set_acting_user(request.user)
        task.save(update_fields=["status", "order", "updated_at", "updated_by"])
        log_activity(request.user, "status_changed", task,
                     summary=f"Task '{task.title[:40]}': {old} → {task.status}")
        return success_response(data=TaskSerializer(task).data, message="Task moved.")

    @action(detail=True, methods=["get"])
    def related(self, request: Request, pk=None):
        """Relationships: the meeting, transcript segment, and related items."""
        task = self.get_object()
        meeting = task.meeting
        data = {"source_meeting": None, "source_segment": None,
                "decisions": [], "risks": [], "issues": [], "reports": []}
        if meeting:
            data["source_meeting"] = {"id": str(meeting.id), "title": meeting.title}
            if task.source_segment_index is not None:
                seg = meeting.segments.filter(index=task.source_segment_index).first()
                if seg:
                    data["source_segment"] = {"index": seg.index, "start_time": seg.start_time, "text": seg.text}
            data["decisions"] = list(Decision.objects.filter(meeting=meeting).values("id", "decision")[:10])
            data["risks"] = list(Risk.objects.filter(meeting=meeting).values("id", "risk", "severity")[:10])
            data["issues"] = list(Issue.objects.filter(meeting=meeting).values("id", "title")[:10])
            data["reports"] = list(Report.objects.filter(meeting=meeting).values("id", "title", "report_type")[:10])
        return success_response(data=data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request: Request, pk=None):
        task = self.get_object()
        if request.method == "POST":
            body = (request.data.get("body") or "").strip()
            if not body:
                return error_response("Comment body is required.", code="invalid", status=400)
            comment = TaskComment.objects.create(owner=request.user, task=task, body=body)
            log_activity(request.user, "commented", task, summary=f"Commented on '{task.title[:40]}'")
            return success_response(data=TaskCommentSerializer(comment).data, status=201)
        return success_response(data=TaskCommentSerializer(task.comments.all(), many=True).data)

    @action(detail=True, methods=["get"])
    def activity(self, request: Request, pk=None):
        task = self.get_object()
        logs = ActivityLog.objects.filter(owner=request.user, entity_id=task.id)
        return success_response(data=ActivityLogSerializer(logs, many=True).data)


class IssueViewSet(OwnerScopedViewSet):
    model = Issue
    serializer_class = IssueSerializer
    filterset_fields = ["status", "issue_type", "severity", "project", "meeting"]


class DecisionViewSet(OwnerScopedViewSet):
    model = Decision
    serializer_class = DecisionSerializer
    filterset_fields = ["status", "project", "meeting"]
    search_fields = ["decision", "reason"]


class RiskViewSet(OwnerScopedViewSet):
    model = Risk
    serializer_class = RiskSerializer
    filterset_fields = ["status", "severity", "project", "meeting"]


class FollowUpViewSet(OwnerScopedViewSet):
    model = FollowUp
    serializer_class = FollowUpSerializer
    filterset_fields = ["status", "project", "meeting"]


class NoteViewSet(OwnerScopedViewSet):
    model = Note
    serializer_class = NoteSerializer
    filterset_fields = ["project", "meeting"]


class ReportViewSet(OwnerScopedViewSet):
    model = Report
    serializer_class = ReportSerializer
    filterset_fields = ["report_type", "project", "meeting", "is_current"]

    @action(detail=False, methods=["post"])
    def generate(self, request: Request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        meeting = project = None
        if data.get("meeting"):
            meeting = Meeting.objects.filter(id=data["meeting"], owner=request.user).first()
            if meeting is None:
                return error_response("Meeting not found.", code="not_found", status=404)
        if data.get("project"):
            project = Project.objects.filter(id=data["project"], owner=request.user).first()
        report = generate_report(owner=request.user, report_type=data["report_type"],
                                 meeting=meeting, project=project)
        return success_response(data=ReportSerializer(report).data, message="Report generated.", status=201)


class NotificationViewSet(OwnerScopedViewSet):
    model = Notification
    serializer_class = NotificationSerializer
    filterset_fields = ["is_read", "notification_type"]

    def get_queryset(self):
        return super().get_queryset()

    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.save(update_fields=["is_read", "updated_at"])
        return success_response(data=NotificationSerializer(n).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return success_response(message=f"Marked {count} as read.", data={"updated": count})


# --- standalone endpoints ---------------------------------------------------
class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only workspace activity feed (audit trail)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ActivityLogSerializer
    filterset_fields = ["entity_type", "verb"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ActivityLog.objects.none()
        return ActivityLog.objects.filter(owner=self.request.user)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=dashboard(request.user))


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=workspace_analytics(request.user))


class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        q = request.query_params.get("q", "")
        semantic = request.query_params.get("semantic") in {"1", "true", "yes"}
        if semantic:
            return success_response(data={"results": semantic_search(request.user, q)})
        return success_response(data=unified_search(request.user, q))


class TimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, meeting_id=None):
        meeting = Meeting.objects.filter(id=meeting_id, owner=request.user).first()
        if meeting is None:
            return error_response("Meeting not found.", code="not_found", status=404)
        return success_response(data=meeting_timeline(meeting))
