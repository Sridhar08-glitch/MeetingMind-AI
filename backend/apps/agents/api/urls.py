"""Agents API routes (mounted at /api/agents/)."""
from __future__ import annotations

from django.urls import path

from apps.agents.api import views

app_name = "agents"

urlpatterns = [
    path("", views.AgentListView.as_view(), name="list"),
    path("matrix/", views.AgentMatrixView.as_view(), name="matrix"),
    path("health/", views.AgentHealthView.as_view(), name="health"),
    path("run/", views.AgentRunView.as_view(), name="run"),
    path("runs/", views.AgentRunsView.as_view(), name="runs"),
    path("runs/<uuid:run_id>/", views.AgentRunDetailView.as_view(), name="run-detail"),
    # Multi-agent planner (12C).
    path("planner/run/", views.PlannerRunView.as_view(), name="planner-run"),
    path("planner/runs/", views.PlannerRunsView.as_view(), name="planner-runs"),
    path("planner/runs/<uuid:plan_id>/", views.PlannerRunDetailView.as_view(), name="planner-run-detail"),
    path("planner/runs/<uuid:plan_id>/approve/", views.PlannerApproveView.as_view(), name="planner-approve"),
    path("planner/runs/<uuid:plan_id>/graph/", views.PlannerGraphView.as_view(), name="planner-graph"),
    path("planner/metrics/", views.PlannerMetricsView.as_view(), name="planner-metrics"),
    # Agent collaboration (12D).
    path("collaboration/templates/", views.CollaborationTemplatesView.as_view(), name="collab-templates"),
    path("collaboration/run/", views.CollaborationRunView.as_view(), name="collab-run"),
    path("collaboration/runs/", views.CollaborationRunsView.as_view(), name="collab-runs"),
    path("collaboration/runs/<uuid:collab_id>/", views.CollaborationRunDetailView.as_view(), name="collab-run-detail"),
    path("collaboration/runs/<uuid:collab_id>/approve/", views.CollaborationApproveView.as_view(), name="collab-approve"),
    path("collaboration/runs/<uuid:collab_id>/graph/", views.CollaborationGraphView.as_view(), name="collab-graph"),
    path("collaboration/metrics/", views.CollaborationMetricsView.as_view(), name="collab-metrics"),
]
