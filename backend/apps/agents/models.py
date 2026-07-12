"""Agent run history (audit trail for every agent execution).

Reuses the shared BaseModel. Agents themselves are declarative (defined in the
in-code AgentRegistry, like the prompt registry) — only their RUNS are persisted,
never duplicated business data.
"""
from __future__ import annotations

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.common.models import BaseModel
from .enums import (
    CollaborationPolicy,
    CollaborationStageType,
    CollaborationStatus,
    ExecutionMode,
    ExecutionPolicy,
    PlannerPhase,
    PlannerStatus,
    RunStatus,
    StepType,
)


class AgentRun(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_runs"
    )
    agent_name = models.CharField(max_length=64, db_index=True)
    # Set when this agent run was executed as part of an orchestrated plan.
    planner_run = models.ForeignKey(
        "PlannerRun", on_delete=models.CASCADE, null=True, blank=True, related_name="agent_runs"
    )
    request = models.TextField(blank=True)
    params = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    status = models.CharField(max_length=12, choices=RunStatus.choices, default=RunStatus.RUNNING, db_index=True)

    # Result + explainability (denormalised for quick listing; full object in `result`).
    answer = models.TextField(blank=True)
    reasoning = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    found = models.BooleanField(default=True)
    knowledge_version = models.PositiveIntegerField(default=0)
    consensus_version = models.PositiveIntegerField(default=0)
    tools_used = models.JSONField(default=list, blank=True)
    result = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    inference_ms = models.PositiveIntegerField(default=0)   # LLM latency
    duration_ms = models.PositiveIntegerField(default=0)    # overall execution
    error = models.TextField(blank=True)

    # --- Quality scores (0–100) ---
    grounding_score = models.FloatField(default=0.0)
    evidence_score = models.FloatField(default=0.0)
    completeness_score = models.FloatField(default=0.0)
    quality_score = models.FloatField(default=0.0, db_index=True)   # overall

    # --- Observability ---
    tool_latency_ms = models.PositiveIntegerField(default=0)
    validation_latency_ms = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)
    fallback_used = models.BooleanField(default=False)
    token_usage = models.PositiveIntegerField(default=0)
    validation_ok = models.BooleanField(default=True)
    validation_issues = models.JSONField(default=list, blank=True)
    sandbox = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "agent_name", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.agent_name} [{self.status}]: {self.request[:40]}"


class AgentRunStep(BaseModel):
    """One step within an agent run (tool call / synthesize / validate) — the
    transparent execution trace."""

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField(default=0)
    step_type = models.CharField(max_length=12, choices=StepType.choices)
    name = models.CharField(max_length=64)
    ok = models.BooleanField(default=True)
    duration_ms = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta(BaseModel.Meta):
        ordering = ("order",)
        indexes = [models.Index(fields=["run", "order"])]

    def __str__(self) -> str:
        return f"{self.step_type}:{self.name} ({'ok' if self.ok else 'fail'})"


