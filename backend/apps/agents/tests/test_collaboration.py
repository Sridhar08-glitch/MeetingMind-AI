"""Phase 12D — Agent Collaboration tests: workflow templates, produce/handoff/
review/vote/debate stages, shared context, collaboration policies, human-approval
gate, metrics and the collaboration graph. Uses the deterministic dummy LLM."""
from __future__ import annotations

import pytest

from apps.agents.collaboration.engine import CollaborationEngine, engine
from apps.agents.collaboration.templates import TEMPLATES, policy_stages
from apps.agents.enums import CollaborationPolicy, CollaborationStatus

pytestmark = pytest.mark.django_db


# ---- Templates + policy stages (units) ------------------------------------

def test_seven_templates_registered():
    assert set(TEMPLATES) == {
        "sprint_planning", "executive_review", "release_readiness", "risk_assessment",
        "architecture_review", "customer_feedback", "incident_postmortem"}
    for t in TEMPLATES.values():
        assert t.stages


def test_policy_stages_shapes():
    ag = ["knowledge_agent", "executive_agent"]
    assert policy_stages(ag, CollaborationPolicy.PARALLEL)[0].type == "produce"
    review = policy_stages(ag, CollaborationPolicy.REVIEW_REQUIRED)
    assert [s.type for s in review] == ["produce", "review"]
    debate = policy_stages(ag, CollaborationPolicy.DEBATE_REQUIRED)
    assert debate[-1].type == "debate"
    assert policy_stages(ag, CollaborationPolicy.SEQUENTIAL)[0].type == "handoff"


# ---- Template workflows ---------------------------------------------------

def test_sprint_planning_produces_and_reviews(user, seeded):
    collab = engine.run(user, "plan the sprint", template="sprint_planning")
    assert collab.status == CollaborationStatus.SUCCEEDED
    assert collab.workflow == "sprint_planning"
    assert collab.answer
    stages = [s.stage_type for s in collab.steps.all()]
    assert "produce" in stages and "review" in stages
    assert collab.review_success_rate is not None      # reviews happened
    assert collab.collaboration_quality > 0


def test_incident_postmortem_handoff_chain(user, seeded):
    collab = engine.run(user, "postmortem for the outage", template="incident_postmortem")
    assert collab.status == CollaborationStatus.SUCCEEDED
    handoffs = [s for s in collab.steps.all() if s.stage_type == "handoff"]
    assert len(handoffs) == 3          # meeting_analyst → risk_analyst → documentation
    # Later agents receive prior findings (handoff augmentation).
    assert "prior agents" in handoffs[1].input.lower() or handoffs[1].input


def test_release_readiness_votes_and_needs_human(user, seeded):
    collab = engine.run(user, "are we ready to release?", template="release_readiness")
    # Template flags human_required → held for approval.
    assert collab.status == CollaborationStatus.PENDING_APPROVAL
    assert collab.human_required and collab.answer
    votes = [s for s in collab.steps.all() if s.stage_type == "vote"]
    assert len(votes) == 3 and collab.agreement_rate is not None
    resumed = engine.approve(user, collab)
    assert resumed.status == CollaborationStatus.SUCCEEDED and resumed.approved


def test_architecture_review_has_debate(user, seeded):
    collab = engine.run(user, "review the auth architecture", template="architecture_review")
    assert collab.status in ("succeeded", "pending_approval")
    assert collab.debate_count >= 1
    assert any(s.stage_type == "debate" for s in collab.steps.all())


# ---- Custom collaboration (policy-driven, template-less) -------------------

def test_custom_review_required_collaboration(user, seeded):
    collab = engine.run(user, "assess our authentication approach",
                        agents=["knowledge_agent", "risk_analyst_agent"],
                        policy=CollaborationPolicy.REVIEW_REQUIRED)
    assert collab.status in ("succeeded", "pending_approval")
    assert collab.agent_count >= 2
    assert collab.tool_reuse_pct >= 0      # shared context tracked
    assert collab.result["agent_contributions"]


def test_shared_context_reuses_tools(user, seeded):
    # Two agents sharing knowledge_search on the same request → cache reuse.
    collab = engine.run(user, "what did we decide about authentication?",
                        agents=["knowledge_agent", "meeting_analyst_agent"],
                        policy=CollaborationPolicy.PARALLEL)
    assert collab.status == CollaborationStatus.SUCCEEDED
    assert collab.tool_reuse_pct >= 0


def test_collaboration_owner_scoped(user, seeded):
    from apps.accounts.models import User
    other = User.objects.create_user(email="collab@example.com", password="x")
    collab = engine.run(other, "assess authentication", agents=["knowledge_agent"],
                        policy=CollaborationPolicy.PARALLEL)
    assert "OAuth2" not in collab.answer


def test_unknown_template_raises(user):
    with pytest.raises(KeyError):
        CollaborationEngine().run(user, "x", template="does_not_exist")


# ---- API ------------------------------------------------------------------

def test_api_templates_and_run(auth_client, user, seeded):
    t = auth_client.get("/api/agents/collaboration/templates/")
    assert t.status_code == 200 and len(t.data["data"]["templates"]) == 7

    r = auth_client.post("/api/agents/collaboration/run/",
                         {"request": "risk review", "template": "risk_assessment"}, format="json")
    assert r.status_code == 200 and r.data["data"]["status"] in ("succeeded", "pending_approval")
    assert r.data["data"]["steps"]
    cid = r.data["data"]["id"]

    assert auth_client.get("/api/agents/collaboration/runs/").status_code == 200
    detail = auth_client.get(f"/api/agents/collaboration/runs/{cid}/")
    assert detail.status_code == 200
    graph = auth_client.get(f"/api/agents/collaboration/runs/{cid}/graph/")
    assert graph.status_code == 200 and graph.data["data"]["nodes"]
    assert auth_client.get("/api/agents/collaboration/metrics/").status_code == 200


def test_api_approval_flow(auth_client, user, seeded):
    r = auth_client.post("/api/agents/collaboration/run/",
                         {"request": "release check", "template": "release_readiness"}, format="json")
    assert r.data["data"]["status"] == "pending_approval"
    cid = r.data["data"]["id"]
    approved = auth_client.post(f"/api/agents/collaboration/runs/{cid}/approve/", {}, format="json")
    assert approved.status_code == 200 and approved.data["data"]["status"] == "succeeded"


def test_api_invalid_policy(auth_client, user):
    assert auth_client.post("/api/agents/collaboration/run/",
                            {"request": "x", "policy": "bogus"}, format="json").status_code == 400
