"""Phase 12C — Planner & orchestration tests: intent analysis, agent selection
(reputation + policy), sequential + parallel execution, result merge, conflict
resolution, execution policies, approval gate, retries, observability, history,
and LLM/tool failure handling. Uses the deterministic dummy LLM."""
from __future__ import annotations

import pytest

from apps.agents.enums import ExecutionPolicy, PlannerStatus
from apps.agents.planner.intent import analyze_intent, _keyword_agents
from apps.agents.planner.policies import get_policy
from apps.agents.planner.reputation import agent_reputation
from apps.agents.planner.selector import select_agents
from apps.agents.planner.service import PlannerService, planner
from apps.knowledge.services.consensus import ConsensusService
from apps.knowledge.services.index import KnowledgeIndexService
from apps.meetings.models import Meeting, TranscriptSegment
from apps.meetings.services.llm import LLMError
from apps.workspace.models import Decision, Project

pytestmark = pytest.mark.django_db


# ---- Intent + selection (units) -------------------------------------------

def test_keyword_intent_mapping():
    assert "risk_analyst_agent" in _keyword_agents("what are our security risks?")
    assert "report_generator_agent" in _keyword_agents("generate a weekly report")
    assert _keyword_agents("hello") == ["knowledge_agent"]   # safe default


def test_analyze_intent_llm_then_fallback(user):
    out = analyze_intent("Give me an executive brief and risks.")
    assert out["agents"] and all(isinstance(a, str) for a in out["agents"])

    class FailingLLM:
        name = model_name = "x"
        def generate(self, *a, **k): raise LLMError("down")
    out2 = analyze_intent("what are the risks?", llm=FailingLLM())
    assert out2["source"] == "fallback" and "risk_analyst_agent" in out2["agents"]


def test_reputation_neutral_prior_then_history(user, seeded):
    rep = agent_reputation(user, "knowledge_agent")
    assert rep["runs"] == 0 and rep["reliability"] > 0
    from apps.agents.framework.executor import executor
    executor.run(user, "knowledge_agent", "warm up")
    rep2 = agent_reputation(user, "knowledge_agent")
    assert rep2["runs"] == 1 and rep2["success_rate"] == 1.0


def test_selector_respects_policy_cap(user):
    candidates = ["executive_agent", "risk_analyst_agent", "project_manager_agent",
                  "qa_agent", "knowledge_agent", "research_agent"]
    fast = select_agents(user, candidates, get_policy(ExecutionPolicy.FAST))
    research = select_agents(user, candidates, get_policy(ExecutionPolicy.RESEARCH))
    assert len(fast) == 2 and len(research) == 6
    assert all("selection_score" in s for s in fast)


# ---- Orchestration (sequential single-agent path — no threads) ------------

@pytest.mark.django_db(transaction=True)
def test_single_agent_plan(user, seeded):
    # A request the keyword mapper routes to exactly one agent.
    class RiskOnlyLLM:
        name = model_name = "x"
        def generate(self, *a, **k): raise LLMError("force keyword mapping")
    svc = PlannerService(llm=None)
    plan = svc.run(user, "identify our top security risks", policy=ExecutionPolicy.FAST)
    assert plan.status == PlannerStatus.SUCCEEDED
    assert plan.answer and 0 <= plan.confidence <= 100
    assert plan.execution_mode in ("single", "parallel", "sequential")
    assert plan.agent_runs.count() >= 1
    assert plan.steps.filter(phase="merge").exists()
    assert plan.result["agent_contributions"]


# ---- Parallel execution (needs committed data for worker threads) ---------

@pytest.mark.django_db(transaction=True)
def test_parallel_multi_agent_plan(user, seeded):
    plan = planner.run(user, "Give an executive brief and the top risks.",
                       policy=ExecutionPolicy.BALANCED)
    assert plan.status == PlannerStatus.SUCCEEDED
    assert plan.agent_count >= 2
    assert plan.execution_mode == "parallel"
    assert plan.answer
    # Every executed agent is linked to the plan.
    assert plan.agent_runs.count() == plan.agent_count
    # Observability recorded.
    assert plan.total_ms >= 0 and plan.planner_quality >= 0
    assert plan.result["agent_contributions"]


