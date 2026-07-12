"""Agents API — list agents/tools, capability matrix, run (or sandbox-preview) an
agent, per-agent health, and run history. Owner-scoped throughout."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Avg
from django.utils.decorators import method_decorator
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.agents.agents import capability_matrix
from apps.agents.collaboration.engine import engine as collab_engine
from apps.agents.collaboration.templates import TEMPLATES, get_template
from apps.agents.enums import (
    CollaborationPolicy,
    CollaborationStatus,
    ExecutionPolicy,
    PlannerStatus,
    RunStatus,
)
from apps.agents.framework.executor import executor
from apps.agents.framework.registry import agent_registry
from apps.agents.framework.tools import tool_registry
from apps.agents.models import AgentRun, AgentRunStep, CollaborationRun, PlannerRun
from apps.agents.planner.service import planner
from apps.common.responses import error_response, success_response

_TRUE = {"1", "true", "yes", True}


def _profile_dict(p) -> dict:
    return {"name": p.name, "title": p.title, "role": p.role, "description": p.description,
            "capabilities": list(p.capabilities), "tools": list(p.tools)}


class AgentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={
            "agents": [_profile_dict(p) for p in agent_registry.all()],
            "tools": [{"name": t.name, "description": t.description, "capability": t.capability}
                      for t in tool_registry.all()],
        })


class AgentMatrixView(APIView):
    """The Agent Capability Matrix — which agent covers which functional area."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"matrix": capability_matrix()})


class AgentRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        agent = (request.data.get("agent") or "").strip()
        req_text = (request.data.get("request") or request.data.get("input") or "").strip()
        if not agent or not agent_registry.has(agent):
            return error_response("Unknown or missing 'agent'.", code="invalid", status=400)
        if not req_text:
            return error_response("A 'request' is required.", code="invalid", status=400)
        params = request.data.get("params") or {}
        if request.data.get("sandbox") in _TRUE:
            return success_response(data=executor.preview(request.user, agent, req_text, params))
        run = executor.run(request.user, agent, req_text, params=params)
        return success_response(data=_run_dict(run, with_steps=True, full=True))


