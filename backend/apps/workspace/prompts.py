"""Workspace AI prompts (reports + emails), registered in the shared registry."""
from __future__ import annotations

from apps.meetings.prompts.registry import Prompt, register_prompt

REPORT_VERSION = "v1"

# Per-type intent, injected into the single versioned report prompt.
REPORT_INSTRUCTIONS = {
    "daily": "Write a concise daily report of progress, blockers and next steps.",
    "weekly": "Write a weekly report summarizing progress, decisions, risks and upcoming work.",
    "sprint": "Write a sprint report: completed work, in-progress items, blockers, and risks.",
    "executive": "Write a brief executive summary for leadership: outcomes, decisions, risks, next steps. Non-technical.",
    "technical": "Write a technical report: technical decisions, issues, technical debt and risks.",
    "customer": "Write a customer-facing status report: progress and next steps, no internal jargon.",
    "progress": "Write a progress report against goals and deadlines.",
    "email_follow_up": "Write a follow-up email listing action items, owners and deadlines. Friendly, professional.",
    "email_recap": "Write a meeting recap email: key points, decisions and next steps.",
    "email_status": "Write a status update email covering progress, blockers and next steps.",
    "email_client": "Write a client update email: progress and next steps, warm and professional.",
    "email_internal": "Write an internal update email for the team: what happened and what's next.",
}

WORKSPACE_REPORT = register_prompt(Prompt(
    name="workspace_report",
    version=REPORT_VERSION,
    system=(
        "You are an assistant that writes clear, well-structured Markdown reports and "
        "emails for a meeting productivity tool. Use ONLY the provided context — never "
        "invent facts, names, dates or numbers. If a section has no data, omit it. "
        "Return Markdown only (no code fences)."
    ),
    template="{instructions}\n\nContext:\n{context}",
))


def report_instruction(report_type: str) -> str:
    return REPORT_INSTRUCTIONS.get(report_type, "Write a concise, well-structured report.")
