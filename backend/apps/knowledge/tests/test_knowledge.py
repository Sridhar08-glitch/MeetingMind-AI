"""Phase 10 — Knowledge Hub tests (indexing, search, chat, insights, brief,
digest, graph, comparison, memory, conflicts, impact). Owner-scoped throughout."""
from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.knowledge.selectors import knowledge_graph, project_memory
from apps.knowledge.services.briefs import daily_digest, executive_brief
from apps.knowledge.services.chat import OrgChatService
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.insights import (
    ai_insights,
    cross_project_comparison,
    decision_impact,
    detect_conflicts,
    recommendations,
)
from apps.knowledge.services.search import OrgSearchService
from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision, Project, Risk, Task

pytestmark = pytest.mark.django_db


def _seed(owner, *, project=None, title="Weekly sync", segs=(), tasks=(), decisions=(), risks=()):
    m = Meeting.objects.create(owner=owner, title=title, description="Team meeting", project=project)
    for i, (spk, txt) in enumerate(segs):
        TranscriptSegment.objects.create(meeting=m, index=i, start_time=float(i * 10),
                                         end_time=float(i * 10 + 5), speaker=spk, text=txt)
    for t in tasks:
        Task.objects.create(owner=owner, meeting=m, project=project, title=t)
    for d in decisions:
        Decision.objects.create(owner=owner, meeting=m, project=project, decision=d)
    for r in risks:
        Risk.objects.create(owner=owner, meeting=m, project=project, risk=r)
    KnowledgeIndexService().index_meeting(m)
    return m


@pytest.fixture
def workspace(user):
    proj = Project.objects.create(owner=user, name="Migration")
    _seed(user, project=proj, title="Kickoff",
          segs=[("Alice", "We will migrate the platform database to Postgres."),
                ("Bob", "Budget review is scheduled next week.")],
          tasks=["Migrate database", "Review budget"],
          decisions=["Proceed with the platform migration"],
          risks=["Budget overrun before board meeting"])
    _seed(user, project=proj, title="Follow-up",
          segs=[("Alice", "The migration timeline slipped by a week."),
                ("Carol", "We should reconsider the migration approach.")],
          decisions=["Delay the platform migration by one week"],
          risks=["Migration timeline risk to the release"])
    return proj


def test_indexing_and_stats(user, workspace):
    stats = KnowledgeIndexService().stats(user)
    assert stats["meetings_indexed"] == 2
    assert stats["projects_included"] == 1
    assert stats["items_indexed"] > 0
    assert stats["last_updated"] is not None


def test_search_is_owner_scoped(user, workspace):
    results = OrgSearchService().search(user, "platform migration", k=10)
    assert results and any("migrat" in r["snippet"].lower() for r in results)
    assert all(r["confidence"] >= 0 for r in results)

    other = User.objects.create_user(email="eve@example.com", password="x")
    assert OrgSearchService().search(other, "platform migration", k=10) == []


def test_search_filters_by_project_and_entity(user, workspace):
    res = OrgSearchService().search(user, "migration", filters={"entity_type": "decision"}, k=10)
    assert res and all(r["entity_type"] == "decision" for r in res)


def test_cross_meeting_chat_grounded_with_sources(user, workspace):
    out = OrgChatService().ask(user, "What is happening with the migration?")
    assert out["found"] is True
    assert out["answer"]
    assert out["sources"], "chat must return an AI Sources panel"
    assert "knowledge_freshness" in out
    assert out["sources"][0]["meeting_id"]


def test_chat_not_found_when_no_evidence(user):
    out = OrgChatService().ask(user, "anything about quantum teleportation")
    assert out["found"] is False
    assert out["answer"] == "I couldn't find that in your meetings."
    assert out["sources"] == []


def test_ai_insights(user, workspace):
    ins = ai_insights(user)
    assert ins["meetings_analyzed"] >= 0
    assert isinstance(ins["project_health"], list)
    assert any(p["name"] == "Migration" for p in ins["project_health"])


def test_recommendations_are_evidence_based(user, workspace):
    for i in range(3):
        Task.objects.create(owner=user, title=f"Blocked work {i}", status="blocked")
    recs = recommendations(user)
    assert any("blocked" in r["detail"].lower() for r in recs)
    assert all("evidence" in r for r in recs)


def test_executive_brief_and_digest(user, workspace):
    brief = executive_brief(user, "weekly")
    assert brief["period"] == "weekly"
    assert brief["brief"]
    assert brief["data"]["new_meetings"] >= 2
    digest = daily_digest(user, "Alice")
    assert digest["digest"]


def test_knowledge_graph(user, workspace):
    g = knowledge_graph(user)
    types = {n["type"] for n in g["nodes"]}
    assert {"meeting", "project", "decision"} <= types
    assert g["edges"]


def test_project_memory(user, workspace):
    mem = project_memory(user, workspace)
    assert mem["counts"]["meetings"] == 2
    assert mem["counts"]["decisions"] >= 2


def test_cross_project_comparison(user, workspace):
    comp = cross_project_comparison(user)
    assert comp["project_count"] == 1
    assert comp["projects"][0]["name"] == "Migration"


def test_conflict_detection(user, workspace):
    conflicts = detect_conflicts(user)
    # Two decisions across two meetings both mention "migration" -> flagged for review.
    assert any(c["topic"] == "migration" and c["count"] >= 2 for c in conflicts)


def test_decision_impact(user, workspace):
    decision = Decision.objects.filter(owner=user, decision__icontains="Proceed").first()
    impact = decision_impact(user, decision)
    assert impact["impact"]["tasks"]["count"] >= 1


# ---- API smoke ----

def test_api_requires_auth(api_client):
    assert api_client.get("/api/knowledge/insights/").status_code == 401


def test_api_search_and_chat(auth_client, user):
    proj = Project.objects.create(owner=user, name="API Project")
    _seed(user, project=proj, title="API meeting",
          segs=[("Alice", "We agreed to ship the new dashboard next sprint.")],
          decisions=["Ship the new dashboard"])
    r = auth_client.get("/api/knowledge/search/?q=dashboard")
    assert r.status_code == 200
    assert r.data["data"]["count"] >= 1

    r = auth_client.post("/api/knowledge/chat/", {"question": "What did we agree to ship?"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["found"] is True
    assert r.data["data"]["sources"]


def test_api_brief_digest_graph_stats(auth_client, user):
    _seed(user, title="Solo meeting", segs=[("Alice", "Quick standup notes.")])
    for path in ("/api/knowledge/brief/", "/api/knowledge/digest/",
                 "/api/knowledge/graph/", "/api/knowledge/stats/",
                 "/api/knowledge/insights/", "/api/knowledge/recommendations/",
                 "/api/knowledge/comparison/", "/api/knowledge/conflicts/"):
        assert auth_client.get(path).status_code == 200, path


def test_api_memory_and_impact_404(auth_client, user):
    import uuid
    assert auth_client.get(f"/api/knowledge/memory/{uuid.uuid4()}/").status_code == 404
    assert auth_client.get(f"/api/knowledge/impact/{uuid.uuid4()}/").status_code == 404
