"""Workflow templates + collaboration policies.

A template is a predefined collaboration GRAPH (ordered stages). Each stage names
a stage type (produce/handoff/review/vote/debate/consensus) and the agents that
act in it. Users pick a template instead of wiring agents by hand.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.agents.enums import CollaborationPolicy, CollaborationStageType as S


@dataclass(frozen=True)
class Stage:
    type: str
    agents: tuple[str, ...] = ()
    mode: str = "parallel"     # parallel | sequential (for produce)
    role: str = ""


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    title: str
    description: str
    stages: tuple[Stage, ...]
    policy: str = CollaborationPolicy.SEQUENTIAL
    human_required: bool = False


TEMPLATES: dict[str, WorkflowTemplate] = {
    "sprint_planning": WorkflowTemplate(
        "sprint_planning", "Sprint Planning",
        "Plan the next sprint: PM + Risk propose, QA reviews.",
        stages=(
            Stage(S.PRODUCE, ("project_manager_agent", "risk_analyst_agent"), role="propose plan + risks"),
            Stage(S.REVIEW, ("qa_agent",), role="review for quality risks"),
        ),
        policy=CollaborationPolicy.REVIEW_REQUIRED,
    ),
    "executive_review": WorkflowTemplate(
        "executive_review", "Executive Review",
        "Leadership review across health, risks and delivery.",
        stages=(Stage(S.PRODUCE, ("executive_agent", "risk_analyst_agent", "project_manager_agent"),
                      role="assess health, risks, delivery"),),
        policy=CollaborationPolicy.PARALLEL,
    ),
    "release_readiness": WorkflowTemplate(
        "release_readiness", "Release Readiness",
        "Assess readiness, then vote to proceed.",
        stages=(
            Stage(S.PRODUCE, ("qa_agent", "risk_analyst_agent"), role="assess readiness"),
            Stage(S.VOTE, ("qa_agent", "risk_analyst_agent", "technical_architect_agent"), role="vote to release"),
        ),
        policy=CollaborationPolicy.CONSENSUS_REQUIRED,
        human_required=True,
    ),
    "risk_assessment": WorkflowTemplate(
        "risk_assessment", "Risk Assessment",
        "Risk analysis reviewed by architecture and QA.",
        stages=(
            Stage(S.PRODUCE, ("risk_analyst_agent",), role="identify + prioritize risks"),
            Stage(S.REVIEW, ("technical_architect_agent", "qa_agent"), role="review risks"),
        ),
        policy=CollaborationPolicy.REVIEW_REQUIRED,
    ),
    "architecture_review": WorkflowTemplate(
        "architecture_review", "Architecture Review",
        "Architect proposes; QA + Risk review; debate resolves disagreement.",
        stages=(
            Stage(S.PRODUCE, ("technical_architect_agent",), role="propose architecture"),
            Stage(S.REVIEW, ("qa_agent", "risk_analyst_agent"), role="critique proposal"),
            Stage(S.DEBATE, ("technical_architect_agent", "research_agent"), role="resolve disagreement"),
        ),
        policy=CollaborationPolicy.DEBATE_REQUIRED,
    ),
    "customer_feedback": WorkflowTemplate(
        "customer_feedback", "Customer Feedback Analysis",
        "Customer Success + Business Analyst analyse feedback.",
        stages=(Stage(S.PRODUCE, ("customer_success_agent", "business_analyst_agent"),
                      role="analyse customer feedback"),),
        policy=CollaborationPolicy.PARALLEL,
    ),
    "incident_postmortem": WorkflowTemplate(
        "incident_postmortem", "Incident Postmortem",
        "Meeting Analyst → Risk Analyst → Documentation hand-off chain.",
        stages=(Stage(S.HANDOFF, ("meeting_analyst_agent", "risk_analyst_agent", "documentation_agent"),
                      mode="sequential", role="analyse → risks → document"),),
        policy=CollaborationPolicy.SEQUENTIAL,
    ),
}


def get_template(name: str) -> WorkflowTemplate | None:
    return TEMPLATES.get(name)


def policy_stages(agents: list[str], policy: str) -> tuple[Stage, ...]:
    """Build stages for an ad-hoc (template-less) collaboration from selected
    agents under a collaboration policy."""
    agents = tuple(dict.fromkeys(agents))
    if policy == CollaborationPolicy.PARALLEL:
        return (Stage(S.PRODUCE, agents, mode="parallel", role="produce"),)
    if policy == CollaborationPolicy.REVIEW_REQUIRED:
        return (Stage(S.PRODUCE, agents, mode="parallel", role="produce"),
                Stage(S.REVIEW, agents, role="peer review"))
    if policy == CollaborationPolicy.DEBATE_REQUIRED:
        return (Stage(S.PRODUCE, agents, mode="parallel", role="produce"),
                Stage(S.DEBATE, agents, role="debate"))
    if policy == CollaborationPolicy.CONSENSUS_REQUIRED:
        return (Stage(S.PRODUCE, agents, mode="parallel", role="produce"),
                Stage(S.CONSENSUS, agents, role="reach consensus"))
    # sequential (handoff-style chain)
    return (Stage(S.HANDOFF, agents, mode="sequential", role="hand off"),)
