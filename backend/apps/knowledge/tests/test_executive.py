"""Phase 11C — Executive Intelligence tests: scoped materialization + versioning,
workspace health/score, analytics, explainable recommendations, org insights,
alert lifecycle, people graph, history/what-changed, trends, predictions,
explanations, executive brief, and natural-language filters. Owner-scoped."""
from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.knowledge.models import (
    AlertStatus,
    ExecutiveAlert,
    ExecutiveExplanation,
    ExecutiveMetricSnapshot,
    ExecutiveRecommendation,
    ExecutiveTrendPoint,
    OrganizationSnapshot,
    ProjectSnapshot,
)
from apps.knowledge.selectors import people_graph
from apps.knowledge.services import executive as exe
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.nlquery import natural_language_query
from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision, Project, Risk, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def org(user):
    proj = Project.objects.create(owner=user, name="ERP")
    m1 = Meeting.objects.create(owner=user, title="Kickoff", description="d", project=proj)
    TranscriptSegment.objects.create(meeting=m1, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Alice", text="We will build the billing module.")
    Decision.objects.create(owner=user, meeting=m1, project=proj, decision="Adopt the ERP platform",
                            participants=["Alice", "Bob"], confidence_score=88)
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Set up billing",
                        status="completed", assignee="Alice", confidence_score=80)
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Integrate payments",
                        status="blocked", assignee="Bob")
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Blocked A", status="blocked")
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Blocked B", status="blocked")
    Risk.objects.create(owner=user, meeting=m1, project=proj, risk="Payment gateway outage risk",
                        severity="critical", status="open", assignee="Carol", confidence_score=70)
    KnowledgeIndexService().index_meeting(m1)
    return proj


def test_materialize_creates_scoped_versioned_snapshots(user, org):
    snap = exe.materialize(user, actor=user)
    assert isinstance(snap, OrganizationSnapshot)
    assert snap.snapshot_version >= 1
    assert snap.knowledge_version >= 1
    # A ProjectSnapshot exists for the project.
    ps = ProjectSnapshot.objects.get(owner=user, project=org)
    assert ps.overall_health_status
    # A metric point was appended (history seed).
    assert ExecutiveMetricSnapshot.objects.filter(owner=user).exists()


def test_dashboard_reads_snapshot_with_cache_key(user, org):
    exe.materialize(user, actor=user)
    dash = exe.get_dashboard(user)
    assert dash["cache_key"].startswith("exec:")
    assert "kv" in dash["cache_key"] and "sv" in dash["cache_key"]
    assert set(dash["health"]["dimensions"]) == {
        "project", "meeting", "knowledge", "task", "decision", "risk", "ai"}
    assert dash["score"]["out_of"] == 100
    assert "analytics" in dash and "recommendations" in dash and "alerts" in dash
    assert dash["project_health"]


def test_health_dimensions_have_status_and_formula(user, org):
    health = exe.compute_health(user)
    assert health["overall"]["status"] in {"excellent", "good", "warning", "critical"}
    for dim in health["dimensions"].values():
        assert 0 <= dim["score"] <= 100
        assert dim["status"] in {"excellent", "good", "warning", "critical"}
        assert dim["formula"] and isinstance(dim["evidence"], dict)


def test_workspace_score_explains_itself(user, org):
    score = exe.compute_score(user)
    assert 0 <= score["score"] <= 100
    assert set(score["breakdown"]) == {
        "knowledge", "execution", "risks", "documentation",
        "ai_confidence", "decision_stability", "trend_stability"}
    assert all("explanation" in v for v in score["breakdown"].values())


def test_analytics_has_growth_and_leaderboards(user, org):
    exe.materialize(user)  # seed a metric point so trend series exist
    a = exe.compute_analytics(user)
    assert "meetings_monthly" in a["growth"]
    assert "top_contributors" in a["leaderboards"]
    assert "most_active_speakers" in a["leaderboards"]
    assert "ai_accuracy" in a and "ai_usage" in a


def test_recommendations_are_normalized_and_explained(user, org):
    exe.materialize(user)
    recs = exe.list_recommendations(user)
    assert recs, "blocked tasks + critical risk should yield recommendations"
    r = recs[0]
    assert r["reason"] and "confidence" in r and "impact" in r
    assert ExecutiveRecommendation.objects.filter(owner=user).exists()


def test_alerts_materialized_with_lifecycle(user, org):
    exe.materialize(user)
    alerts = exe.list_alerts(user, status=AlertStatus.OPEN)
    assert any(a["type"] == "overdue_risk" for a in alerts)      # critical open risk
    assert any(a["type"] == "repeated_blocker" for a in alerts)  # ≥3 blocked
    alert = ExecutiveAlert.objects.filter(owner=user).first()
    exe.set_alert_status(user, alert, AlertStatus.ACKNOWLEDGED)
    alert.refresh_from_db()
    assert alert.status == "acknowledged"
    exe.set_alert_status(user, alert, AlertStatus.DISMISSED)
    alert.refresh_from_db()
    assert alert.status == "dismissed"


