"""Knowledge-hub AI prompts (versioned), registered in the shared registry."""
from __future__ import annotations

from apps.meetings.prompts.registry import Prompt, register_prompt

ORG_CHAT_VERSION = "v1"

ORG_CHAT_SCHEMA = '{"answer": "grounded ONLY in the evidence", "citations": [1, 2], "found": true}'

ORG_CHAT = register_prompt(Prompt(
    name="org_chat",
    version=ORG_CHAT_VERSION,
    system=(
        "You are an organizational knowledge assistant. You answer questions using "
        "ONLY the provided evidence, which spans MANY meetings across the workspace. "
        "You never use outside knowledge and never invent facts, names, dates or "
        "numbers. Cite the numbered evidence you used in `citations`. If the answer "
        "is not in the evidence, set \"found\": false and set \"answer\" to exactly: "
        "\"I couldn't find that in your meetings.\" Respond with ONE valid JSON "
        "object only, matching the schema."
    ),
    template=(
        "Schema:\n{schema}\n\n"
        "Evidence from across the organization's meetings (cite by number):\n{context}\n\n"
        "{history}Question: {question}"
    ),
))

BRIEF_VERSION = "v1"

EXECUTIVE_BRIEF = register_prompt(Prompt(
    name="executive_brief",
    version=BRIEF_VERSION,
    system=(
        "You write concise executive briefings for leadership from workspace "
        "activity data. Use ONLY the provided figures and items — never invent. "
        "Return short, skimmable Markdown (headings + bullets), no code fences."
    ),
    template="Write a {period} executive brief from this workspace data:\n\n{context}",
))

CONSENSUS_VERSION = "v1"

CONSENSUS_SCHEMA = (
    '{"current_position": "the stance the org currently holds", '
    '"category": "technical|business|timeline|risk|architecture|security|customer|performance|compliance|general", '
    '"support_count": 3, "opposition_count": 1, "confidence": 88, '
    '"resolved": true, "reason": "why this is the current position, citing the evidence"}'
)

KNOWLEDGE_CONSENSUS = register_prompt(Prompt(
    name="knowledge_consensus",
    version=CONSENSUS_VERSION,
    system=(
        "You analyse a set of decisions made across DIFFERENT meetings about the "
        "SAME topic and determine the organization's CURRENT consensus. Use ONLY "
        "the provided decisions — never invent facts. Weigh more RECENT and "
        "non-reversed decisions more heavily. Count how many decisions SUPPORT vs "
        "OPPOSE the current position. Classify the topic's contradiction category. "
        "If the decisions genuinely agree (or a later one clearly settled it), set "
        "\"resolved\": true and give the reason. Respond with ONE valid JSON object "
        "only, matching the schema. Counts must not exceed the number of decisions."
    ),
    template=(
        "Schema:\n{schema}\n\n"
        "Topic: {topic}\n\n"
        "Decisions on this topic, oldest first (each with its meeting + date + status):\n"
        "{decisions}\n\n"
        "Determine the current consensus."
    ),
))

NL_FILTER_VERSION = "v1"

NL_FILTER_SCHEMA = (
    '{"entity_type": "meeting|segment|summary|decision|task|issue|risk|report|"'
    ' (empty for any), "keywords": "free-text search terms", '
    '"date_from": "YYYY-MM-DD or empty", "date_to": "YYYY-MM-DD or empty", '
    '"category": "e.g. customer, security (empty if none)"}'
)

NL_FILTER = register_prompt(Prompt(
    name="nl_filter",
    version=NL_FILTER_VERSION,
    system=(
        "You translate a user's natural-language request about their meeting "
        "workspace into a STRUCTURED filter. Extract the entity type they want, "
        "free-text keywords, an optional date range, and an optional category. "
        "Use ONLY what the request implies — never invent filters. Respond with "
        "ONE valid JSON object only, matching the schema."
    ),
    template="Schema:\n{schema}\n\nToday is {today}.\nRequest: {query}",
))

DIGEST_VERSION = "v1"

DAILY_DIGEST = register_prompt(Prompt(
    name="daily_digest",
    system=(
        "You write a short, friendly daily digest for a user from their workspace "
        "activity. Use ONLY the provided data. Return brief Markdown."
    ),
    version=DIGEST_VERSION,
    template="Write a daily digest for {name} from this data:\n\n{context}",
))
