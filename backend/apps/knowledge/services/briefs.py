"""Executive AI Brief + Daily AI Digest.

Both build a compact, factual context from stored workspace data and ask the
local LLM to render skimmable Markdown. If the LLM is unavailable, a
deterministic Markdown fallback is produced from the same data — the feature
stays fully usable offline (FOSS policy).
"""
from __future__ import annotations

import json
import logging

from django.utils import timezone

from apps.knowledge.prompts import BRIEF_VERSION, DIGEST_VERSION
from apps.knowledge.services.insights import ai_insights, cross_project_comparison, recommendations
from apps.meetings.models import Meeting
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.workspace.models import Decision, Risk, Task

logger = logging.getLogger("meetingmind.ai")
_PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def _window(owner, days):
    since = timezone.now() - timezone.timedelta(days=days)
    return {
        "since": since,
        "meetings": Meeting.objects.filter(owner=owner, created_at__gte=since),
        "tasks": Task.objects.filter(owner=owner, created_at__gte=since),
        "decisions": Decision.objects.filter(owner=owner, created_at__gte=since),
        "risks": Risk.objects.filter(owner=owner, created_at__gte=since),
    }


def _brief_context(owner, period, days):
    w = _window(owner, days)
    ins = ai_insights(owner)
    ctx = {
        "period": period,
        "window_days": days,
        "new_meetings": w["meetings"].count(),
        "new_tasks": w["tasks"].count(),
        "new_decisions": w["decisions"].count(),
        "new_risks": w["risks"].count(),
        "overdue_tasks": ins["overdue_tasks"]["count"],
        "blocked_tasks": ins["blocked_tasks"]["count"],
        "top_topics": [t["label"] for t in ins["top_topics"][:6]],
        "recurring_risks": [r["topic"] for r in ins["recurring_risks"][:5]],
        "projects": cross_project_comparison(owner)["projects"][:8],
        "recommendations": [r["title"] for r in recommendations(owner)[:5]],
    }
    return ctx, ins


def _render(prompt_name, **kwargs):
    prompt = prompt_registry.get(prompt_name)
    system, user = prompt.render(**kwargs)
    llm = get_llm_provider()
    resp = llm.generate(user, system=system, json=False)
    return resp.text.strip(), llm


def executive_brief(owner, period: str = "weekly") -> dict:
    period = period if period in _PERIOD_DAYS else "weekly"
    days = _PERIOD_DAYS[period]
    ctx, _ins = _brief_context(owner, period, days)
    context = json.dumps(ctx, indent=2, default=str)
    try:
        text, llm = _render("executive_brief", period=period, context=context)
        provider, model = llm.name, llm.model_name
    except LLMError as exc:
        logger.warning("Executive brief LLM failed (%s) — using fallback", exc.message)
        text, provider, model = _brief_fallback(period, ctx), "fallback", ""
    return {"period": period, "brief": text, "generated_at": timezone.now(),
            "data": ctx, "prompt_version": BRIEF_VERSION, "provider": provider, "model": model}


def daily_digest(owner, name: str = "there") -> dict:
    ctx, _ins = _brief_context(owner, "daily", 1)
    context = json.dumps(ctx, indent=2, default=str)
    try:
        text, llm = _render("daily_digest", name=name, context=context)
        provider, model = llm.name, llm.model_name
    except LLMError as exc:
        logger.warning("Daily digest LLM failed (%s) — using fallback", exc.message)
        text, provider, model = _brief_fallback("daily", ctx), "fallback", ""
    return {"digest": text, "generated_at": timezone.now(), "data": ctx,
            "prompt_version": DIGEST_VERSION, "provider": provider, "model": model}


def _brief_fallback(period, ctx) -> str:
    lines = [f"# {period.title()} Brief", ""]
    lines.append(f"- New meetings: {ctx['new_meetings']}")
    lines.append(f"- New tasks: {ctx['new_tasks']} (overdue: {ctx['overdue_tasks']}, blocked: {ctx['blocked_tasks']})")
    lines.append(f"- New decisions: {ctx['new_decisions']} · New risks: {ctx['new_risks']}")
    if ctx["top_topics"]:
        lines += ["", "## Top topics", *[f"- {t}" for t in ctx["top_topics"]]]
    if ctx["recommendations"]:
        lines += ["", "## Recommendations", *[f"- {r}" for r in ctx["recommendations"]]]
    return "\n".join(lines)