class PlannerRun(BaseModel):
    """One orchestrated multi-agent run: intent → select → execute → merge →
    resolve → validate → unified explainable answer."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planner_runs"
    )
    request = models.TextField(blank=True)
    policy = models.CharField(max_length=20, choices=ExecutionPolicy.choices, default=ExecutionPolicy.BALANCED)
    execution_mode = models.CharField(max_length=12, choices=ExecutionMode.choices, default=ExecutionMode.PARALLEL)
    status = models.CharField(max_length=18, choices=PlannerStatus.choices, default=PlannerStatus.RUNNING, db_index=True)

    intent = models.TextField(blank=True)
    selected_agents = models.JSONField(default=list, blank=True, encoder=DjangoJSONEncoder)

    # Unified result + explainability.
    answer = models.TextField(blank=True)
    reasoning = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    found = models.BooleanField(default=True)
    knowledge_version = models.PositiveIntegerField(default=0)
    consensus_version = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    # Quality scores (0–100).
    planner_quality = models.FloatField(default=0.0, db_index=True)
    selection_score = models.FloatField(default=0.0)
    merge_quality = models.FloatField(default=0.0)
    grounding_score = models.FloatField(default=0.0)
    evidence_coverage = models.FloatField(default=0.0)
    conflict_resolution_score = models.FloatField(default=100.0)

    # Observability (ms).
    planning_ms = models.PositiveIntegerField(default=0)
    execution_ms = models.PositiveIntegerField(default=0)
    merge_ms = models.PositiveIntegerField(default=0)
    validation_ms = models.PositiveIntegerField(default=0)
    total_ms = models.PositiveIntegerField(default=0)
    parallel_efficiency = models.FloatField(default=0.0)
    agent_count = models.PositiveIntegerField(default=0)
    tool_calls = models.PositiveIntegerField(default=0)
    llm_calls = models.PositiveIntegerField(default=0)

    # Human-in-the-loop approval gate (for future mutating workflows).
    requires_approval = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"]), models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"plan [{self.status}]: {self.request[:40]}"


class PlannerStep(BaseModel):
    """A phase of the orchestration pipeline (analyze/select/execute/merge/…)."""

    run = models.ForeignKey(PlannerRun, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField(default=0)
    phase = models.CharField(max_length=12, choices=PlannerPhase.choices)
    name = models.CharField(max_length=80)
    ok = models.BooleanField(default=True)
    duration_ms = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta(BaseModel.Meta):
        ordering = ("order",)
        indexes = [models.Index(fields=["run", "order"])]

    def __str__(self) -> str:
        return f"{self.phase}:{self.name}"


class CollaborationRun(BaseModel):
    """A collaborative multi-agent workflow: agents produce, hand off, review,
    debate and vote on each other's work before a validated final answer.
    Complements PlannerRun (which just orchestrates)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collaboration_runs"
    )
    planner_run = models.ForeignKey(
        PlannerRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="collaborations"
    )
    workflow = models.CharField(max_length=48, default="custom", db_index=True)   # template name or "custom"
    request = models.TextField(blank=True)
    policy = models.CharField(max_length=20, choices=CollaborationPolicy.choices,
                              default=CollaborationPolicy.SEQUENTIAL)
    status = models.CharField(max_length=18, choices=CollaborationStatus.choices,
                              default=CollaborationStatus.RUNNING, db_index=True)

    answer = models.TextField(blank=True)
    reasoning = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    found = models.BooleanField(default=True)
    knowledge_version = models.PositiveIntegerField(default=0)
    consensus_version = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    # Collaboration metrics.
    collaboration_quality = models.FloatField(default=0.0, db_index=True)
    agreement_rate = models.FloatField(null=True, blank=True)
    review_success_rate = models.FloatField(null=True, blank=True)
    debate_count = models.PositiveIntegerField(default=0)
    tool_reuse_pct = models.FloatField(default=0.0)
    stages_count = models.PositiveIntegerField(default=0)
    agent_count = models.PositiveIntegerField(default=0)
    total_ms = models.PositiveIntegerField(default=0)

    # Human-in-the-loop.
    human_required = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"]), models.Index(fields=["owner", "status"])]

    def __str__(self) -> str:
        return f"collab[{self.workflow}/{self.status}]: {self.request[:40]}"


class CollaborationStep(BaseModel):
    """One collaboration stage — a produce/handoff/review/vote/debate/… act by
    an agent (or the engine), with its input, output and (for reviews) verdict."""

    run = models.ForeignKey(CollaborationRun, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField(default=0)
    stage_type = models.CharField(max_length=12, choices=CollaborationStageType.choices)
    agent = models.CharField(max_length=64, blank=True)
    role = models.CharField(max_length=120, blank=True)
    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    input = models.TextField(blank=True)
    output = models.TextField(blank=True)
    review = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)   # {approved, score, critique}
    approved = models.BooleanField(null=True, blank=True)
    vote = models.CharField(max_length=4, blank=True)   # "yes" | "no"
    confidence = models.FloatField(default=0.0)
    quality = models.FloatField(default=0.0)
    latency_ms = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta(BaseModel.Meta):
        ordering = ("order",)
        indexes = [models.Index(fields=["run", "order"])]

    def __str__(self) -> str:
        return f"{self.stage_type}:{self.agent or 'engine'}"
