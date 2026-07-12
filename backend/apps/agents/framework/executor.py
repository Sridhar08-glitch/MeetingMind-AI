"""Agent factory + executor. Runs an agent through the framework and persists the
full audit trail (AgentRun + AgentRunStep) with quality scores + observability.
Sandbox mode (``preview``) runs the same pipeline WITHOUT persisting or mutating
anything — the foundation for a future Sandbox → Approval → Execute flow."""
from __future__ import annotations

import logging
from dataclasses import asdict
from time import perf_counter

from django.db import transaction

from apps.agents.enums import RunStatus
from apps.agents.models import AgentRun, AgentRunStep

from .base import AgentResult, BaseAgent, Telemetry
from .registry import AgentProfile, agent_registry
from .tools import AgentContext

logger = logging.getLogger("meetingmind.ai")


class AgentFactory:
    @staticmethod
    def create(profile: AgentProfile, llm=None) -> BaseAgent:
        # Declarative default covers every agent; custom classes could resolve here.
        return BaseAgent(profile, llm=llm)


class AgentExecutor:
    def __init__(self, llm=None):
        self.llm = llm

    def _run_agent(self, owner, agent_name, request, params, cache=None):
        profile = agent_registry.get(agent_name)          # raises KeyError if unknown
        agent = AgentFactory.create(profile, llm=self.llm)
        context = AgentContext(owner=owner, request=request, params=params or {}, cache=cache)
        started = perf_counter()
        result, steps, tele = agent.run(context)
        duration = int((perf_counter() - started) * 1000)
        return result, steps, tele, duration

    @staticmethod
    def _apply(run: AgentRun, result: AgentResult, tele: Telemetry, duration: int) -> None:
        run.status = RunStatus.SUCCEEDED
        run.answer = result.answer
        run.reasoning = result.reasoning
        run.confidence = result.confidence
        run.found = result.found
        run.knowledge_version = result.knowledge_version
        run.consensus_version = result.consensus_version
        run.tools_used = result.tools_used
        run.provider = result.provider
        run.model = result.model
        run.prompt_version = result.prompt_version
        run.inference_ms = result.inference_ms
        run.duration_ms = duration
        run.result = asdict(result)
        run.grounding_score = result.grounding_score
        run.evidence_score = result.evidence_score
        run.completeness_score = result.completeness_score
        run.quality_score = result.quality_score
        run.tool_latency_ms = tele.tool_latency_ms
        run.validation_latency_ms = tele.validation_latency_ms
        run.retry_count = tele.retry_count
        run.fallback_used = tele.fallback_used
        run.validation_ok = tele.validation_ok
        run.validation_issues = tele.validation_issues

    def run(self, owner, agent_name: str, request: str, params: dict | None = None,
            planner_run=None, cache=None) -> AgentRun:
        agent_registry.get(agent_name)   # validate up-front
        run = AgentRun.objects.create(owner=owner, agent_name=agent_name, request=request,
                                      params=params or {}, status=RunStatus.RUNNING,
                                      planner_run=planner_run)
        try:
            result, steps, tele, duration = self._run_agent(owner, agent_name, request, params, cache=cache)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent %s failed", agent_name)
            run.status = RunStatus.FAILED
            run.error = str(exc)[:1000]
            run.save()
            return run

        with transaction.atomic():
            self._apply(run, result, tele, duration)
            run.save()
            for i, s in enumerate(steps):
                AgentRunStep.objects.create(run=run, order=i, step_type=s["type"], name=s["name"],
                                            ok=s["ok"], duration_ms=s.get("ms", 0), detail=s.get("detail", {}))
        return run

    def preview(self, owner, agent_name: str, request: str, params: dict | None = None) -> dict:
        """Sandbox run — full pipeline, nothing persisted or mutated (agents are
        read-only via tools, so this is inherently side-effect free)."""
        try:
            result, steps, tele, duration = self._run_agent(owner, agent_name, request, params)
        except Exception as exc:  # noqa: BLE001
            return {"sandbox": True, "agent": agent_name, "status": "failed", "error": str(exc)}
        return {
            "sandbox": True, "agent": agent_name, "request": request, "status": "succeeded",
            "duration_ms": duration, **asdict(result),
            "telemetry": asdict(tele),
            "steps": [{"order": i, "type": s["type"], "name": s["name"], "ok": s["ok"],
                       "duration_ms": s.get("ms", 0), "detail": s.get("detail", {})}
                      for i, s in enumerate(steps)],
        }


executor = AgentExecutor()
