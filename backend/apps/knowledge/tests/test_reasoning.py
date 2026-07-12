"""Phase 11B — organizational reasoning tests: reliability score, AI consensus,
consensus evolution, conflict registry + categorization + resolution, decision
impact graph, and organizational memory score. Owner-scoped throughout.

Uses the deterministic dummy LLM (conftest forces AI_PROVIDER=mock)."""
from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.knowledge.models import (
    ConflictStatus,
    KnowledgeConflict,
    KnowledgeConsensus,
)
from apps.knowledge.services.consensus import (
    ConsensusService,
    consensus_evolution,
    list_conflicts,
    list_consensus,
    resolve_conflict,
)
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.insights import decision_impact_graph
from apps.knowledge.services.reliability import knowledge_reliability
from apps.knowledge.services.scoring import organizational_memory_scores, project_memory_score
from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision, Project, Risk, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def reasoning(user):
    """Two meetings with opposing decisions on the shared topic 'database'."""
    proj = Project.objects.create(owner=user, name="Platform")
    m1 = Meeting.objects.create(owner=user, title="Kickoff", description="d", project=proj)
    TranscriptSegment.objects.create(meeting=m1, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Alice", text="We will use PostgreSQL for the database.")
    Decision.objects.create(owner=user, meeting=m1, project=proj, decision="Use PostgreSQL for the database",
                            confidence_score=90)
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Provision the database", confidence_score=80)
    Risk.objects.create(owner=user, meeting=m1, project=proj, risk="Database migration downtime", confidence_score=70)
    KnowledgeIndexService().index_meeting(m1)

    m2 = Meeting.objects.create(owner=user, title="Review", description="d", project=proj)
    TranscriptSegment.objects.create(meeting=m2, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Bob", text="We should move to MySQL for the database instead.")
    Decision.objects.create(owner=user, meeting=m2, project=proj, decision="Move to MySQL for the database",
                            confidence_score=60)
    KnowledgeIndexService().index_meeting(m2)
    return proj


def test_reliability_score_is_explainable(user, reasoning):
    rel = knowledge_reliability(user, "database")
    assert rel["found"] is True
    assert 0 <= rel["overall"] <= 100
    assert set(rel["components"]) == {
        "evidence_strength", "agreement", "recency", "coverage", "source_quality"}
    assert all(0 <= v <= 100 for v in rel["components"].values())
    assert rel["evidence"]["decisions"] >= 2

    # Unknown topic → not found, zero.
    assert knowledge_reliability(user, "nonexistent-topic-xyz")["found"] is False


def test_consensus_is_computed_and_cached(user, reasoning):
    computed = ConsensusService().compute(user, persist=True)
    topics = {c["topic"] for c in computed}
    assert "database" in topics
    c = KnowledgeConsensus.objects.get(owner=user, topic="database")
    assert c.current_position
    assert c.support_count <= 2 and c.opposition_count <= 2   # clamped to #decisions
    assert c.category  # classified
    # One revision recorded (Consensus Evolution seed).
    assert c.revisions.count() == 1
    assert c.trend == "new"

    listed = list_consensus(user)
    assert any(x["topic"] == "database" for x in listed)


def test_consensus_recompute_is_stable(user, reasoning):
    svc = ConsensusService()
    svc.compute(user, persist=True)
    svc.compute(user, persist=True)   # same dummy position → no new revision
    c = KnowledgeConsensus.objects.get(owner=user, topic="database")
    assert c.revisions.count() == 1
    assert c.stability_score == 100.0


def test_consensus_evolution(user, reasoning):
    ConsensusService().compute(user, persist=True)
    evo = consensus_evolution(user, "database")
    assert evo["found"] is True
    assert evo["timeline"] and "position" in evo["timeline"][0]
    assert evo["current"]["topic"] == "database"


def test_conflict_registry_and_categorization(user, reasoning):
    ConsensusService().compute(user, persist=True)
    conflicts = list_conflicts(user)
    assert conflicts, "opposing decisions should register a conflict"
    conf = conflicts[0]
    assert conf["category"]                # categorized
    assert conf["status"] == "open"
    assert conf["decision_count"] >= 2
    assert conf["positions"]


def test_conflict_resolution(user, reasoning):
    ConsensusService().compute(user, persist=True)
    conflict = KnowledgeConflict.objects.filter(owner=user).first()
    decision = Decision.objects.filter(owner=user, decision__icontains="MySQL").first()
    resolve_conflict(user, conflict, resolved_by=user, decision=decision,
                     status=ConflictStatus.RESOLVED, reason="Perf testing favoured MySQL.")
    conflict.refresh_from_db()
    assert conflict.status == "resolved"
    assert conflict.resolved_decision_id == decision.id
    assert conflict.resolved_by_id == user.id


def test_decision_impact_graph(user, reasoning):
    decision = Decision.objects.filter(owner=user, decision__icontains="PostgreSQL").first()
    graph = decision_impact_graph(user, decision)
    assert graph["counts"]["tasks"] >= 1
    assert graph["counts"]["risks"] >= 1
    nodes = {n["id"] for n in graph["graph"]["nodes"]}
    assert str(decision.id) in nodes
    assert graph["graph"]["edges"]


def test_organizational_memory_score(user, reasoning):
    ConsensusService().compute(user, persist=True)
    score = project_memory_score(user, reasoning)
    assert 0 <= score["overall"] <= 100
    assert set(score["components"]) == {
        "knowledge_quality", "decision_stability", "documentation",
        "ai_confidence", "trend_stability"}
    assert score["signals"]["decisions"] >= 2

    org = organizational_memory_scores(user)
    assert org["project_count"] == 1
    assert 0 <= org["workspace_overall"] <= 100


def test_reasoning_is_owner_scoped(user, reasoning):
    ConsensusService().compute(user, persist=True)
    other = User.objects.create_user(email="mallory@example.com", password="x")
    assert list_consensus(other) == []
    assert list_conflicts(other) == []
    assert knowledge_reliability(other, "database")["found"] is False


# ---- API smoke ----

def test_api_reasoning_endpoints(auth_client, user, reasoning):
    # Compute consensus (POST), then read everything back.
    assert auth_client.post("/api/knowledge/consensus/").status_code == 200
    assert auth_client.get("/api/knowledge/consensus/").status_code == 200
    assert auth_client.get("/api/knowledge/consensus/evolution/?topic=database").status_code == 200
    assert auth_client.get("/api/knowledge/reliability/?topic=database").status_code == 200
    assert auth_client.get("/api/knowledge/conflicts/registry/").status_code == 200
    assert auth_client.get("/api/knowledge/memory-score/").status_code == 200
    assert auth_client.get(f"/api/knowledge/memory-score/{reasoning.id}/").status_code == 200

    decision = Decision.objects.filter(owner=user).first()
    assert auth_client.get(f"/api/knowledge/impact-graph/{decision.id}/").status_code == 200

    conflict = KnowledgeConflict.objects.filter(owner=user).first()
    r = auth_client.post(f"/api/knowledge/conflicts/{conflict.id}/resolve/",
                         {"status": "resolved", "reason": "settled"}, format="json")
    assert r.status_code == 200

    # Validation errors.
    assert auth_client.get("/api/knowledge/reliability/").status_code == 400
    assert auth_client.get("/api/knowledge/consensus/evolution/").status_code == 400
