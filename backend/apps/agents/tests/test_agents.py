"""Phase 12A — Agent Framework tests: registry, tool registry, permissions,
execution engine, validator, history persistence, explainability, owner-scoping,
and the two reference agents end-to-end. Uses the deterministic dummy LLM."""
from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.agents.framework.base import BaseAgent
from apps.agents.framework.executor import executor
from apps.agents.framework.permissions import PermissionDenied, permission_engine
from apps.agents.framework.registry import agent_registry
from apps.agents.framework.tools import AgentContext, tool_registry
from apps.agents.framework.validator import validator
from apps.agents.models import AgentRunStep

pytestmark = pytest.mark.django_db


# ---- Framework units -------------------------------------------------------

def test_registry_has_agents_and_tools():
    names = {a.name for a in agent_registry.all()}
    assert {"knowledge_agent", "executive_agent"} <= names
    tools = {t.name for t in tool_registry.all()}
    assert {"knowledge_search", "consensus", "executive_health", "recommendations"} <= tools


def test_permission_engine_blocks_undeclared_tool(user):
    profile = agent_registry.get("knowledge_agent")   # tools: knowledge_search, consensus
    ctx = AgentContext(owner=user, request="x")
    exec_tool = tool_registry.get("executive_health")
    with pytest.raises(PermissionDenied):
        permission_engine.check_tool(ctx, profile, exec_tool)
    # A declared tool is allowed.
    permission_engine.check_tool(ctx, profile, tool_registry.get("knowledge_search"))


def test_validator_flags_empty_and_ungrounded():
    assert validator.validate(answer="", confidence=50, evidence=[], sources=[], found=False).ok is False
    assert validator.validate(answer="ok", confidence=150, evidence=[{}], sources=[], found=True).ok is False
    assert validator.validate(answer="ok", confidence=80, evidence=[{"id": "1"}],
                              sources=[{"id": "1"}], found=True).ok is True


def test_base_agent_produces_explainable_result(user, seeded):
    profile = agent_registry.get("knowledge_agent")
    result, steps, tele = BaseAgent(profile).run(AgentContext(owner=user, request="What auth did we choose?"))
    assert result.answer
    assert {"knowledge_search", "consensus"} <= set(result.tools_used)
    assert result.evidence and result.sources          # grounded
    assert result.knowledge_version >= 1
    assert 0 <= result.confidence <= 100
    assert 0 <= result.quality_score <= 100
    # Steps trace: one tool call per declared tool + synthesize + validate.
    kinds = [s["type"] for s in steps]
    assert kinds.count("tool_call") == len(profile.tools) and "synthesize" in kinds and "validate" in kinds
    assert tele.tool_latency_ms >= 0 and tele.fallback_used is False


# ---- Executor + history ----------------------------------------------------

def test_executor_persists_run_and_steps(user, seeded):
    run = executor.run(user, "knowledge_agent", "What is our authentication approach?")
    assert run.status == "succeeded"
    assert run.answer and run.confidence > 0
    assert {"knowledge_search", "consensus"} <= set(run.tools_used)
    assert run.result["sources"]
    assert AgentRunStep.objects.filter(run=run).count() >= 4
    assert run.knowledge_version >= 1
    assert 0 <= run.quality_score <= 100          # quality scoring stored


def test_executive_agent_runs(user, seeded):
    run = executor.run(user, "executive_agent", "How healthy is the workspace?")
    assert run.status == "succeeded"
    assert {"executive_health", "recommendations"} <= set(run.tools_used)
    assert run.answer


def test_agents_are_owner_scoped(user, seeded):
    other = User.objects.create_user(email="zoe@example.com", password="x")
    run = executor.run(other, "knowledge_agent", "What is our authentication approach?")
    # No evidence for a different owner → grounded fallback, no leakage.
    assert run.result["evidence"] == []
    assert {"knowledge_search", "consensus"} <= set(run.tools_used)
    # And it never returned another owner's data.
    assert "OAuth2" not in run.answer


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        agent_registry.get("nonexistent_agent")


# ---- API smoke -------------------------------------------------------------

def test_api_list_and_run(auth_client, user, seeded):
    r = auth_client.get("/api/agents/")
    assert r.status_code == 200
    assert any(a["name"] == "knowledge_agent" for a in r.data["data"]["agents"])

    r = auth_client.post("/api/agents/run/",
                         {"agent": "knowledge_agent", "request": "What auth did we pick?"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["status"] == "succeeded"
    assert r.data["data"]["steps"]
    run_id = r.data["data"]["id"]

    assert auth_client.get("/api/agents/runs/").status_code == 200
    detail = auth_client.get(f"/api/agents/runs/{run_id}/")
    assert detail.status_code == 200 and detail.data["data"]["result"]


def test_api_validation_errors(auth_client, user):
    assert auth_client.post("/api/agents/run/", {"agent": "nope", "request": "x"}, format="json").status_code == 400
    assert auth_client.post("/api/agents/run/", {"agent": "knowledge_agent"}, format="json").status_code == 400


def test_api_requires_auth(api_client):
    assert api_client.get("/api/agents/").status_code == 401
