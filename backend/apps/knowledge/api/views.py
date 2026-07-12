"""Knowledge Hub API — org search, cross-meeting chat, insights, brief, digest,
graph, comparison, project memory, conflicts, decision impact, freshness.

Every endpoint is owner-scoped (authorization before any retrieval/aggregation).
"""
from __future__ import annotations

from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.knowledge.models import ConflictStatus, KnowledgeConflict, KnowledgeVersion
from apps.knowledge.selectors import knowledge_graph, project_memory
from apps.knowledge.services.briefs import daily_digest, executive_brief
from apps.knowledge.services.chat import OrgChatService
from apps.knowledge.services.consensus import (
    ConsensusService,
    consensus_evolution,
    list_conflicts,
    list_consensus,
    resolve_conflict,
)
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.insights import (
    ai_insights,
    cross_project_comparison,
    decision_impact,
    decision_impact_graph,
    detect_conflicts,
    recommendations,
)
from apps.knowledge.services import executive as exe
from apps.knowledge.services.nlquery import natural_language_query
from apps.knowledge.services.reliability import knowledge_reliability
from apps.knowledge.services.scoring import organizational_memory_scores, project_memory_score
from apps.knowledge.selectors import people_graph
from apps.knowledge.models import (
    AlertStatus,
    ExecutiveAlert,
    ExecutiveRecommendation,
    RecommendationStatus,
    TrendGranularity,
)
from apps.knowledge.services.search import OrgSearchService
from apps.knowledge.services.temporal import (
    decision_evolution,
    entity_history,
    knowledge_events,
    time_travel_stats,
    topic_timeline,
)
from apps.meetings.models import Meeting
from apps.meetings.services.media import ProcessingError
from apps.workspace.models import Decision, Project

_TRUE = {"1", "true", "yes"}


def _parse_dt(value):
    """Parse an ISO datetime; a bare date (YYYY-MM-DD) resolves to END of that
    day so "as of <date>" includes everything that happened during the day."""
    if not value:
        return None
    value = value.strip()
    # Bare date → end of day (parse_datetime would otherwise give midnight and
    # exclude same-day activity, e.g. a meeting indexed at 08:17 on that date).
    if len(value) == 10 and value.count("-") == 2:
        value = f"{value}T23:59:59"
    return parse_datetime(value)


def _filters(qp) -> dict:
    f = {}
    for key in ("project", "meeting", "entity_type", "speaker", "language", "date_from", "date_to"):
        val = qp.get(key)
        if val:
            f[key] = val
    as_of = _parse_dt(qp.get("as_of"))
    if as_of:
        f["as_of"] = as_of
    return f


class OrgSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return error_response("Query 'q' is required.", code="invalid", status=400)
        try:
            k = min(int(request.query_params.get("k", 20)), 50)
        except ValueError:
            k = 20
        results = OrgSearchService().search(request.user, q, filters=_filters(request.query_params), k=k)
        return success_response(data={"query": q, "count": len(results), "results": results})


class OrgChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return error_response("A 'question' is required.", code="invalid", status=400)
        project_id = request.data.get("project_id")
        k = min(int(request.data.get("k", 8) or 8), 20)
        filters = dict(request.data.get("filters") or {})
        as_of = _parse_dt(request.data.get("as_of"))
        if as_of:
            filters["as_of"] = as_of   # Time-Travel: ask over historical knowledge
        try:
            answer = OrgChatService().ask(request.user, question, project_id=project_id,
                                          filters=filters, k=k)
        except ProcessingError as exc:
            return error_response(exc.message, code=exc.code, status=502)
        return success_response(data=answer)


class KnowledgeStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=KnowledgeIndexService().stats(request.user))


class ReindexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        svc = KnowledgeIndexService()
        count = 0
        for meeting in Meeting.objects.filter(owner=request.user):
            try:
                svc.index_meeting(meeting)
                count += 1
            except Exception:  # noqa: BLE001
                continue
        return success_response(message=f"Re-indexed {count} meeting(s).",
                                data={"meetings_indexed": count, **KnowledgeIndexService().stats(request.user)})


class InsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=ai_insights(request.user))


class RecommendationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"recommendations": recommendations(request.user)})


class ExecutiveBriefView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        period = request.query_params.get("period", "weekly")
        return success_response(data=executive_brief(request.user, period))


class DailyDigestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        name = (getattr(request.user, "full_name", "") or request.user.email).strip()
        return success_response(data=daily_digest(request.user, name))


class GraphView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=knowledge_graph(
            request.user,
            project=request.query_params.get("project"),
            meeting=request.query_params.get("meeting"),
        ))


class ComparisonView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=cross_project_comparison(request.user))


class ProjectMemoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, project_id):
        project = Project.objects.filter(owner=request.user, id=project_id).first()
        if not project:
            return error_response("Project not found.", code="not_found", status=404)
        return success_response(data=project_memory(request.user, project))


class ConflictsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"conflicts": detect_conflicts(request.user)})


class DecisionImpactView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, decision_id):
        decision = Decision.objects.filter(owner=request.user, id=decision_id).first()
        if not decision:
            return error_response("Decision not found.", code="not_found", status=404)
        return success_response(data=decision_impact(request.user, decision))


# ---------------------------------------------------------------------------
# Phase 11A — Temporal knowledge (versioning, time-travel, timeline, evolution)
# ---------------------------------------------------------------------------


class KnowledgeVersionsView(APIView):
    """Feature #1 — the version history behind every AI answer."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except ValueError:
            limit = 50
        rows = (KnowledgeVersion.objects.filter(owner=request.user)
                .select_related("embedding_version").order_by("-version")[:limit])
        data = [
            {"version": r.version, "indexed_at": r.indexed_at, "trigger": r.trigger,
             "reason": r.reason,
             "embedding_version": r.embedding_version.label if r.embedding_version else None,
             "meetings": r.meetings, "projects": r.projects, "tasks": r.tasks,
             "decisions": r.decisions, "risks": r.risks, "items": r.items}
            for r in rows
        ]
        return success_response(data={"count": len(data), "versions": data})


class TimeTravelView(APIView):
    """Feature #2 — 'What did we know as of <date>?'"""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        when = _parse_dt(request.query_params.get("as_of"))
        if not when:
            return error_response("An 'as_of' date/datetime is required.", code="invalid", status=400)
        return success_response(data=time_travel_stats(request.user, when))


class KnowledgeTimelineView(APIView):
    """Feature #5 — watch a topic evolve over time."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        topic = (request.query_params.get("topic") or "").strip()
        if not topic:
            return error_response("A 'topic' is required.", code="invalid", status=400)
        return success_response(data=topic_timeline(
            request.user, topic, entity_type=request.query_params.get("entity_type")))


class EntityHistoryView(APIView):
    """Full version chain + audit events for one knowledge entity."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, entity_type, entity_id):
        return success_response(data=entity_history(request.user, entity_type, entity_id))


class DecisionEvolutionView(APIView):
    """Feature #6 — a decision's version chain (v1 → current)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, decision_id):
        decision = Decision.objects.filter(owner=request.user, id=decision_id).first()
        if not decision:
            return error_response("Decision not found.", code="not_found", status=404)
        return success_response(data=decision_evolution(request.user, decision))


class KnowledgeEventsView(APIView):
    """The immutable knowledge-evolution audit feed."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        try:
            limit = min(int(request.query_params.get("limit", 100)), 500)
        except ValueError:
            limit = 100
        return success_response(data={"events": knowledge_events(
            request.user,
            entity_type=request.query_params.get("entity_type"),
            event_type=request.query_params.get("event_type"),
            limit=limit,
        )})


# ---------------------------------------------------------------------------
# Phase 11B — Organizational Reasoning
# ---------------------------------------------------------------------------


class ReliabilityView(APIView):
    """Feature #1 — explainable Knowledge Reliability Score for a topic."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        topic = (request.query_params.get("topic") or "").strip()
        if not topic:
            return error_response("A 'topic' is required.", code="invalid", status=400)
        return success_response(data=knowledge_reliability(request.user, topic))


class ConsensusView(APIView):
    """GET the cached organizational consensus; POST to (re)compute it."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"consensus": list_consensus(request.user)})

    def post(self, request: Request):
        try:
            computed = ConsensusService().compute(request.user, persist=True)
        except ProcessingError as exc:
            return error_response(exc.message, code=exc.code, status=502)
        return success_response(message=f"Computed consensus for {len(computed)} topic(s).",
                                data={"consensus": computed})


class ConsensusEvolutionView(APIView):
    """Feature #2 — how the consensus on a topic changed over time."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        topic = (request.query_params.get("topic") or "").strip()
        if not topic:
            return error_response("A 'topic' is required.", code="invalid", status=400)
        return success_response(data=consensus_evolution(request.user, topic))


class ConflictRegistryView(APIView):
    """The categorized conflict registry (feature #3)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"conflicts": list_conflicts(
            request.user,
            status=request.query_params.get("status"),
            category=request.query_params.get("category"),
        )})


class ConflictResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, conflict_id):
        conflict = KnowledgeConflict.objects.filter(owner=request.user, id=conflict_id).first()
        if not conflict:
            return error_response("Conflict not found.", code="not_found", status=404)
        status = request.data.get("status", ConflictStatus.RESOLVED)
        if status not in ConflictStatus.values:
            return error_response("Invalid status.", code="invalid", status=400)
        decision = None
        if request.data.get("decision_id"):
            decision = Decision.objects.filter(owner=request.user, id=request.data["decision_id"]).first()
        resolve_conflict(request.user, conflict, resolved_by=request.user, decision=decision,
                         status=status, reason=(request.data.get("reason") or ""))
        return success_response(message="Conflict updated.")


class DecisionImpactGraphView(APIView):
    """Feature #4 — a decision's full impact graph."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, decision_id):
        decision = Decision.objects.filter(owner=request.user, id=decision_id).first()
        if not decision:
            return error_response("Decision not found.", code="not_found", status=404)
        return success_response(data=decision_impact_graph(request.user, decision))


class MemoryScoreView(APIView):
    """Feature #5 — Organizational Memory Score (all projects)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=organizational_memory_scores(request.user))


class ProjectMemoryScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, project_id):
        project = Project.objects.filter(owner=request.user, id=project_id).first()
        if not project:
            return error_response("Project not found.", code="not_found", status=404)
        return success_response(data=project_memory_score(request.user, project))


# ---------------------------------------------------------------------------
# Phase 11C — Executive Intelligence (reads materialized snapshots)
# ---------------------------------------------------------------------------


class ExecutiveDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        refresh = request.query_params.get("refresh") in _TRUE
        return success_response(data=exe.get_dashboard(request.user, refresh=refresh))


class ExecutiveRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        snap = exe.materialize(request.user, actor=request.user)
        return success_response(message="Executive view materialized.",
                                data={"snapshot_version": snap.snapshot_version,
                                      "knowledge_version": snap.knowledge_version,
                                      "processing_ms": snap.processing_ms})


class WorkspaceHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.read_snapshot(request.user).health)


class WorkspaceScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.read_snapshot(request.user).score)


class ExecutiveAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.read_snapshot(request.user).analytics)


class OrganizationInsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.read_snapshot(request.user).organization_insights)


class ExecutiveRecommendationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"recommendations": exe.list_recommendations(request.user)})


class ExecutiveRecommendationStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, rec_id):
        rec = ExecutiveRecommendation.objects.filter(owner=request.user, id=rec_id).first()
        if not rec:
            return error_response("Recommendation not found.", code="not_found", status=404)
        status = request.data.get("status")
        if status not in RecommendationStatus.values:
            return error_response("Invalid status.", code="invalid", status=400)
        exe.set_recommendation_status(request.user, rec, status)
        return success_response(message="Recommendation updated.")


class ExecutiveAlertsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"alerts": exe.list_alerts(
            request.user, status=request.query_params.get("status"))})


class ExecutiveAlertStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, alert_id):
        alert = ExecutiveAlert.objects.filter(owner=request.user, id=alert_id).first()
        if not alert:
            return error_response("Alert not found.", code="not_found", status=404)
        status = request.data.get("status")
        if status not in AlertStatus.values:
            return error_response("Invalid status.", code="invalid", status=400)
        exe.set_alert_status(request.user, alert, status)
        return success_response(message="Alert updated.")


class ExecutiveHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.executive_history(request.user))


class ExecutiveWhatChangedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        since = _parse_dt(request.query_params.get("since"))
        if not since:
            from django.utils import timezone
            since = timezone.now() - timezone.timedelta(days=7)
        return success_response(data=exe.what_changed(request.user, since))


class ExecutivePredictionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"predictions": exe.list_predictions(request.user),
                                      "detail": exe.predictive_health(request.user)})


class ExecutiveTrendsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        gran = request.query_params.get("granularity", TrendGranularity.DAILY)
        if gran not in TrendGranularity.values:
            gran = TrendGranularity.DAILY
        return success_response(data={"granularity": gran, "points": exe.get_trends(
            request.user, granularity=gran, metric=request.query_params.get("metric"))})


class ExecutiveExplainView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        metric = request.query_params.get("metric")
        if not metric:
            return error_response("A 'metric' is required.", code="invalid", status=400)
        data = exe.explanation_for(request.user, request.query_params.get("scope", "organization"), metric)
        if data is None:
            return error_response("Explanation not found.", code="not_found", status=404)
        return success_response(data=data)


class ExecutiveBriefView2(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=exe.executive_report(
            request.user, request.query_params.get("period", "week")))


class PeopleGraphView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=people_graph(
            request.user, project=request.query_params.get("project")))


class NaturalLanguageQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        q = (request.data.get("q") or request.data.get("query") or "").strip()
        if not q:
            return error_response("A 'q' query is required.", code="invalid", status=400)
        return success_response(data=natural_language_query(request.user, q))
