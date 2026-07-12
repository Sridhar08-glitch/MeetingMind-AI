"""The 12 production agent profiles (Phase 12B).

Every agent is DECLARATIVE — a profile of capabilities + allowed tools + role.
The generic BaseAgent runs them all; there is no agent-specific business logic.
Adding an agent = adding a profile here.
"""
from apps.agents.enums import AgentCapability as Cap
from apps.agents.framework.registry import AgentProfile, register_agent

AGENTS = [
    AgentProfile(
        name="executive_agent", title="Executive Agent",
        role="brief leadership on workspace health, score, trends, risks and strategic recommendations",
        description="Executive briefs, organization health, workspace score, strategic recommendations, "
                    "trend analysis and executive history.",
        capabilities=(Cap.EXECUTIVE, Cap.RECOMMENDATIONS, Cap.REPORTING),
        tools=("executive_health", "recommendations", "workspace_status", "history", "trends", "reporting"),
    ),
    AgentProfile(
        name="project_manager_agent", title="Project Manager Agent",
        role="plan sprints, prioritize tasks, surface blocked work, dependencies and roadmaps",
        description="Sprint planning, task prioritization, milestones, dependencies, blocked tasks, "
                    "roadmaps and capacity planning.",
        capabilities=(Cap.WORKSPACE, Cap.EXECUTIVE),
        tools=("tasks", "projects", "workspace_status", "comparison"),
    ),
    AgentProfile(
        name="technical_architect_agent", title="Technical Architect Agent",
        role="review architecture decisions, technical debt, dependencies and technology choices",
        description="Architecture reviews, technical debt, dependency analysis, technology and scalability "
                    "and security review from recorded decisions and knowledge.",
        capabilities=(Cap.KNOWLEDGE_SEARCH, Cap.CONSENSUS, Cap.RISK),
        tools=("knowledge_search", "decisions", "consensus", "risks"),
    ),
    AgentProfile(
        name="qa_agent", title="QA Agent",
        role="assess regression risk, test coverage gaps, release readiness and quality risks",
        description="Regression analysis, test coverage, missing tests, risk detection, release readiness "
                    "and bug-trend analysis from meetings, tasks and risks.",
        capabilities=(Cap.WORKSPACE, Cap.RISK, Cap.KNOWLEDGE_SEARCH),
        tools=("tasks", "risks", "meetings", "knowledge_search"),
    ),
    AgentProfile(
        name="risk_analyst_agent", title="Risk Analyst Agent",
        role="detect, prioritize and propose mitigations for project, security and timeline risks",
        description="Risk detection, prioritization, mitigation plans, compliance, security and timeline risks.",
        capabilities=(Cap.RISK, Cap.CONSENSUS, Cap.WORKSPACE),
        tools=("risks", "conflicts", "workspace_status", "consensus"),
    ),
    AgentProfile(
        name="business_analyst_agent", title="Business Analyst Agent",
        role="derive requirements, user stories, acceptance criteria and gaps from discussions",
        description="Requirements, user stories, acceptance criteria, gap analysis and business reports.",
        capabilities=(Cap.KNOWLEDGE_SEARCH, Cap.REPORTING),
        tools=("knowledge_search", "meetings", "decisions", "reporting"),
    ),
    AgentProfile(
        name="documentation_agent", title="Documentation Agent",
        role="draft documentation, release notes and technical docs grounded in decisions and meetings",
        description="API docs, release notes, technical documentation, user guides and architecture docs.",
        capabilities=(Cap.KNOWLEDGE_SEARCH, Cap.REPORTING),
        tools=("knowledge_search", "decisions", "meetings", "reporting"),
    ),
    AgentProfile(
        name="meeting_analyst_agent", title="Meeting Analyst Agent",
        role="evaluate meeting quality, participation, missing decisions and action items",
        description="Meeting quality, participation, missing decisions, missing action items and effectiveness.",
        capabilities=(Cap.KNOWLEDGE_SEARCH,),
        tools=("meetings", "knowledge_search", "decisions"),
    ),
    AgentProfile(
        name="knowledge_agent", title="Knowledge Agent",
        role="answer questions from organizational knowledge with evidence, consensus and evolution",
        description="Organization search, decision lookup, consensus, time travel, knowledge evolution "
                    "and conflict resolution.",
        capabilities=(Cap.KNOWLEDGE_SEARCH, Cap.ORG_QA, Cap.CONSENSUS, Cap.TIME_TRAVEL),
        tools=("knowledge_search", "consensus", "timeline", "conflicts"),
    ),
    AgentProfile(
        name="report_generator_agent", title="Report Generator Agent",
        role="generate executive, project, weekly, monthly and sprint reports from workspace data",
        description="Executive, project, weekly, monthly and sprint reports.",
        capabilities=(Cap.REPORTING, Cap.EXECUTIVE, Cap.WORKSPACE),
        tools=("reporting", "executive_health", "workspace_status", "projects"),
    ),
    AgentProfile(
        name="research_agent", title="Research Agent",
        role="research history, trends, technology comparisons and cross-project insights",
        description="Historical research, trend research, technology comparison, knowledge analysis "
                    "and cross-project insights.",
        capabilities=(Cap.KNOWLEDGE_SEARCH, Cap.TIME_TRAVEL, Cap.EXECUTIVE),
        tools=("knowledge_search", "timeline", "comparison", "trends", "history"),
    ),
    AgentProfile(
        name="customer_success_agent", title="Customer Success Agent",
        role="surface customer requests, recurring problems, feature requests and support trends",
        description="Customer requests, recurring problems, feature requests, support trends and customer health.",
        capabilities=(Cap.WORKSPACE, Cap.RISK, Cap.KNOWLEDGE_SEARCH),
        tools=("customers", "risks", "knowledge_search", "trends"),
    ),
]

for _profile in AGENTS:
    register_agent(_profile)


# Capability matrix — which functional areas each agent's tools cover (docs + UI).
_AREA_BY_TOOL = {
    "knowledge_search": "knowledge", "consensus": "knowledge", "reliability": "knowledge",
    "timeline": "time_travel", "conflicts": "knowledge", "graph": "knowledge",
    "tasks": "tasks", "projects": "projects", "workspace_status": "tasks", "comparison": "projects",
    "meetings": "meetings", "decisions": "decisions", "risks": "risks", "customers": "customers",
    "executive_health": "executive", "recommendations": "executive", "trends": "executive",
    "history": "executive", "reporting": "reports",
}
MATRIX_AREAS = ["meetings", "tasks", "risks", "decisions", "projects", "knowledge",
                "executive", "reports", "time_travel", "customers"]


def capability_matrix() -> list[dict]:
    from apps.agents.framework.registry import agent_registry
    rows = []
    for p in agent_registry.all():
        areas = {_AREA_BY_TOOL.get(t) for t in p.tools}
        rows.append({"agent": p.name, "title": p.title,
                     **{a: (a in areas) for a in MATRIX_AREAS}})
    return rows
