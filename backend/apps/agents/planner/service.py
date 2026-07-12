"""The multi-agent orchestrator. Reuses the executor, validator, consensus and
conflict registries; agents stay simple. Supports parallel/sequential execution,
execution policies, agent reputation, conflict resolution, a human-approval gate,
full observability and orchestration history."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from time import perf_counter

from django.db import connection, transaction
from django.utils import timezone

from apps.agents.enums import ExecutionMode, PlannerPhase, PlannerStatus, RunStatus
from apps.agents.framework.executor import executor as agent_executor
from apps.agents.framework.validator import validator
from apps.agents.models import PlannerRun, PlannerStep
from apps.knowledge.services.index import KnowledgeIndexService

from .intent import analyze_intent
from .merge import ResultMerger
from .policies import get_policy
from .selector import select_agents

logger = logging.getLogger("meetingmind.ai")

# Agents that would create/modify/delete data require human approval before
# execution. All current agents are read-only, so this stays empty — but the
# gate exists for future automation (Sandbox → Approval → Execute).
MUTATING_AGENTS: set[str] = set()


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


class PlannerService:
    def __init__(self, llm=None):
        self.llm = llm
        self.merger = ResultMerger(llm=llm)

    # -- public ------------------------------------------------------------

    def run(self, owner, request: str, *, policy: str = "balanced",
            params: dict | None = None, approve: bool = False) -> PlannerRun:
        params = params or {}
        pol = get_policy(policy)
        total_t = perf_counter()
        plan = PlannerRun.objects.create(owner=owner, request=request, policy=policy,
                                         status=PlannerStatus.RUNNING)
        steps: list[dict] = []

        # 1. Intent + 2. decompose ----------------------------------------
        t = perf_counter()
        intent = analyze_intent(request, llm=self.llm)
        planning_ms = int((perf_counter() - t) * 1000)
        steps.append({"phase": PlannerPhase.ANALYZE, "name": intent["source"], "ok": True,
                      "ms": planning_ms, "detail": {"agents": intent["agents"], "mode": intent["mode"]}})

        # 3. Select agents ------------------------------------------------
        t = perf_counter()
        selected = select_agents(owner, intent["agents"], pol)
        steps.append({"phase": PlannerPhase.SELECT, "name": "selector", "ok": bool(selected),
                      "ms": int((perf_counter() - t) * 1000),
                      "detail": {"selected": [s["agent"] for s in selected]}})
        sub_requests = {s["agent"]: request for s in selected}   # decompose: default = original ask
        steps.append({"phase": PlannerPhase.DECOMPOSE, "name": "decomposer", "ok": True, "ms": 0,
                      "detail": {"sub_requests": len(sub_requests)}})

        plan.intent = intent["intent"]
        plan.selected_agents = selected
        plan.agent_count = len(selected)

        # 4. Approval gate -------------------------------------------------
        requires_approval = bool(params.get("require_approval")) or bool(
            {s["agent"] for s in selected} & MUTATING_AGENTS)
        if requires_approval and not approve:
            plan.requires_approval = True
            plan.status = PlannerStatus.PENDING_APPROVAL
            plan.planning_ms = planning_ms
            plan.total_ms = int((perf_counter() - total_t) * 1000)
            plan.save()
            self._persist_steps(plan, steps)
            return plan

        plan.requires_approval = requires_approval
        plan.approved = approve or not requires_approval

        # 5. Execute ------------------------------------------------------
        mode = ExecutionMode.SINGLE if len(selected) == 1 else (
            ExecutionMode.PARALLEL if pol.parallel else ExecutionMode.SEQUENTIAL)
        plan.execution_mode = mode
        t = perf_counter()
        agent_runs = self._execute(owner, plan, selected, sub_requests, pol, mode)
        execution_ms = int((perf_counter() - t) * 1000)
        agent_total_ms = sum(r.duration_ms for r in agent_runs)
        for r in agent_runs:
            steps.append({"phase": PlannerPhase.EXECUTE, "name": r.agent_name, "ok": r.status == RunStatus.SUCCEEDED,
                          "ms": r.duration_ms, "detail": {"confidence": r.confidence, "quality": r.quality_score,
                                                          "tools": r.tools_used, "retried": r.retry_count}})

        results = [r.result for r in agent_runs if r.status == RunStatus.SUCCEEDED and r.result]

        # 6. Merge + 7. resolve -------------------------------------------
        t = perf_counter()
        merged = self.merger.merge(owner, request, results, use_llm=pol.merge_llm)
        merge_ms = int((perf_counter() - t) * 1000)
        steps.append({"phase": PlannerPhase.MERGE, "name": "merger", "ok": bool(merged["answer"]),
                      "ms": merge_ms, "detail": {"agents_merged": len(results), "llm_used": merged["llm_used"]}})
        steps.append({"phase": PlannerPhase.RESOLVE, "name": "conflict_resolver",
                      "ok": merged["conflict_resolution"]["score"] >= 100,
                      "ms": 0, "detail": merged["conflict_resolution"]})

        # 8. Validate -----------------------------------------------------
        t = perf_counter()
        v = validator.validate(answer=merged["answer"], confidence=merged["confidence"],
                               evidence=merged["evidence"], sources=merged["sources"], found=merged["found"])
        validation_ms = int((perf_counter() - t) * 1000)
        steps.append({"phase": PlannerPhase.VALIDATE, "name": "validator", "ok": v.ok, "ms": validation_ms,
                      "detail": {"issues": v.issues}})

        # Scores + observability ------------------------------------------
        stats = KnowledgeIndexService().stats(owner)
        avg_conf = merged["confidence"]
        selection_score = round(sum(s["selection_score"] for s in selected) / max(1, len(selected)), 1)
        planner_quality = _clamp(0.25 * merged["merge_quality"] + 0.2 * merged["grounding_score"]
                                 + 0.2 * merged["evidence_coverage"] + 0.15 * avg_conf
                                 + 0.1 * merged["conflict_resolution"]["score"] + 0.1 * selection_score)
        parallel_eff = round(agent_total_ms / execution_ms, 2) if execution_ms else 1.0

        self._finalize(plan, merged, v, stats, {
            "planning_ms": planning_ms, "execution_ms": execution_ms, "merge_ms": merge_ms,
            "validation_ms": validation_ms, "total_ms": int((perf_counter() - total_t) * 1000),
            "parallel_efficiency": parallel_eff, "selection_score": selection_score,
            "planner_quality": planner_quality,
            "tool_calls": sum(len(r.tools_used) for r in agent_runs),
            "llm_calls": len(agent_runs) + (1 if merged["llm_used"] else 0) + 1,  # agents + merge + intent
        })
        self._persist_steps(plan, steps)
        return plan

    def approve(self, owner, plan: PlannerRun) -> PlannerRun:
        """Resume a plan that was held at the approval gate."""
        if plan.status != PlannerStatus.PENDING_APPROVAL:
            return plan
        plan.approved = True
        plan.approved_by = owner
        plan.approved_at = timezone.now()
        plan.save(update_fields=["approved", "approved_by", "approved_at", "updated_at"])
        # Re-run with the same request/policy, approval granted.
        return self.run(owner, plan.request, policy=plan.policy, approve=True)

    # -- execution ----------------------------------------------------------

    def _execute(self, owner, plan, selected, sub_requests, pol, mode):
        if mode == ExecutionMode.PARALLEL:
            return self._parallel(owner, plan, selected, sub_requests, pol)
        return self._sequential(owner, plan, selected, sub_requests, pol)

    def _run_one(self, owner, plan, agent_name, req, cache):
        run = agent_executor.run(owner, agent_name, req, planner_run=plan, cache=cache)
        if run.status == RunStatus.FAILED:   # retry once
            run = agent_executor.run(owner, agent_name, req, planner_run=plan, cache=cache)
        return run

    def _sequential(self, owner, plan, selected, sub_requests, pol):
        cache: dict = {}   # sequential runs share tool results
        return [self._run_one(owner, plan, s["agent"], sub_requests[s["agent"]], cache) for s in selected]

    def _parallel(self, owner, plan, selected, sub_requests, pol):
        def task(agent_name, req):
            try:
                return self._run_one(owner, plan, agent_name, req, cache=None)
            finally:
                connection.close()   # close this worker thread's DB connection

        runs = []
        with ThreadPoolExecutor(max_workers=min(len(selected), 6)) as pool:
            futures = {pool.submit(task, s["agent"], sub_requests[s["agent"]]): s["agent"] for s in selected}
            try:
                for f in as_completed(futures, timeout=pol.agent_timeout_s):
                    runs.append(f.result())
            except TimeoutError:
                logger.warning("Planner parallel execution hit timeout; collected %d/%d agents.",
                               len(runs), len(selected))
        return runs

    # -- persistence --------------------------------------------------------

    @transaction.atomic
    def _finalize(self, plan, merged, v, stats, obs):
        plan.status = PlannerStatus.SUCCEEDED
        plan.answer = merged["answer"]
        plan.reasoning = merged["reasoning"]
        plan.confidence = merged["confidence"]
        plan.found = merged["found"]
        plan.knowledge_version = stats.get("knowledge_version", 0)
        plan.consensus_version = _consensus_count(plan.owner)
        plan.result = {**merged, "validation": {"ok": v.ok, "issues": v.issues}}
        plan.merge_quality = merged["merge_quality"]
        plan.grounding_score = merged["grounding_score"]
        plan.evidence_coverage = merged["evidence_coverage"]
        plan.conflict_resolution_score = merged["conflict_resolution"]["score"]
        for k, val in obs.items():
            setattr(plan, k, val)
        plan.save()

    def _persist_steps(self, plan, steps):
        for i, s in enumerate(steps):
            PlannerStep.objects.create(run=plan, order=i, phase=s["phase"], name=s["name"],
                                       ok=s["ok"], duration_ms=s.get("ms", 0), detail=s.get("detail", {}))


def _consensus_count(owner) -> int:
    from apps.knowledge.models import KnowledgeConsensus
    return KnowledgeConsensus.objects.filter(owner=owner).count()


planner = PlannerService()
