"""Knowledge Reliability Score (Phase 11B, feature #1).

Splits a single opaque confidence number into explainable components so the AI
is transparent about *why* it trusts a piece of knowledge:

    Overall • Evidence Strength • Agreement • Recency • Coverage • Source Quality

All deterministic (no LLM) and evidence-based — computed from the current
knowledge index + any recorded conflict/consensus for the topic. Owner-scoped.
"""
from __future__ import annotations

import math

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.knowledge.models import (
    ConflictStatus,
    KnowledgeConflict,
    KnowledgeConsensus,
    KnowledgeItem,
)

# Structured, human-reviewed knowledge is a stronger source than a raw
# transcript line — used for the Source Quality component.
_HIGH_QUALITY = {"decision", "summary", "report", "meeting", "project"}
_COMPONENT_WEIGHTS = {
    "evidence_strength": 0.30, "agreement": 0.25, "recency": 0.15,
    "coverage": 0.15, "source_quality": 0.15,
}


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def knowledge_reliability(owner, topic: str) -> dict:
    topic = (topic or "").strip()
    items = (KnowledgeItem.objects.current().filter(owner=owner)
             .filter(Q(title__icontains=topic) | Q(text__icontains=topic)) if topic
             else KnowledgeItem.objects.current().filter(owner=owner))

    total = items.count()
    if not total:
        return {"topic": topic, "overall": 0.0, "components": {}, "evidence": {}, "found": False}

    by_type: dict[str, int] = {}
    for row in items.values("entity_type").annotate(n=Count("id")):
        by_type[row["entity_type"]] = row["n"]

    meetings = items.exclude(meeting=None).values("meeting").distinct().count()
    latest = items.aggregate(m=Max("occurred_at"))["m"]

    # Evidence Strength — more corroborating records → stronger (log-scaled).
    evidence_strength = 50 + 18 * math.log2(1 + total)

    # Recency — gentle 180-day half-life decay from the newest evidence.
    recency = 100.0
    if latest is not None:
        age_days = max(0.0, (timezone.now() - latest).total_seconds() / 86400)
        recency = 100 * (0.5 ** (age_days / 180))

    # Coverage — diversity of entity types + breadth of meetings.
    type_diversity = len(by_type) / 7.0                      # 7 meaningful types
    meeting_breadth = min(1.0, meetings / 5.0)
    coverage = 100 * (0.5 * type_diversity + 0.5 * meeting_breadth)

    # Source Quality — share of evidence from structured, reviewed sources.
    hq = sum(n for t, n in by_type.items() if t in _HIGH_QUALITY)
    source_quality = 100 * (hq / total)

    # Agreement — start high; a recorded open conflict / opposing decisions lower it.
    agreement = 95.0
    consensus = KnowledgeConsensus.objects.filter(owner=owner, topic__iexact=topic).first() if topic else None
    if consensus and (consensus.support_count + consensus.opposition_count) > 0:
        agreement = 100 * consensus.support_count / (consensus.support_count + consensus.opposition_count)
    elif topic and KnowledgeConflict.objects.filter(
            owner=owner, topic__iexact=topic, status=ConflictStatus.OPEN).exists():
        agreement = 55.0

    components = {
        "evidence_strength": _clamp(evidence_strength),
        "agreement": _clamp(agreement),
        "recency": _clamp(recency),
        "coverage": _clamp(coverage),
        "source_quality": _clamp(source_quality),
    }
    overall = _clamp(sum(components[k] * w for k, w in _COMPONENT_WEIGHTS.items()))

    return {
        "topic": topic,
        "found": True,
        "overall": overall,
        "components": components,
        "evidence": {
            "total_records": total,
            "meetings": meetings,
            "decisions": by_type.get("decision", 0),
            "tasks": by_type.get("task", 0),
            "risks": by_type.get("risk", 0),
            "reports": by_type.get("report", 0),
            "segments": by_type.get("segment", 0),
            "by_entity_type": by_type,
        },
        "last_evidence_at": latest,
    }
