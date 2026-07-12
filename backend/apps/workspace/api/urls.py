"""Workspace URL routes mounted under /api/workspace/."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.workspace.api.views import (
    ActivityLogViewSet,
    AISuggestionViewSet,
    AnalyticsView,
    DashboardView,
    DecisionViewSet,
    FollowUpViewSet,
    IssueViewSet,
    MilestoneViewSet,
    NoteViewSet,
    NotificationViewSet,
    ProjectViewSet,
    ReportViewSet,
    RiskViewSet,
    SearchView,
    TaskViewSet,
    TimelineView,
    VoicePersonViewSet,
    WorkspaceViewSet,
)

app_name = "workspace"

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("voice-people", VoicePersonViewSet, basename="voiceperson")
router.register("suggestions", AISuggestionViewSet, basename="suggestion")
router.register("projects", ProjectViewSet, basename="project")
router.register("milestones", MilestoneViewSet, basename="milestone")
router.register("tasks", TaskViewSet, basename="task")
router.register("issues", IssueViewSet, basename="issue")
router.register("decisions", DecisionViewSet, basename="decision")
router.register("risks", RiskViewSet, basename="risk")
router.register("follow-ups", FollowUpViewSet, basename="followup")
router.register("notes", NoteViewSet, basename="note")
router.register("reports", ReportViewSet, basename="report")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("activity", ActivityLogViewSet, basename="activity")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("search/", SearchView.as_view(), name="search"),
    path("timeline/<uuid:meeting_id>/", TimelineView.as_view(), name="timeline"),
    path("", include(router.urls)),
]
