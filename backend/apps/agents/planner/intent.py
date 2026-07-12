"""Intent analysis + task decomposition. An LLM maps the request to the agents
needed; a deterministic keyword mapper is the offline fallback."""
from __future__ import annotations

import json
import logging
import re

from apps.agents.framework.registry import agent_registry
from apps.agents.prompts import PLANNER_INTENT_SCHEMA
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider

logger = logging.getLogger("meetingmind.ai")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Keyword → agent (deterministic fallback + augmentation).
_KEYWORDS = {
    "risk_analyst_agent": ["risk", "mitigat", "compliance", "security", "threat", "exposure"],
    "report_generator_agent": ["report", "weekly", "monthly", "sprint report"],
    "executive_agent": ["executive", "brief", "health", "score", "leadership", "strateg"],
    "project_manager_agent": ["sprint", "priorit", "roadmap", "milestone", "blocked", "capacity", "plan the", "task"],
    "technical_architect_agent": ["architect", "architecture", "technical debt", "technology", "scalab", "dependency", "refactor"],
    "qa_agent": ["qa", "test", "coverage", "regression", "release readiness", "bug"],
    "business_analyst_agent": ["requirement", "user stor", "acceptance", "gap analysis"],
    "documentation_agent": ["document", "release note", "docs", "user guide", "api doc"],
    "meeting_analyst_agent": ["meeting quality", "participation", "effective", "action item"],
    "knowledge_agent": ["decide", "decision", "consensus", "conflict", "what did", "search", "knowledge", "lookup"],
    "research_agent": ["research", "compare", "comparison", "trend", "history", "evolution", "cross-project"],
    "customer_success_agent": ["customer", "support", "feature request", "churn", "complaint"],
}


def _keyword_agents(request: str) -> list[str]:
    low = request.lower()
    hits = [a for a, kws in _KEYWORDS.items() if any(k in low for k in kws)]
    return hits or ["knowledge_agent"]


def analyze_intent(request: str, *, llm=None) -> dict:
    """Return {intent, agents, mode, reasoning}. LLM-first, keyword fallback."""
    fallback_agents = _keyword_agents(request)
    llm = llm or get_llm_provider()
    prompt = prompt_registry.get("planner_intent")
    agent_catalog = "; ".join(f"{p.name} ({p.role})" for p in agent_registry.all())
    system, user = prompt.render(schema=PLANNER_INTENT_SCHEMA, agents=agent_catalog, request=request)
    try:
        resp = llm.generate(user, system=system, json=True, schema_hint="planner_intent")
        obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
        agents = [a for a in (obj.get("agents") or []) if agent_registry.has(a)]
        if not agents:
            agents = fallback_agents
        return {
            "intent": str(obj.get("intent", "")).strip() or request[:120],
            "agents": agents,
            "mode": str(obj.get("mode", "parallel")).strip().lower(),
            "reasoning": str(obj.get("reasoning", "")).strip(),
            "source": "llm",
        }
    except (LLMError, json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
        logger.warning("Intent analysis LLM failed (%s); using keyword mapping.", exc)
        return {"intent": request[:120], "agents": fallback_agents, "mode": "parallel",
                "reasoning": "Selected by keyword mapping (LLM unavailable).", "source": "fallback"}
