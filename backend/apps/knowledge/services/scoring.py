"""Organizational Memory Score (Phase 11B, feature #5).

A per-project executive metric with explainable sub-scores:

    Knowledge Quality • Decision Stability • Documentation •
    AI Confidence • Trend Stability → Overall

All evidence-based (computed from the index, decisions, reports, and cached
consensus) — no LLM, no invented numbers. Owner-scoped.
"""
from __future__ import annotations

from django.db.models import Avg, Q

from apps.knowledge.models import KnowledgeConsensus, KnowledgeItem
from apps.meetings.models import AIAnalysis, Meeting
from apps.workspace.models import Decision, Project, Report, Risk, Task

_WEIGHTS = {
    "knowledge_quality": 0.25, "decision_stability": 0.20, "documentation": 0.20,
    "ai_confidence": 0.20, "trend_stability": 0.15,
}


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def _avg_ai_confidence(owner, in_project) -> float | None:
    vals = []
    for model, field in ((Task, "confidence_score"), (Decision, "confidence_score"),
                         (Risk, "confidence_score")):
        agg = (model.objects.filter(owner=owner).filter(in_project)
               .exclude(**{f"{field}__isnull": True}).aggregate(a=Avg(field))["a"])
        if agg is not None:
            vals.append(agg)
    return sum(vals) / len(vals) if vals else None


def project_memory_score(owner, project: Project) -> dict:
    in_project = Q(project=project) | Q(meeting__project=project)
    meetings = Meeting.objects.filter(owner=owner, project=project, is_deleted=False)
    n_meetings = meetings.count()

    items = KnowledgeItem.objects.current().filter(owner=owner, project=project)

    # Knowledge Quality — avg item confidence, blended with entity-type breadth.
    avg_conf = items.aggregate(a=Avg("confidence"))["a"]
    type_breadth = min(1.0, items.values("entity_type").distinct().count() / 6.0)
    knowledge_quality = (0.7 * (avg_conf if avg_conf is not None else 0.0)
                         + 0.3 * 100 * type_breadth) if items.exists() else 0.0

    # Decision Stability — fewer reversed/superseded decisions ⇒ more stable.
    decisions = Decision.objects.filter(owner=owner).filter(in_project)
    n_dec = decisions.count()
    reversed_n = decisions.filter(status="reversed").count()
    superseded_n = items.filter(entity_type="decision", version__gt=1).count()
    decision_stability = (100 * (1 - min(1.0, (reversed_n + superseded_n) / n_dec))
                          if n_dec else 100.0)

    # Documentation — do meetings have summaries + reports?
    summaries = (AIAnalysis.objects.filter(meeting__owner=owner, meeting__project=project,
                                           is_current=True)
                 .values("meeting").distinct().count())
    reports = Report.objects.filter(owner=owner).filter(in_project).count()
    documentation = (100 * min(1.0, (summaries + reports) / n_meetings)) if n_meetings else 0.0

    # AI Confidence — avg confidence of AI-sourced records.
    ai_conf = _avg_ai_confidence(owner, in_project)
    ai_confidence = ai_conf if ai_conf is not None else 0.0

    # Trend Stability — avg stability of consensus on this project's topics.
    meeting_ids = {str(m) for m in meetings.values_list("id", flat=True)}
    stabilities = [
        c.stability_score for c in KnowledgeConsensus.objects.filter(owner=owner)
        if meeting_ids & set((c.evidence or {}).get("meeting_ids", []))
    ]
    trend_stability = sum(stabilities) / len(stabilities) if stabilities else 100.0

    components = {
        "knowledge_quality": _clamp(knowledge_quality),
        "decision_stability": _clamp(decision_stability),
        "documentation": _clamp(documentation),
        "ai_confidence": _clamp(ai_confidence),
        "trend_stability": _clamp(trend_stability),
    }
    overall = _clamp(sum(components[k] * w for k, w in _WEIGHTS.items()))
    return {
        "project_id": str(project.id), "name": project.name, "status": project.status,
        "overall": overall, "components": components,
        "signals": {"meetings": n_meetings, "decisions": n_dec,
                    "reversed_decisions": reversed_n, "superseded_decisions": superseded_n,
                    "reports": reports, "summaries": summaries},
    }


def organizational_memory_scores(owner) -> dict:
    rows = [project_memory_score(owner, p) for p in Project.objects.filter(owner=owner)]
    rows.sort(key=lambda r: -r["overall"])
    workspace_overall = round(sum(r["overall"] for r in rows) / len(rows), 1) if rows else 0.0
    return {"workspace_overall": workspace_overall, "project_count": len(rows), "projects": rows}
