"""Phase 12B — Core Agents tests: all 12 agents run through the shared framework
with grounding + explainability + observability; tool failures and LLM failures
degrade gracefully; sandbox mode persists nothing; capability matrix + agent
health. Uses the deterministic dummy LLM (conftest forces AI_PROVIDER=mock)."""
from __future__ import annotations

import pytest

from apps.agents.agents import capability_matrix
from apps.agents.enums import AgentCapability
from apps.agents.framework.base import BaseAgent
from apps.agents.framework.executor import executor
from apps.agents.framework.registry import agent_registry
from apps.agents.framework.tools import AgentContext, tool_registry
from apps.agents.models import AgentRun
from apps.meetings.services.llm import LLMError

pytestmark = pytest.mark.django_db

ALL_AGENTS = [
    "executive_agent", "project_manager_agent", "technical_architect_agent", "qa_agent",
    "risk_analyst_agent", "business_analyst_agent", "documentation_agent", "meeting_analyst_agent",
    "knowledge_agent", "report_generator_agent", "research_agent", "customer_success_agent",
]


def test_twelve_agents_registered():
    names = {a.name for a in agent_registry.all()}
    assert set(ALL_AGENTS) <= names
    assert len(ALL_AGENTS) == 12


@pytest.mark.parametrize("agent_name", ALL_AGENTS)
def test_every_agent_runs_grounded_and_explainable(agent_name, user, seeded):
    run = executor.run(user, agent_name, "Give me a status update.")
    assert run.status == "succeeded", agent_name
    assert run.answer
    profile = agent_registry.get(agent_name)
    # Every declared tool was invoked (Tool Registry only — no direct access).
    assert run.tools_used == list(profile.tools)
    # Explainability + observability recorded.
    assert 0 <= run.confidence <= 100
    assert 0 <= run.quality_score <= 100
    assert run.result["reasoning"] is not None
    assert "recommendations" in run.result and "next_actions" in run.result
    assert run.duration_ms >= 0 and run.retry_count >= 0


def test_output_contract_fields_present(user, seeded):
    run = executor.run(user, "risk_analyst_agent", "What are our biggest risks?")
    r = run.result
    for key in ("reasoning", "confidence", "evidence", "sources", "related_meetings",
                "related_decisions", "related_tasks", "related_risks", "recommendations",
                "next_actions", "knowledge_version", "consensus_version",
                "grounding_score", "evidence_score", "completeness_score", "quality_score"):
        assert key in r, key
    # Risk agent surfaced risk evidence.
    assert any(e.get("type") == "risk" for e in r["evidence"]) or r["related_risks"] == []


def test_tool_failure_degrades_gracefully(user, seeded, monkeypatch):
    # Break one tool; the agent must still complete using the others.
    tool = tool_registry.get("risks")
    monkeypatch.setattr(tool, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    run = executor.run(user, "risk_analyst_agent", "risk report")
    assert run.status == "succeeded"
    # The failed tool call is recorded as not-ok, others succeed.
    steps = list(run.steps.all())
    assert any(s.step_type == "tool_call" and s.name == "risks" and not s.ok for s in steps)
    assert any(s.step_type == "tool_call" and s.ok for s in steps)


def test_llm_failure_uses_fallback(user, seeded):
    class FailingLLM:
        name, model_name = "failing", "failing"
        def generate(self, *a, **k):
            raise LLMError("ollama down", retryable=True)

    result, steps, tele = BaseAgent(agent_registry.get("knowledge_agent"), llm=FailingLLM()).run(
        AgentContext(owner=user, request="What auth did we choose?"))
    assert tele.fallback_used is True
    assert tele.retry_count >= 1
    assert result.answer                      # still usable (deterministic fallback)
    assert result.grounding_score <= 45       # fallback caps grounding


def test_sandbox_persists_nothing(user, seeded):
    before = AgentRun.objects.count()
    preview = executor.preview(user, "executive_agent", "sandbox health check")
    assert preview["sandbox"] is True and preview["status"] == "succeeded"
    assert preview["answer"] and "telemetry" in preview and preview["steps"]
    assert AgentRun.objects.count() == before   # nothing written


def test_capability_matrix():
    matrix = capability_matrix()
    assert len(matrix) == 12
    execu = next(r for r in matrix if r["agent"] == "executive_agent")
    assert execu["executive"] is True and execu["reports"] is True
    docs = next(r for r in matrix if r["agent"] == "documentation_agent")
    assert docs["reports"] is True


def test_agent_capabilities_gate_tools():
    # Every tool an agent declares must exist in the registry.
    for p in agent_registry.all():
        for t in p.tools:
            assert tool_registry.has(t), f"{p.name} → {t}"
    assert AgentCapability.EXECUTIVE in agent_registry.get("executive_agent").capabilities


# ---- API -------------------------------------------------------------------

def test_api_matrix_health_and_sandbox(auth_client, user, seeded):
    assert auth_client.get("/api/agents/matrix/").status_code == 200
    executor.run(user, "knowledge_agent", "warm up a run")
    health = auth_client.get("/api/agents/health/")
    assert health.status_code == 200
    ka = next(h for h in health.data["data"]["health"] if h["agent"] == "knowledge_agent")
    assert ka["runs"] >= 1 and ka["success_rate"] == 1.0

    r = auth_client.post("/api/agents/run/",
                         {"agent": "project_manager_agent", "request": "plan the sprint", "sandbox": True},
                         format="json")
    assert r.status_code == 200 and r.data["data"]["sandbox"] is True
