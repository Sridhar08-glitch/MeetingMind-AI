"""The generic agent execution engine.

Every agent runs through :class:`BaseAgent`. It is capability-driven: the agent's
profile declares which tools to gather evidence from; the local LLM then
synthesizes a grounded, explainable answer. This keeps agents 100% declarative —
no per-agent business logic — and every answer carries reasoning, evidence,
confidence, knowledge/consensus versions and sources.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from time import perf_counter

from apps.agents.prompts import AGENT_SCHEMA, AGENT_SYNTHESIS_VERSION
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider

from .permissions import permission_engine
from .registry import AgentProfile
from .tools import AgentContext, ToolResult, tool_registry
from .validator import validator

logger = logging.getLogger("meetingmind.ai")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class AgentResult:
    agent: str
    answer: str
    reasoning: str = ""
    confidence: float = 0.0
    found: bool = True
    key_points: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    related_meetings: list[dict] = field(default_factory=list)
    related_decisions: list[dict] = field(default_factory=list)
    related_tasks: list[dict] = field(default_factory=list)
    related_risks: list[dict] = field(default_factory=list)
    knowledge_version: int = 0
    consensus_version: int = 0
    tools_used: list[str] = field(default_factory=list)
    # Quality scores (0–100).
    grounding_score: float = 0.0
    evidence_score: float = 0.0
    completeness_score: float = 0.0
    quality_score: float = 0.0
    provider: str = ""
    model: str = ""
    prompt_version: str = AGENT_SYNTHESIS_VERSION
    inference_ms: int = 0


@dataclass
class Telemetry:
    tool_latency_ms: int = 0
    llm_latency_ms: int = 0
    validation_latency_ms: int = 0
    retry_count: int = 0
    fallback_used: bool = False
    validation_ok: bool = True
    validation_issues: list = field(default_factory=list)


class BaseAgent:
    def __init__(self, profile: AgentProfile, llm=None):
        self.profile = profile
        self.llm = llm or get_llm_provider()

    # -- public ------------------------------------------------------------

    def run(self, context: AgentContext) -> tuple[AgentResult, list[dict], Telemetry]:
        steps: list[dict] = []
        evidence, meta, summaries, tools_used = [], {}, [], []
        tool_latency = 0

        # Optional shared cache (set by the planner) — identical tool calls
        # across agents in one plan run only once.
        cache = context.cache

        for tname in self.profile.tools:
            tool = tool_registry.get(tname)
            permission_engine.check_tool(context, self.profile, tool)
            cache_key = (tname, context.request)
            cached = cache.get(cache_key) if cache is not None else None
            t0 = perf_counter()
            if cached is not None:
                tr, ok = cached, True
            else:
                try:
                    tr = tool.run(context)
                    ok = True
                except Exception as exc:  # noqa: BLE001 — a bad tool must not kill the run
                    logger.warning("Tool %s failed: %s", tname, exc)
                    tr = ToolResult(data=None, summary=f"(tool {tname} unavailable)")
                    ok = False
                if cache is not None and ok:
                    cache[cache_key] = tr
            dt = int((perf_counter() - t0) * 1000)
            tool_latency += dt
            evidence.extend(tr.evidence)
            meta.update(tr.meta)
            if tr.summary:
                summaries.append(f"[{tname}] {tr.summary}")
            tools_used.append(tname)
            steps.append({"type": "tool_call", "name": tname, "ok": ok, "ms": dt,
                          "detail": {"evidence": len(tr.evidence)}})

        # Synthesize a grounded answer from the gathered evidence.
        context_text = "\n\n".join(summaries) or "(no evidence found)"
        prompt = prompt_registry.get(self.profile.prompt)
        system, user = prompt.render(
            role=self.profile.role, request=context.request or "(no request)",
            evidence=context_text, schema=AGENT_SCHEMA,
        )
        t0 = perf_counter()
        syn = self._synthesize(system, user, evidence)
        synth_ms = int((perf_counter() - t0) * 1000)
        steps.append({"type": "synthesize", "name": self.profile.prompt, "ok": bool(syn["answer"]),
                      "ms": synth_ms, "detail": {"retries": syn["retry_count"], "fallback": syn["fallback_used"]}})

        sources = _sources(evidence)
        tv = perf_counter()
        v = validator.validate(answer=syn["answer"], confidence=syn["confidence"], evidence=evidence,
                               sources=sources, found=syn["found"])
        validation_ms = int((perf_counter() - tv) * 1000)
        found = syn["found"] and "empty_answer" not in v.issues
        steps.append({"type": "validate", "name": "validator", "ok": v.ok, "ms": validation_ms,
                      "detail": {"issues": v.issues}})

        grounding, evidence_score, completeness = _quality(syn, evidence, sources, found)
        quality = round((grounding + evidence_score + syn["confidence"] + completeness) / 4, 1)

        result = AgentResult(
            agent=self.profile.name, answer=syn["answer"], reasoning=syn["reasoning"],
            confidence=syn["confidence"], found=found, key_points=syn["key_points"],
            recommendations=syn["recommendations"], next_actions=syn["next_actions"],
            evidence=evidence[:20], sources=sources,
            related_meetings=_dedupe_meetings(evidence),
            related_decisions=[e for e in evidence if e.get("type") == "decision"][:8],
            related_tasks=[e for e in evidence if e.get("type") == "task"][:8],
            related_risks=[e for e in evidence if e.get("type") == "risk"][:8],
            knowledge_version=int(meta.get("knowledge_version", 0)),
            consensus_version=int(meta.get("consensus_version", 0)),
            tools_used=tools_used,
            grounding_score=grounding, evidence_score=evidence_score,
            completeness_score=completeness, quality_score=quality,
            provider=self.llm.name, model=self.llm.model_name, inference_ms=synth_ms,
        )
        telemetry = Telemetry(
            tool_latency_ms=tool_latency, llm_latency_ms=synth_ms, validation_latency_ms=validation_ms,
            retry_count=syn["retry_count"], fallback_used=syn["fallback_used"],
            validation_ok=v.ok, validation_issues=v.issues,
        )
        return result, steps, telemetry

    # -- LLM synthesis (retry-once, deterministic fallback) ----------------

    def _synthesize(self, system, user, evidence) -> dict:
        retry_count = 0
        for attempt in (1, 2):
            sys_p = system if attempt == 1 else system + " Reply with ONE valid JSON object only."
            try:
                resp = self.llm.generate(user, system=sys_p, json=True, schema_hint="agent_synthesis")
                obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
                answer = str(obj.get("answer", "")).strip()
                if not answer:
                    retry_count += 1
                    continue
                return {
                    "answer": answer,
                    "reasoning": str(obj.get("reasoning", "")).strip(),
                    "confidence": float(max(0, min(100, obj.get("confidence", 60) or 60))),
                    "key_points": [str(x) for x in (obj.get("key_points") or [])][:8],
                    "recommendations": [str(x) for x in (obj.get("recommendations") or [])][:8],
                    "next_actions": [str(x) for x in (obj.get("next_actions") or [])][:8],
                    "found": bool(obj.get("found", bool(evidence))),
                    "retry_count": retry_count, "fallback_used": False,
                }
            except (LLMError, json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
                logger.warning("Agent synthesis attempt %d failed: %s", attempt, exc)
                retry_count += 1
        # Deterministic fallback keeps the agent usable if the LLM is down.
        base = {"key_points": [], "recommendations": [], "next_actions": [],
                "retry_count": retry_count, "fallback_used": True}
        if evidence:
            top = evidence[0]
            return {**base, "answer": f"Based on the available evidence: {top.get('title') or top.get('snippet', '')}",
                    "reasoning": "LLM unavailable; summarised from the top evidence.",
                    "confidence": 40.0, "found": True}
        return {**base, "answer": "I couldn't find enough information to answer that.",
                "reasoning": "No evidence found.", "confidence": 20.0, "found": False}


def _sources(evidence: list[dict]) -> list[dict]:
    out = []
    for e in evidence[:8]:
        out.append({"type": e.get("type"), "id": e.get("id"), "title": e.get("title"),
                    "meeting_id": e.get("meeting_id"), "snippet": e.get("snippet", "")[:200]})
    return out


def _dedupe_meetings(evidence: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in evidence:
        mid = e.get("meeting_id")
        if mid and mid not in seen:
            seen.add(mid)
            out.append({"meeting_id": mid, "title": e.get("source") or e.get("title")})
    return out[:8]


def _quality(syn: dict, evidence: list[dict], sources: list[dict], found: bool) -> tuple[float, float, float]:
    """Grounding, Evidence and Completeness sub-scores (0–100)."""
    import math

    grounding = 100.0 if (found and evidence) else (50.0 if evidence else 15.0)
    if syn["fallback_used"]:
        grounding = min(grounding, 45.0)
    evidence_score = round(min(100.0, 100 * math.log2(1 + len(evidence)) / math.log2(9)), 1)
    parts = [bool(syn["answer"]), bool(syn["reasoning"]), bool(syn["key_points"]),
             bool(sources), bool(syn["recommendations"] or syn["next_actions"])]
    completeness = round(100 * sum(parts) / len(parts), 1)
    return round(grounding, 1), evidence_score, completeness