def test_people_graph_includes_people(user, org):
    g = people_graph(user)
    types = {n["type"] for n in g["nodes"]}
    assert "person" in types
    assert g["counts"]["people"] >= 1
    # A speaker→meeting edge exists.
    assert any(e["type"] == "speaker" for e in g["edges"])
    assert any(e["type"] in {"assignee", "participant"} for e in g["edges"])


def test_explanations_are_stored_per_metric(user, org):
    exe.materialize(user)
    exp = exe.explanation_for(user, "organization", "health.risk")
    assert exp is not None
    assert exp["formula"] and exp["knowledge_version"] >= 0
    assert ExecutiveExplanation.objects.filter(owner=user, scope="organization").exists()


def test_trends_materialized(user, org):
    exe.materialize(user)
    exe.materialize(user)
    pts = exe.get_trends(user, granularity="daily", metric="overall_health")
    assert pts and all("value" in p for p in pts)
    assert ExecutiveTrendPoint.objects.filter(owner=user).exists()


def test_history_and_what_changed(user, org):
    exe.materialize(user)
    hist = exe.executive_history(user)
    assert hist["now"] is not None and "overall_health" in hist["now"]
    changed = exe.what_changed(user, timezone.now() - timezone.timedelta(days=1))
    assert changed["new_decisions"]  # a decision was created in the fixture


def test_predictions_structure(user, org):
    for _ in range(3):
        exe.materialize(user)
    pred = exe.predictive_health(user)
    assert "available" in pred


def test_scope_limited_project_materialization(user, org):
    # Materializing one project does not require an org snapshot to exist.
    ps = exe.materialize_project(user, org, actor=user)
    assert ps.snapshot_version >= 1
    assert ProjectSnapshot.objects.filter(owner=user, project=org).exists()


def test_executive_report(user, org):
    rep = exe.executive_report(user, "week")
    assert rep["executive_summary"]
    assert "critical_risks" in rep and "top_achievements" in rep
    assert "knowledge_changes" in rep


def test_nl_query_uses_retrieval(user, org):
    out = natural_language_query(user, "show billing tasks")
    assert "results" in out and "interpreted" in out
    assert out["filters"] is not None


def test_nl_query_ignores_invalid_entity_type(user, org, monkeypatch):
    """Regression (live-found): the LLM sometimes returns a topic word as
    entity_type (e.g. 'billing'), which must NOT be applied as a filter — else
    every result is wrongly excluded."""
    from apps.knowledge.services import nlquery
    monkeypatch.setattr(nlquery, "_interpret", lambda q: {
        "entity_type": "billing", "keywords": "billing", "date_from": "", "date_to": "", "category": ""})
    out = natural_language_query(user, "billing")
    assert "entity_type" not in out["filters"]           # bogus type dropped
    assert "billing" in out["search_text"].lower()       # folded into free text

    # A REAL entity type is still honoured.
    monkeypatch.setattr(nlquery, "_interpret", lambda q: {
        "entity_type": "risk", "keywords": "outage", "date_from": "", "date_to": "", "category": ""})
    out2 = natural_language_query(user, "risks")
    assert out2["filters"].get("entity_type") == "risk"


def test_parse_dt_bare_date_is_end_of_day():
    """Regression (live-found): "as of <date>" must cover the whole day, not
    resolve to midnight (which excluded same-day indexed knowledge)."""
    from apps.knowledge.api.views import _parse_dt
    dt = _parse_dt("2026-07-09")
    assert dt is not None and (dt.hour, dt.minute, dt.second) == (23, 59, 59)
    # Full datetimes are still parsed as-is.
    assert _parse_dt("2026-07-09T08:00:00").hour == 8


def test_executive_is_owner_scoped(user, org):
    exe.materialize(user)
    other = User.objects.create_user(email="ivan@example.com", password="x")
    assert exe.list_alerts(other) == []
    assert exe.list_recommendations(other) == []
    assert people_graph(other)["counts"]["people"] == 0


# ---- API smoke ----

def test_api_executive_endpoints(auth_client, user, org):
    assert auth_client.post("/api/knowledge/executive/refresh/").status_code == 200
    for path in ("/api/knowledge/executive/dashboard/",
                 "/api/knowledge/executive/health/",
                 "/api/knowledge/executive/score/",
                 "/api/knowledge/executive/analytics/",
                 "/api/knowledge/executive/insights/",
                 "/api/knowledge/executive/recommendations/",
                 "/api/knowledge/executive/alerts/",
                 "/api/knowledge/executive/history/",
                 "/api/knowledge/executive/what-changed/",
                 "/api/knowledge/executive/predictions/",
                 "/api/knowledge/executive/trends/?granularity=daily",
                 "/api/knowledge/executive/brief/?period=week",
                 "/api/knowledge/executive/explain/?metric=health.overall",
                 "/api/knowledge/people-graph/"):
        assert auth_client.get(path).status_code == 200, path

    r = auth_client.post("/api/knowledge/nl-query/", {"q": "show critical risks"}, format="json")
    assert r.status_code == 200

    alert = ExecutiveAlert.objects.filter(owner=user).first()
    assert auth_client.post(f"/api/knowledge/executive/alerts/{alert.id}/status/",
                            {"status": "acknowledged"}, format="json").status_code == 200


def test_api_executive_requires_auth(api_client):
    assert api_client.get("/api/knowledge/executive/dashboard/").status_code == 401
