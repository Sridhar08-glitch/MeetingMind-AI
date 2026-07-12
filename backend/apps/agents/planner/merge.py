"""Result merger + conflict resolver.

Deduplicates evidence/sources/recommendations across agents, synthesizes one
coherent answer (LLM under quality policies, deterministic otherwise), and — when
agents touch contested topics — resolves via the existing Consensus + Conflict
registries (the single source of truth), never by inventing a verdict.
"""
from __future__ import annotations

import json
import logging
import re

from apps.agents.prompts import PLANNER_MERGE_SCHEMA
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider

logger = logging.getLogger("meetingmind.ai")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _dedupe_by(items, key):
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def resolve_conflicts(owner, request: str, agent_results: list[dict]) -> dict:
    """Surface contested topics touched by the request/answers and resolve them
    through the consensus registry."""
    from apps.knowledge.services.consensus import list_conflicts, list_consensus

    open_conflicts = list_conflicts(owner, status="open")
    if not open_conflicts:
        return {"conflicts": [], "resolutions": [], "score": 100.0}

    text = (request + " " + " ".join(r.get("answer", "") for r in agent_results)).lower()
    consensus = {c["topic"].lower(): c for c in list_consensus(owner)}
    touched, resolutions = [], []
    for c in open_conflicts:
        topic = c["topic"]
        if topic.lower() in text:
            touched.append(c)
            con = consensus.get(topic.lower())
            if con:
                resolutions.append({
                    "topic": topic, "category": c["category"],
                    "resolution": con["current_position"], "confidence": con["confidence"],
                    "reason": con.get("reason") or f"Current consensus favours: {con['current_position']}",
                })
    if not touched:
        return {"conflicts": [], "resolutions": [], "score": 100.0}
    score = round(100 * len(resolutions) / len(touched), 1)
    return {"conflicts": touched, "resolutions": resolutions, "score": score}


class ResultMerger:
    def __init__(self, llm=None):
        self.llm = llm or get_llm_provider()

    def merge(self, owner, request: str, agent_results: list[dict], *, use_llm: bool) -> dict:
        ok = [r for r in agent_results if r.get("found") is not False and r.get("answer")]
        pool = ok or agent_results

        evidence = _dedupe_by([e for r in pool for e in r.get("evidence", [])],
                              lambda e: (e.get("type"), e.get("id")))
        sources = _dedupe_by([s for r in pool for s in r.get("sources", [])], lambda s: s.get("id") or s.get("title"))
        recommendations = _dedupe_by([x for r in pool for x in r.get("recommendations", [])], lambda x: x.lower())
        next_actions = _dedupe_by([x for r in pool for x in r.get("next_actions", [])], lambda x: x.lower())
        related_meetings = _dedupe_by([m for r in pool for m in r.get("related_meetings", [])], lambda m: m.get("meeting_id"))
        related_decisions = _dedupe_by([d for r in pool for d in r.get("related_decisions", [])], lambda d: d.get("id"))
        related_tasks = _dedupe_by([t for r in pool for t in r.get("related_tasks", [])], lambda t: t.get("id"))
        related_risks = _dedupe_by([r2 for r in pool for r2 in r.get("related_risks", [])], lambda r2: r2.get("id"))

        contributions = [
            {"agent": r["agent"], "answer": r.get("answer", "")[:400], "confidence": r.get("confidence", 0),
             "quality": r.get("quality_score", 0), "tools_used": r.get("tools_used", [])}
            for r in pool
        ]
        conflict = resolve_conflicts(owner, request, pool)

        answer, reasoning, confidence, llm_used = self._synthesize(request, pool, contributions, use_llm)
        if conflict["resolutions"]:
            notes = "; ".join(f"{r['topic']} → {r['resolution']}" for r in conflict["resolutions"])
            reasoning = (reasoning + f" Contested topics resolved via consensus: {notes}.").strip()

        # Merge quality heuristics.
        merge_quality = round(min(100.0, 40 + 12 * len(pool) + (10 if evidence else 0)), 1)
        grounding = 100.0 if evidence else (55.0 if pool else 20.0)
        coverage = round(min(100.0, 100 * len(evidence) / 12), 1)

        return {
            "answer": answer, "reasoning": reasoning, "confidence": confidence,
            "found": bool(evidence) or any(r.get("found") for r in pool),
            "evidence": evidence[:30], "sources": sources[:12],
            "recommendations": recommendations[:12], "next_actions": next_actions[:12],
            "related_meetings": related_meetings[:10], "related_decisions": related_decisions[:10],
            "related_tasks": related_tasks[:10], "related_risks": related_risks[:10],
            "agent_contributions": contributions, "conflict_resolution": conflict,
            "merge_quality": merge_quality, "grounding_score": grounding, "evidence_coverage": coverage,
            "llm_used": llm_used,
        }

    def _synthesize(self, request, pool, contributions, use_llm):
        # Deterministic fallback / non-LLM policies: stitch the agent answers.
        def deterministic():
            parts = [f"{c['agent'].replace('_', ' ')}: {c['answer']}" for c in contributions[:5]]
            avg_conf = round(sum(c["confidence"] for c in contributions) / max(1, len(contributions)), 1)
            return "\n\n".join(parts), "Combined the findings of the selected agents.", avg_conf, False

        if not use_llm or len(pool) == 1:
            if len(pool) == 1:
                r = pool[0]
                return r.get("answer", ""), r.get("reasoning", ""), r.get("confidence", 60.0), False
            return deterministic()

        findings = "\n\n".join(f"[{c['agent']}] (confidence {c['confidence']})\n{c['answer']}" for c in contributions)
        prompt = prompt_registry.get("planner_merge")
        system, user = prompt.render(schema=PLANNER_MERGE_SCHEMA, request=request, findings=findings)
        try:
            resp = self.llm.generate(user, system=system, json=True, schema_hint="planner_merge")
            obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
            answer = str(obj.get("answer", "")).strip()
            if not answer:
                return deterministic()
            return (answer, str(obj.get("reasoning", "")).strip(),
                    float(max(0, min(100, obj.get("confidence", 70) or 70))), True)
        except (LLMError, json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
            logger.warning("Planner merge LLM failed (%s); using deterministic merge.", exc)
            return deterministic()