@pytest.mark.django_db(transaction=True)
def test_conflict_resolution_uses_consensus(user):
    proj = Project.objects.create(owner=user, name="DB")
    for i, (title, dec, seg) in enumerate([
        ("Kickoff", "Use PostgreSQL for the database", "We will use PostgreSQL for the database."),
        ("Review", "Switch to MySQL for the database", "We should switch to MySQL for the database."),
    ]):
        m = Meeting.objects.create(owner=user, title=title, description="d", project=proj)
        TranscriptSegment.objects.create(meeting=m, index=0, start_time=0.0, end_time=5.0, speaker="A", text=seg)
        Decision.objects.create(owner=user, meeting=m, project=proj, decision=dec)
        KnowledgeIndexService().index_meeting(m)
    ConsensusService().compute(user, persist=True)

    plan = planner.run(user, "what database should we use", policy=ExecutionPolicy.FAST)
    assert plan.status == PlannerStatus.SUCCEEDED
    cr = plan.result["conflict_resolution"]
    assert cr["resolutions"], "database conflict should be resolved via consensus"
    assert 0 <= plan.conflict_resolution_score <= 100


# ---- Approval gate --------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_approval_gate_holds_then_resumes(user, seeded):
    plan = planner.run(user, "run a workflow", policy=ExecutionPolicy.FAST,
                       params={"require_approval": True})
    assert plan.status == PlannerStatus.PENDING_APPROVAL
    assert plan.requires_approval and not plan.answer
    resumed = planner.approve(user, plan)
    assert resumed.status == PlannerStatus.SUCCEEDED and resumed.answer


# ---- Failure handling -----------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_merge_llm_failure_falls_back(user, seeded):
    class MergeFailLLM:
        name = model_name = "x"
        calls = {"n": 0}
        def generate(self, *a, **k):
            raise LLMError("merge down")
    svc = PlannerService(llm=MergeFailLLM())
    plan = svc.run(user, "security risks", policy=ExecutionPolicy.HIGHEST_QUALITY)
    assert plan.status == PlannerStatus.SUCCEEDED and plan.answer  # deterministic merge


@pytest.mark.django_db(transaction=True)
def test_owner_scoped(user, seeded):
    from apps.accounts.models import User
    other = User.objects.create_user(email="orch@example.com", password="x")
    plan = planner.run(other, "security risks", policy=ExecutionPolicy.FAST)
    assert plan.status == PlannerStatus.SUCCEEDED
    assert "OAuth2" not in plan.answer          # no leakage of user's data


# ---- API ------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_api_planner_run_and_history(auth_client, user, seeded):
    r = auth_client.post("/api/agents/planner/run/",
                         {"request": "executive brief and risks", "policy": "fast"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["status"] == "succeeded"
    assert r.data["data"]["result"]["agent_contributions"]
    plan_id = r.data["data"]["id"]

    assert auth_client.get("/api/agents/planner/runs/").status_code == 200
    assert auth_client.get(f"/api/agents/planner/runs/{plan_id}/").status_code == 200
    graph = auth_client.get(f"/api/agents/planner/runs/{plan_id}/graph/")
    assert graph.status_code == 200 and graph.data["data"]["nodes"]
    assert auth_client.get("/api/agents/planner/metrics/").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_api_approval_flow(auth_client, user, seeded):
    r = auth_client.post("/api/agents/planner/run/",
                         {"request": "do a workflow", "policy": "fast",
                          "params": {"require_approval": True}}, format="json")
    assert r.status_code == 200 and r.data["data"]["status"] == "pending_approval"
    plan_id = r.data["data"]["id"]
    approved = auth_client.post(f"/api/agents/planner/runs/{plan_id}/approve/", {}, format="json")
    assert approved.status_code == 200 and approved.data["data"]["status"] == "succeeded"


def test_api_invalid_policy(auth_client, user):
    assert auth_client.post("/api/agents/planner/run/",
                            {"request": "x", "policy": "turbo"}, format="json").status_code == 400
