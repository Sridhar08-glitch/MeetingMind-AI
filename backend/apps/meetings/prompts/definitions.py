"""Registered prompt templates (versioned).

A single comprehensive prompt (``meeting_analysis``) asks the model to produce
ALL artifacts — executive/detailed/bullet summaries, meeting minutes, action
items, decisions, risks, follow-ups, deadlines and keywords — in ONE structured
JSON response (one inference: faster, cheaper, and internally consistent).

A ``merge_analysis`` prompt reduces per-chunk summaries for very long meetings.
"""
from __future__ import annotations

from .registry import Prompt, register_prompt

# Bump the version when a template changes; it is stored on every AI result.
ANALYSIS_VERSION = "v3"

_SCHEMA = """{
  "executive_summary": "2-3 sentence high-level summary of the meeting",
  "detailed_summary": "one or two paragraph narrative summary",
  "bullet_summary": ["concise bullet point", "..."],
  "meeting_minutes": "structured minutes as short numbered lines",
  "action_items": [{"task": "what must be done", "owner": "name or empty string", "priority": "low|medium|high", "due_date": "text or empty string", "status": "open"}],
  "decisions": [{"decision": "what was decided", "reason": "why", "participants": ["names"]}],
  "risks": [{"risk": "risk/concern/blocker", "severity": "low|medium|high", "mitigation": "text or empty"}],
  "issues": [{"title": "a bug, problem, technical debt, customer, security or performance issue raised", "type": "bug|problem|tech_debt|customer|security|performance", "severity": "low|medium|high|critical", "description": "text or empty"}],
  "follow_ups": [{"item": "follow-up action or pending question", "owner": "name or empty"}],
  "deadlines": [{"item": "what is due", "date": "when (text)"}],
  "keywords": {"topics": ["..."], "technologies": ["..."], "people": ["..."], "companies": ["..."], "phrases": ["important phrases"]}
}"""

MEETING_ANALYSIS = register_prompt(Prompt(
    name="meeting_analysis",
    version=ANALYSIS_VERSION,
    system=(
        "You are an expert meeting analyst. You read a meeting transcript and "
        "extract structured insights. You ALWAYS respond with a single valid JSON "
        "object and nothing else — no prose, no markdown fences. Use empty arrays "
        "or empty strings when information is not present. Never invent facts that "
        "are not supported by the transcript."
    ),
    template=(
        "Analyze the following meeting transcript and return a single JSON object "
        "matching EXACTLY this schema (same keys, same types):\n\n{schema}\n\n"
        "Write in a {style} tone. {language_instruction}Transcript:\n\"\"\"\n{transcript}\n\"\"\""
    ),
))

MERGE_ANALYSIS = register_prompt(Prompt(
    name="merge_analysis",
    version=ANALYSIS_VERSION,
    system=(
        "You merge partial analyses of consecutive chunks of one long meeting into "
        "a single coherent analysis. Respond with ONE valid JSON object only, using "
        "the same schema. Deduplicate and consolidate; do not invent facts."
    ),
    template=(
        "Here are partial JSON analyses of consecutive parts of the same meeting. "
        "Merge them into one JSON object matching this schema:\n\n{schema}\n\n"
        "Partial analyses:\n{partials}"
    ),
))


def analysis_schema() -> str:
    return _SCHEMA


# --- Translation (Phase 13) -------------------------------------------------
TRANSLATION_VERSION = "v1"

TRANSLATION = register_prompt(Prompt(
    name="translation",
    version=TRANSLATION_VERSION,
    system=(
        "You are a professional translator. You translate text accurately into the "
        "requested language, preserving meaning, names, numbers and tone. You output "
        "ONLY a single valid JSON object and nothing else — no prose, no fences."
    ),
    template=(
        "Translate each of the following numbered lines into {target_language}. "
        "Return a JSON object EXACTLY like "
        "{{\"translations\": [\"translation of line 1\", \"translation of line 2\"]}} "
        "with the SAME number of items, in the SAME order. Do not add, drop, merge or "
        "split lines.\n\nLines:\n{lines}"
    ),
))


# --- Speaker naming (Phase 15) — SUGGEST names only; never auto-apply --------
SPEAKER_NAMING_VERSION = "v1"

SPEAKER_NAMING = register_prompt(Prompt(
    name="speaker_naming",
    version=SPEAKER_NAMING_VERSION,
    system=(
        "You identify speakers in a meeting transcript. You may ONLY infer a real "
        "name when it is clearly supported by the transcript — a self-introduction "
        "(\"Hi, I'm Alice\"), someone being addressed by name, or an unambiguous "
        "reference. NEVER guess from topic or role. If a speaker's name is not "
        "clearly stated, omit them. Output ONLY a single valid JSON object, no prose."
    ),
    template=(
        "For each speaker below, return their real name ONLY if the transcript "
        "clearly supports it. Return a JSON object EXACTLY like "
        "{{\"speakers\": [{{\"label\": \"Speaker 1\", \"name\": \"Alice\", "
        "\"confidence\": 92, \"evidence\": \"said 'I'm Alice'\"}}]}} — confidence 0-100, "
        "and INCLUDE ONLY speakers whose name is supported (omit unknowns).\n\n"
        "Speaker-labeled transcript:\n\"\"\"\n{transcript}\n\"\"\""
    ),
))


# --- Meeting chat (Phase 8) -------------------------------------------------
CHAT_VERSION = "v1"

CHAT_SCHEMA = """{
  "answer": "your answer, grounded ONLY in the provided context",
  "citations": [1, 2],
  "found": true
}"""

MEETING_CHAT = register_prompt(Prompt(
    name="meeting_chat",
    version=CHAT_VERSION,
    system=(
        "You are an AI meeting assistant. You answer questions about ONE meeting "
        "using ONLY the provided context (transcript excerpts, summary, action "
        "items, decisions). You never use outside knowledge and never invent "
        "facts. Cite the numbered transcript excerpts you used in `citations`. If "
        "the answer is not in the context, set \"found\": false and set \"answer\" "
        "to exactly: \"I couldn't find that information in this meeting.\" "
        "Respond with ONE valid JSON object only, matching the schema."
    ),
    template=(
        "Schema:\n{schema}\n\n"
        "Meeting: {title}\n{summary}\n\n"
        "Numbered transcript excerpts (cite these by number):\n{context}\n\n"
        "{history}"
        "Question: {question}"
    ),
))


def chat_schema() -> str:
    return CHAT_SCHEMA
