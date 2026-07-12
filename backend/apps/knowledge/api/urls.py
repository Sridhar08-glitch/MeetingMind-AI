"""Knowledge Hub API routes (mounted at /api/knowledge/)."""
from __future__ import annotations

from django.urls import path

from apps.knowledge.api import views

app_name = "knowledge"

urlpatterns = [
    path("search/", views.OrgSearchView.as_view(), name="search"),
    path("chat/", views.OrgChatView.as_view(), name="chat"),
    path("stats/", views.KnowledgeStatsView.as_view(), name="stats"),
    path("reindex/", views.ReindexView.as_view(), name="reindex"),
    path("insights/", views.InsightsView.as_view(), name="insights"),
    path("recommendations/", views.RecommendationsView.as_view(), name="recommendations"),
    path("brief/", views.ExecutiveBriefView.as_view(), name="brief"),
    path("digest/", views.DailyDigestView.as_view(), name="digest"),
    path("graph/", views.GraphView.as_view(), name="graph"),
    path("comparison/", views.ComparisonView.as_view(), name="comparison"),
    path("conflicts/", views.ConflictsView.as_view(), name="conflicts"),
    path("memory/<uuid:project_id>/", views.ProjectMemoryView.as_view(), name="memory"),
    path("impact/<uuid:decision_id>/", views.DecisionImpactView.as_view(), name="impact"),
    # Phase 11A — temporal knowledge.
    path("versions/", views.KnowledgeVersionsView.as_view(), name="versions"),
    path("timetravel/", views.TimeTravelView.as_view(), name="timetravel"),
    path("timeline/", views.KnowledgeTimelineView.as_view(), name="timeline"),
    path("events/", views.KnowledgeEventsView.as_view(), name="events"),
    path("history/<str:entity_type>/<uuid:entity_id>/", views.EntityHistoryView.as_view(), name="entity-history"),
    path("decision/<uuid:decision_id>/evolution/", views.DecisionEvolutionView.as_view(), name="decision-evolution"),
    # Phase 11B — organizational reasoning.
    path("reliability/", views.ReliabilityView.as_view(), name="reliability"),
    path("consensus/", views.ConsensusView.as_view(), name="consensus"),
    path("consensus/evolution/", views.ConsensusEvolutionView.as_view(), name="consensus-evolution"),
    path("conflicts/registry/", views.ConflictRegistryView.as_view(), name="conflict-registry"),
    path("conflicts/<uuid:conflict_id>/resolve/", views.ConflictResolveView.as_view(), name="conflict-resolve"),
    path("impact-graph/<uuid:decision_id>/", views.DecisionImpactGraphView.as_view(), name="impact-graph"),
    path("memory-score/", views.MemoryScoreView.as_view(), name="memory-score"),
    path("memory-score/<uuid:project_id>/", views.ProjectMemoryScoreView.as_view(), name="project-memory-score"),
    # Phase 11C — executive intelligence.
    path("executive/dashboard/", views.ExecutiveDashboardView.as_view(), name="exec-dashboard"),
    path("executive/refresh/", views.ExecutiveRefreshView.as_view(), name="exec-refresh"),
    path("executive/health/", views.WorkspaceHealthView.as_view(), name="exec-health"),
    path("executive/score/", views.WorkspaceScoreView.as_view(), name="exec-score"),
    path("executive/analytics/", views.ExecutiveAnalyticsView.as_view(), name="exec-analytics"),
    path("executive/insights/", views.OrganizationInsightsView.as_view(), name="exec-insights"),
    path("executive/recommendations/", views.ExecutiveRecommendationsView.as_view(), name="exec-recs"),
    path("executive/recommendations/<uuid:rec_id>/status/", views.ExecutiveRecommendationStatusView.as_view(), name="exec-rec-status"),
    path("executive/alerts/", views.ExecutiveAlertsView.as_view(), name="exec-alerts"),
    path("executive/alerts/<uuid:alert_id>/status/", views.ExecutiveAlertStatusView.as_view(), name="exec-alert-status"),
    path("executive/history/", views.ExecutiveHistoryView.as_view(), name="exec-history"),
    path("executive/what-changed/", views.ExecutiveWhatChangedView.as_view(), name="exec-what-changed"),
    path("executive/predictions/", views.ExecutivePredictionsView.as_view(), name="exec-predictions"),
    path("executive/trends/", views.ExecutiveTrendsView.as_view(), name="exec-trends"),
    path("executive/explain/", views.ExecutiveExplainView.as_view(), name="exec-explain"),
    path("executive/brief/", views.ExecutiveBriefView2.as_view(), name="exec-brief"),
    path("people-graph/", views.PeopleGraphView.as_view(), name="people-graph"),
    path("nl-query/", views.NaturalLanguageQueryView.as_view(), name="nl-query"),
]