class AgentHealthView(APIView):
    """Per-agent health: last run, success/failure rate, avg latency/confidence/quality."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        rows = []
        for p in agent_registry.all():
            runs = AgentRun.objects.filter(owner=request.user, agent_name=p.name)
            total = runs.count()
            succeeded = runs.filter(status=RunStatus.SUCCEEDED).count()
            agg = runs.aggregate(lat=Avg("duration_ms"), conf=Avg("confidence"), q=Avg("quality_score"))
            last = runs.order_by("-created_at").first()
            tool_failures = AgentRunStep.objects.filter(
                run__owner=request.user, run__agent_name=p.name, step_type="tool_call", ok=False).count()
            rows.append({
                "agent": p.name, "title": p.title, "runs": total,
                "success_rate": round(succeeded / total, 2) if total else None,
                "failure_rate": round((total - succeeded) / total, 2) if total else None,
                "avg_latency_ms": round(agg["lat"]) if agg["lat"] else None,
                "avg_confidence": round(agg["conf"], 1) if agg["conf"] else None,
                "avg_quality": round(agg["q"], 1) if agg["q"] else None,
                "tool_failures": tool_failures,
                "validation_failures": runs.filter(validation_ok=False).count(),
                "fallbacks": runs.filter(fallback_used=True).count(),
                "last_run": last.created_at if last else None,
            })
        return success_response(data={"health": rows})


class AgentRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        qs = AgentRun.objects.filter(owner=request.user)
        agent = request.query_params.get("agent")
        if agent:
            qs = qs.filter(agent_name=agent)
        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except ValueError:
            limit = 30
        return success_response(data={"runs": [_run_dict(r) for r in qs.order_by("-created_at")[:limit]]})


class AgentRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id):
        run = AgentRun.objects.filter(owner=request.user, id=run_id).first()
        if not run:
            return error_response("Run not found.", code="not_found", status=404)
        return success_response(data=_run_dict(run, with_steps=True, full=True))


def _run_dict(run: AgentRun, *, with_steps: bool = False, full: bool = False) -> dict:
    data = {
        "id": str(run.id), "agent": run.agent_name, "request": run.request, "status": run.status,
        "answer": run.answer, "reasoning": run.reasoning, "confidence": run.confidence, "found": run.found,
        "knowledge_version": run.knowledge_version, "consensus_version": run.consensus_version,
        "tools_used": run.tools_used, "quality_score": run.quality_score,
        "grounding_score": run.grounding_score, "evidence_score": run.evidence_score,
        "completeness_score": run.completeness_score, "fallback_used": run.fallback_used,
        "retry_count": run.retry_count, "provider": run.provider, "model": run.model,
        "prompt_version": run.prompt_version, "inference_ms": run.inference_ms,
        "tool_latency_ms": run.tool_latency_ms, "duration_ms": run.duration_ms,
        "validation_ok": run.validation_ok, "created_at": run.created_at,
    }
    if full:
        data["result"] = run.result
        data["validation_issues"] = run.validation_issues
        data["error"] = run.error
    if with_steps:
        data["steps"] = [
            {"order": s.order, "type": s.step_type, "name": s.name, "ok": s.ok,
             "duration_ms": s.duration_ms, "detail": s.detail}
            for s in run.steps.all()
        ]
    return data


# ---------------------------------------------------------------------------
# Multi-Agent Planner (12C)
# ---------------------------------------------------------------------------


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class PlannerRunView(APIView):
    # The planner orchestrates concurrent agents and manages its own
    # transactions; it must not run inside the request-level atomic block.
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        req_text = (request.data.get("request") or request.data.get("input") or "").strip()
        if not req_text:
            return error_response("A 'request' is required.", code="invalid", status=400)
        policy = request.data.get("policy", ExecutionPolicy.BALANCED)
        if policy not in ExecutionPolicy.values:
            return error_response("Invalid policy.", code="invalid", status=400)
        plan = planner.run(request.user, req_text, policy=policy, params=request.data.get("params") or {})
        return success_response(data=_plan_dict(plan, full=True, graph=True))


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class PlannerApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, plan_id):
        plan = PlannerRun.objects.filter(owner=request.user, id=plan_id).first()
        if not plan:
            return error_response("Plan not found.", code="not_found", status=404)
        if plan.status != PlannerStatus.PENDING_APPROVAL:
            return error_response("Plan is not awaiting approval.", code="invalid", status=400)
        resumed = planner.approve(request.user, plan)
        return success_response(data=_plan_dict(resumed, full=True))


class PlannerRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except ValueError:
            limit = 30
        qs = PlannerRun.objects.filter(owner=request.user).order_by("-created_at")[:limit]
        return success_response(data={"runs": [_plan_dict(p) for p in qs]})


class PlannerRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, plan_id):
        plan = PlannerRun.objects.filter(owner=request.user, id=plan_id).first()
        if not plan:
            return error_response("Plan not found.", code="not_found", status=404)
        return success_response(data=_plan_dict(plan, full=True, graph=True))


class PlannerGraphView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, plan_id):
        plan = PlannerRun.objects.filter(owner=request.user, id=plan_id).first()
        if not plan:
            return error_response("Plan not found.", code="not_found", status=404)
        return success_response(data=_execution_graph(plan))


class PlannerMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        runs = PlannerRun.objects.filter(owner=request.user)
        total = runs.count()
        succeeded = runs.filter(status=PlannerStatus.SUCCEEDED).count()
        agg = runs.aggregate(q=Avg("planner_quality"), tot=Avg("total_ms"), exe=Avg("execution_ms"),
                             mrg=Avg("merge_ms"), plan=Avg("planning_ms"), pe=Avg("parallel_efficiency"),
                             conf=Avg("confidence"))
        return success_response(data={
            "total_plans": total,
            "success_rate": round(succeeded / total, 2) if total else None,
            "avg_quality": round(agg["q"], 1) if agg["q"] else None,
            "avg_confidence": round(agg["conf"], 1) if agg["conf"] else None,
            "avg_total_ms": round(agg["tot"]) if agg["tot"] else None,
            "avg_planning_ms": round(agg["plan"]) if agg["plan"] else None,
            "avg_execution_ms": round(agg["exe"]) if agg["exe"] else None,
            "avg_merge_ms": round(agg["mrg"]) if agg["mrg"] else None,
            "avg_parallel_efficiency": round(agg["pe"], 2) if agg["pe"] else None,
            "policies": list(ExecutionPolicy.values),
        })


def _plan_dict(plan: PlannerRun, *, full: bool = False, graph: bool = False) -> dict:
    data = {
        "id": str(plan.id), "request": plan.request, "policy": plan.policy,
        "execution_mode": plan.execution_mode, "status": plan.status, "intent": plan.intent,
        "selected_agents": [s["agent"] for s in plan.selected_agents],
        "answer": plan.answer, "reasoning": plan.reasoning, "confidence": plan.confidence,
        "found": plan.found, "knowledge_version": plan.knowledge_version,
        "consensus_version": plan.consensus_version, "planner_quality": plan.planner_quality,
        "requires_approval": plan.requires_approval, "approved": plan.approved,
        "agent_count": plan.agent_count, "total_ms": plan.total_ms,
        "parallel_efficiency": plan.parallel_efficiency, "created_at": plan.created_at,
    }
    if full:
        data.update({
            "result": plan.result, "scores": {
                "planner_quality": plan.planner_quality, "selection_score": plan.selection_score,
                "merge_quality": plan.merge_quality, "grounding_score": plan.grounding_score,
                "evidence_coverage": plan.evidence_coverage,
                "conflict_resolution_score": plan.conflict_resolution_score},
            "observability": {
                "planning_ms": plan.planning_ms, "execution_ms": plan.execution_ms,
                "merge_ms": plan.merge_ms, "validation_ms": plan.validation_ms,
                "total_ms": plan.total_ms, "parallel_efficiency": plan.parallel_efficiency,
                "tool_calls": plan.tool_calls, "llm_calls": plan.llm_calls},
            "steps": [{"order": s.order, "phase": s.phase, "name": s.name, "ok": s.ok,
                       "duration_ms": s.duration_ms, "detail": s.detail} for s in plan.steps.all()],
            "error": plan.error,
        })
    if graph:
        data["execution_graph"] = _execution_graph(plan)
    return data


def _execution_graph(plan: PlannerRun) -> dict:
    nodes = [{"id": "planner", "type": "planner", "label": plan.intent or "Planner"}]
    edges = []
    for run in plan.agent_runs.all():
        nodes.append({"id": run.agent_name, "type": "agent", "label": run.agent_name,
                      "status": run.status, "confidence": run.confidence, "quality": run.quality_score})
        edges.append({"source": "planner", "target": run.agent_name, "type": "executes"})
        for t in run.tools_used:
            tid = f"{run.agent_name}:{t}"
            nodes.append({"id": tid, "type": "tool", "label": t})
            edges.append({"source": run.agent_name, "target": tid, "type": "uses"})
    nodes.append({"id": "answer", "type": "result", "label": "Merged answer"})
    for run in plan.agent_runs.all():
        edges.append({"source": run.agent_name, "target": "answer", "type": "contributes"})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Agent Collaboration (12D)
# ---------------------------------------------------------------------------


class CollaborationTemplatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data={"templates": [
            {"name": t.name, "title": t.title, "description": t.description, "policy": t.policy,
             "human_required": t.human_required,
             "stages": [{"type": s.type, "agents": list(s.agents), "role": s.role} for s in t.stages]}
            for t in TEMPLATES.values()]})


class CollaborationRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        req_text = (request.data.get("request") or "").strip()
        template = request.data.get("template")
        if not req_text and not template:
            return error_response("A 'request' or 'template' is required.", code="invalid", status=400)
        if template and not get_template(template):
            return error_response("Unknown workflow template.", code="invalid", status=400)
        policy = request.data.get("policy", CollaborationPolicy.SEQUENTIAL)
        if policy not in CollaborationPolicy.values:
            return error_response("Invalid policy.", code="invalid", status=400)
        collab = collab_engine.run(request.user, req_text or template, template=template,
                                   agents=request.data.get("agents"), policy=policy)
        return success_response(data=_collab_dict(collab, full=True, graph=True))


class CollaborationApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, collab_id):
        collab = CollaborationRun.objects.filter(owner=request.user, id=collab_id).first()
        if not collab:
            return error_response("Collaboration not found.", code="not_found", status=404)
        if collab.status != CollaborationStatus.PENDING_APPROVAL:
            return error_response("Not awaiting approval.", code="invalid", status=400)
        collab_engine.approve(request.user, collab)
        return success_response(data=_collab_dict(collab, full=True))


class CollaborationRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except ValueError:
            limit = 30
        qs = CollaborationRun.objects.filter(owner=request.user).order_by("-created_at")[:limit]
        return success_response(data={"runs": [_collab_dict(c) for c in qs]})


class CollaborationRunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, collab_id):
        collab = CollaborationRun.objects.filter(owner=request.user, id=collab_id).first()
        if not collab:
            return error_response("Collaboration not found.", code="not_found", status=404)
        return success_response(data=_collab_dict(collab, full=True, graph=True))


class CollaborationGraphView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, collab_id):
        collab = CollaborationRun.objects.filter(owner=request.user, id=collab_id).first()
        if not collab:
            return error_response("Collaboration not found.", code="not_found", status=404)
        return success_response(data=_collab_graph(collab))


class CollaborationMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        runs = CollaborationRun.objects.filter(owner=request.user)
        total = runs.count()
        succeeded = runs.filter(status=CollaborationStatus.SUCCEEDED).count()
        approvals = runs.filter(human_required=True).count()
        agg = runs.aggregate(q=Avg("collaboration_quality"), ar=Avg("agreement_rate"),
                             rs=Avg("review_success_rate"), tr=Avg("tool_reuse_pct"),
                             lat=Avg("total_ms"), deb=Avg("debate_count"))
        return success_response(data={
            "total_collaborations": total,
            "success_rate": round(succeeded / total, 2) if total else None,
            "avg_collaboration_quality": round(agg["q"], 1) if agg["q"] else None,
            "avg_agreement_rate": round(agg["ar"], 2) if agg["ar"] is not None else None,
            "avg_review_success_rate": round(agg["rs"], 2) if agg["rs"] is not None else None,
            "avg_tool_reuse_pct": round(agg["tr"], 1) if agg["tr"] is not None else None,
            "avg_latency_ms": round(agg["lat"]) if agg["lat"] else None,
            "debate_frequency": round(agg["deb"], 2) if agg["deb"] is not None else None,
            "human_approval_rate": round(approvals / total, 2) if total else None,
            "templates": list(TEMPLATES.keys()),
        })


def _collab_dict(c: CollaborationRun, *, full: bool = False, graph: bool = False) -> dict:
    data = {
        "id": str(c.id), "workflow": c.workflow, "request": c.request, "policy": c.policy,
        "status": c.status, "answer": c.answer, "reasoning": c.reasoning, "confidence": c.confidence,
        "found": c.found, "knowledge_version": c.knowledge_version, "consensus_version": c.consensus_version,
        "collaboration_quality": c.collaboration_quality, "agreement_rate": c.agreement_rate,
        "review_success_rate": c.review_success_rate, "debate_count": c.debate_count,
        "tool_reuse_pct": c.tool_reuse_pct, "stages_count": c.stages_count, "agent_count": c.agent_count,
        "human_required": c.human_required, "approved": c.approved, "total_ms": c.total_ms,
        "created_at": c.created_at,
    }
    if full:
        data["result"] = c.result
        data["steps"] = [
            {"order": s.order, "stage": s.stage_type, "agent": s.agent, "role": s.role,
             "output": s.output, "approved": s.approved, "vote": s.vote, "review": s.review,
             "confidence": s.confidence, "quality": s.quality, "latency_ms": s.latency_ms}
            for s in c.steps.all()
        ]
    if graph:
        data["collaboration_graph"] = _collab_graph(c)
    return data


def _collab_graph(c: CollaborationRun) -> dict:
    nodes = [{"id": "start", "type": "start", "label": c.workflow}]
    edges = []
    prev = "start"
    for s in c.steps.all():
        nid = f"{s.order}:{s.agent or s.stage_type}"
        nodes.append({"id": nid, "type": s.stage_type, "agent": s.agent, "label": s.agent or s.stage_type,
                      "approved": s.approved, "vote": s.vote, "confidence": s.confidence})
        edges.append({"source": prev, "target": nid, "type": s.stage_type})
        prev = nid
    nodes.append({"id": "final", "type": "result", "label": "Final answer"})
    edges.append({"source": prev, "target": "final", "type": "final"})
    return {"nodes": nodes, "edges": edges}
