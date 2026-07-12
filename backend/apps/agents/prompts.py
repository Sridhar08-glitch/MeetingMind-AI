"""Versioned agent prompts (registered in the shared prompt registry)."""
from __future__ import annotations

from apps.meetings.prompts.registry import Prompt, register_prompt

AGENT_SYNTHESIS_VERSION = "v2"

AGENT_SCHEMA = (
    '{"answer": "grounded answer using ONLY the evidence", '
    '"reasoning": "brief explanation of how you reached it", '
    '"key_points": ["bullet", "points"], '
    '"recommendations": ["actionable recommendation"], '
    '"next_actions": ["concrete next step"], '
    '"confidence": 82, "found": true}'
)

AGENT_SYNTHESIS = register_prompt(Prompt(
    name="agent_synthesis",
    version=AGENT_SYNTHESIS_VERSION,
    system=(
        "You are a specialized AI agent. Your role: {role}. You answer the user's "
        "request using ONLY the evidence gathered by your tools — never invent "
        "facts, names, numbers or dates. Be concise and decision-useful. Provide "
        "actionable recommendations and concrete next actions where the evidence "
        "supports them. If the evidence is insufficient, set \"found\": false and "
        "say what is missing. Respond with ONE valid JSON object only, matching "
        "the schema."
    ),
    template=(
        "Schema:\n{schema}\n\n"
        "Evidence gathered by your tools:\n{evidence}\n\n"
        "User request: {request}"
    ),
))


# --- Planner (12C) ---------------------------------------------------------

PLANNER_INTENT_VERSION = "v1"

PLANNER_INTENT_SCHEMA = (
    '{"intent": "one-line restatement of what the user wants", '
    '"agents": ["agent_name", ...], '
    '"mode": "parallel|sequential", '
    '"reasoning": "why these agents"}'
)

PLANNER_INTENT = register_prompt(Prompt(
    name="planner_intent",
    version=PLANNER_INTENT_VERSION,
    system=(
        "You are the planner for a multi-agent workspace assistant. Given a user "
        "request, decide which specialized agents should handle it. Choose ONLY "
        "from the provided agent list, by their exact names. Prefer the fewest "
        "agents that fully cover the request. Respond with ONE valid JSON object "
        "only, matching the schema."
    ),
    template="Schema:\n{schema}\n\nAvailable agents:\n{agents}\n\nUser request: {request}",
))

PLANNER_MERGE_VERSION = "v1"

PLANNER_MERGE_SCHEMA = (
    '{"answer": "one unified answer combining the agent findings", '
    '"reasoning": "how the findings fit together", "confidence": 84}'
)

PLANNER_MERGE = register_prompt(Prompt(
    name="planner_merge",
    version=PLANNER_MERGE_VERSION,
    system=(
        "You merge the findings of several specialized agents into ONE coherent, "
        "non-redundant answer for the user. Use ONLY what the agents reported — "
        "never add facts. Preserve important specifics; remove duplication. If the "
        "agents disagree, note the disagreement neutrally. Respond with ONE valid "
        "JSON object only, matching the schema."
    ),
    template="Schema:\n{schema}\n\nOriginal request: {request}\n\nAgent findings:\n{findings}",
))
