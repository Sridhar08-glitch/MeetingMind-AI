"""The collaboration engine. Runs a workflow of stages (produce → handoff →
review → vote → debate → consensus) over a SHARED context (one tool cache across
all agents), then merges + validates a final answer. Everything reuses the 12A
framework, 12B agents and 12C merger/consensus. Stages run sequentially so agents
can build on and critique each other's work."""
from __future__ import annotations

import logging
from time import perf_counter

from django.db import transaction
from django.utils import timezone

from apps.agents.collaboration.templates import get_template, policy_stages
from apps.agents.enums import (
    CollaborationPolicy,
    CollaborationStageType as S,
    CollaborationStatus,
)
from apps.agents.framework.executor import executor as agent_executor
from apps.agents.framework.registry import agent_registry
from apps.agents.framework.validator import validator
from apps.agents.models import CollaborationRun, CollaborationStep
from apps.agents.planner.intent import analyze_intent
from apps.agents.planner.merge import ResultMerger, resolve_conflicts
from apps.knowledge.services.index import KnowledgeIndexService

logger = logging.getLogger("meetingmind.ai")

_HUMAN_CONFIDENCE_THRESHOLD = 55.0
_APPROVE_THRESHOLD = 60.0


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


class CollaborationEngine:
    def __init__(self, llm=None):
        self.llm = llm
        self.merger = ResultMerger(llm=llm)

    # -- public ------------------------------------------------------------

    def run(self, owner, request: str, *, template: str | None = None,
            agents: list[str] | None = None, policy: str = CollaborationPolicy.SEQUENTIAL,
            approve: bool = False) -> CollaborationRun:
        total_t = perf_counter()
        human_required_wf = False
        if template:
            tmpl = get_template(template)
            if not tmpl:
                raise KeyError(f"Unknown workflow template '{template}'.")
            stages, policy, workflow, human_required_wf = tmpl.stages, tmpl.policy, template, tmpl.human_required
        else:
            if not agents:
                agents = analyze_intent(request, llm=self.llm)["agents"]
            agents = [a for a in agents if agent_registry.has(a)] or ["knowledge_agent"]
            stages, workflow = policy_stages(agents, policy), "custom"

        collab = CollaborationRun.objects.create(owner=owner, request=request, workflow=workflow,
                                                 policy=policy, status=CollaborationStatus.RUNNING)

        cache: dict = {}          # SHARED CONTEXT across every agent in the workflow
        findings: list[dict] = []
        agent_runs = []
        reviews, votes = [], []
        debate_count = 0
        step_rows: list[dict] = []

        for stage in stages:
            if stage.type in (S.PRODUCE, S.HANDOFF):
                handoff = stage.type == S.HANDOFF
                for name in stage.agents:
                    req = self._augment(request, findings) if handoff else request
                    run = self._exec(owner, name, req, cache)
                    agent_runs.append(run)
                    if run.result:
                        findings.append(run.result)
                    step_rows.append({"type": stage.type, "agent": name, "role": stage.role,
                                      "agent_run": run, "input": req[:500], "output": run.answer,
                                      "confidence": run.confidence, "quality": run.quality_score,
                                      "latency": run.duration_ms})
            elif stage.type == S.REVIEW:
                proposal = self._proposal(owner, request, findings)
                for reviewer in stage.agents:
                    run = self._exec(owner, reviewer, self._review_prompt(request, proposal), cache)
                    agent_runs.append(run)
                    approved = bool(run.found and run.confidence >= _APPROVE_THRESHOLD)
                    reviews.append(approved)
                    step_rows.append({"type": S.REVIEW, "agent": reviewer, "role": stage.role, "agent_run": run,
                                      "input": proposal[:500], "output": run.answer, "approved": approved,
                                      "review": {"approved": approved, "score": run.confidence,
                                                 "critique": run.answer[:400]},
                                      "confidence": run.confidence, "quality": run.quality_score,
                                      "latency": run.duration_ms})
            elif stage.type == S.VOTE:
                proposal = self._proposal(owner, request, findings)
                for voter in stage.agents:
                    run = self._exec(owner, voter, self._vote_prompt(request, proposal), cache)
                    agent_runs.append(run)
                    vote = "yes" if (run.found and run.confidence >= _APPROVE_THRESHOLD) else "no"
                    votes.append(vote)
                    step_rows.append({"type": S.VOTE, "agent": voter, "role": stage.role, "agent_run": run,
                                      "input": proposal[:500], "output": run.answer, "vote": vote,
                                      "confidence": run.confidence, "quality": run.quality_score,
                                      "latency": run.duration_ms})
            elif stage.type in (S.DEBATE, S.CONSENSUS):
                debate_count += 1 if stage.type == S.DEBATE else 0
                resolution = resolve_conflicts(owner, request, findings)
                positions = [{"agent": f.get("agent"), "position": f.get("answer", "")[:200]} for f in findings]
                step_rows.append({"type": stage.type, "agent": "", "role": stage.role, "input": request[:500],
                                  "output": "; ".join(r["resolution"] for r in resolution["resolutions"]) or "positions recorded",
                                  "detail": {"positions": positions, "resolution": resolution}})

        # Final merge over all produced/handed-off findings.
        merged = self.merger.merge(owner, request, findings, use_llm=True)

        agreement_rate = round(votes.count("yes") / len(votes), 2) if votes else None
        review_success = round(sum(reviews) / len(reviews), 2) if reviews else None
        total_tools = sum(len(r.tools_used) for r in agent_runs)
        tool_reuse = round(100 * (total_tools - len(cache)) / total_tools, 1) if total_tools else 0.0

        collaboration_quality = _clamp(
            0.4 * merged["merge_quality"] + 0.25 * merged["confidence"]
            + 0.2 * ((review_success or agreement_rate or 1.0) * 100)
            + 0.15 * merged["grounding_score"])

        v = validator.validate(answer=merged["answer"], confidence=merged["confidence"],
                               evidence=merged["evidence"], sources=merged["sources"], found=merged["found"])

        human_required = human_required_wf or merged["confidence"] < _HUMAN_CONFIDENCE_THRESHOLD
        status = (CollaborationStatus.PENDING_APPROVAL if (human_required and not approve)
                  else CollaborationStatus.SUCCEEDED)

        stats = KnowledgeIndexService().stats(owner)
        self._finalize(collab, merged, v, stats, {
            "status": status, "human_required": human_required, "approved": approve or not human_required,
            "agreement_rate": agreement_rate, "review_success_rate": review_success,
            "debate_count": debate_count, "tool_reuse_pct": tool_reuse,
            "collaboration_quality": collaboration_quality, "stages_count": len(stages),
            "agent_count": len(agent_runs), "total_ms": int((perf_counter() - total_t) * 1000),
            "reviews": reviews, "votes": votes,
        })
        self._persist_steps(collab, step_rows)
        return collab

    def approve(self, owner, collab: CollaborationRun) -> CollaborationRun:
        if collab.status != CollaborationStatus.PENDING_APPROVAL:
            return collab
        collab.status = CollaborationStatus.SUCCEEDED
        collab.approved = True
        collab.approved_by = owner
        collab.approved_at = timezone.now()
        collab.save(update_fields=["status", "approved", "approved_by", "approved_at", "updated_at"])
        return collab

    # -- helpers -----------------------------------------------------------

    def _exec(self, owner, agent_name, request, cache):
        return agent_executor.run(owner, agent_name, request, cache=cache)

    def _augment(self, request, findings):
        if not findings:
            return request
        prior = "\n".join(f"- {f.get('agent', 'agent')}: {f.get('answer', '')[:200]}" for f in findings[-3:])
        return f"{request}\n\nBuild on the prior agents' findings:\n{prior}"

    def _proposal(self, owner, request, findings):
        if not findings:
            return "(no proposal yet)"
        merged = self.merger.merge(owner, request, findings, use_llm=False)
        return merged["answer"]

    def _review_prompt(self, request, proposal):
        return (f"Critically review the following proposal for weaknesses, risks, gaps or missing evidence. "
                f"State whether you would approve it and why.\n\nPROPOSAL:\n{proposal}\n\nOriginal request: {request}")

    def _vote_prompt(self, request, proposal):
        return (f"Assess whether this proposal should proceed, based on the evidence. "
                f"Give your confidence.\n\nPROPOSAL:\n{proposal}\n\nOriginal request: {request}")

    @transaction.atomic
    def _finalize(self, collab, merged, v, stats, meta):
        collab.status = meta["status"]
        collab.answer = merged["answer"]
        collab.reasoning = merged["reasoning"]
        collab.confidence = merged["confidence"]
        collab.found = merged["found"]
        collab.knowledge_version = stats.get("knowledge_version", 0)
        collab.consensus_version = _consensus_count(collab.owner)
        collab.result = {**merged, "validation": {"ok": v.ok, "issues": v.issues},
                         "reviews": meta["reviews"], "votes": meta["votes"]}
        for k in ("human_required", "approved", "agreement_rate", "review_success_rate",
                  "debate_count", "tool_reuse_pct", "collaboration_quality", "stages_count",
                  "agent_count", "total_ms"):
            setattr(collab, k, meta[k])
        collab.save()

    def _persist_steps(self, collab, rows):
        for i, s in enumerate(rows):
            CollaborationStep.objects.create(
                run=collab, order=i, stage_type=s["type"], agent=s.get("agent", ""),
                role=s.get("role", ""), agent_run=s.get("agent_run"),
                input=s.get("input", ""), output=s.get("output", ""),
                review=s.get("review", {}), approved=s.get("approved"), vote=s.get("vote", ""),
                confidence=s.get("confidence", 0.0), quality=s.get("quality", 0.0),
                latency_ms=s.get("latency", 0), detail=s.get("detail", {}))


def _consensus_count(owner) -> int:
    from apps.knowledge.models import KnowledgeConsensus
    return KnowledgeConsensus.objects.filter(owner=owner).count()


engine = CollaborationEngine()
