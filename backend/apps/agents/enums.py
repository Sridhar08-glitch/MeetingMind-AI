"""Enumerations for the multi-agent framework (Phase 12)."""
from __future__ import annotations

from django.db import models


class AgentCapability(models.TextChoices):
    """Declarative capabilities an agent may hold (gate access to tools)."""

    KNOWLEDGE_SEARCH = "knowledge_search", "Knowledge search"
    ORG_QA = "org_qa", "Organization Q&A"
    TIME_TRAVEL = "time_travel", "Time travel"
    CONSENSUS = "consensus", "Consensus & conflicts"
    EXECUTIVE = "executive", "Executive intelligence"
    RECOMMENDATIONS = "recommendations", "Recommendations"
    WORKSPACE = "workspace", "Workspace (tasks/risks/decisions)"
    REPORTING = "reporting", "Reporting"
    RISK = "risk", "Risk analysis"


class RunStatus(models.TextChoices):
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class StepType(models.TextChoices):
    TOOL_CALL = "tool_call", "Tool call"
    SYNTHESIZE = "synthesize", "Synthesize"
    VALIDATE = "validate", "Validate"
    PLAN = "plan", "Plan"


class PlannerStatus(models.TextChoices):
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    PENDING_APPROVAL = "pending_approval", "Pending approval"


class ExecutionMode(models.TextChoices):
    SINGLE = "single", "Single agent"
    SEQUENTIAL = "sequential", "Sequential"
    PARALLEL = "parallel", "Parallel"
    CONDITIONAL = "conditional", "Conditional"


class ExecutionPolicy(models.TextChoices):
    FAST = "fast", "Fast"
    BALANCED = "balanced", "Balanced"
    HIGHEST_QUALITY = "highest_quality", "Highest quality"
    LOWEST_LATENCY = "lowest_latency", "Lowest latency"
    RESEARCH = "research", "Research"


class PlannerPhase(models.TextChoices):
    ANALYZE = "analyze", "Analyze intent"
    DECOMPOSE = "decompose", "Decompose"
    SELECT = "select", "Select agents"
    EXECUTE = "execute", "Execute"
    MERGE = "merge", "Merge"
    RESOLVE = "resolve", "Resolve conflicts"
    VALIDATE = "validate", "Validate"


class CollaborationStatus(models.TextChoices):
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    PENDING_APPROVAL = "pending_approval", "Pending human approval"


class CollaborationPolicy(models.TextChoices):
    SEQUENTIAL = "sequential", "Sequential"
    PARALLEL = "parallel", "Parallel"
    REVIEW_REQUIRED = "review_required", "Review required"
    DEBATE_REQUIRED = "debate_required", "Debate required"
    CONSENSUS_REQUIRED = "consensus_required", "Consensus required"


class CollaborationStageType(models.TextChoices):
    PRODUCE = "produce", "Produce"
    HANDOFF = "handoff", "Handoff"
    REVIEW = "review", "Review"
    VOTE = "vote", "Vote"
    DEBATE = "debate", "Debate"
    CONSENSUS = "consensus", "Consensus"
    HUMAN_GATE = "human_gate", "Human gate"
    MERGE = "merge", "Merge"
