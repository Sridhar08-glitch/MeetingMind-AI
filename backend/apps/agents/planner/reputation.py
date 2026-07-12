"""Agent reputation — a long-term performance profile derived from AgentRun
history. The planner prefers reliable agents. No new storage (reads history)."""
from __future__ import annotations

from django.db.models import Avg

from apps.agents.enums import RunStatus
from apps.agents.models import AgentRun

_NEUTRAL_PRIOR = 62.0   # reputation for an agent with no history yet


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def agent_reputation(owner, agent_name: str) -> dict:
    runs = AgentRun.objects.filter(owner=owner, agent_name=agent_name)
    total = runs.count()
    if not total:
        return {"agent": agent_name, "runs": 0, "reliability": _NEUTRAL_PRIOR,
                "success_rate": None, "avg_quality": None, "avg_confidence": None,
                "avg_latency_ms": None}
    succeeded = runs.filter(status=RunStatus.SUCCEEDED).count()
    val_fail = runs.filter(validation_ok=False).count()
    agg = runs.aggregate(q=Avg("quality_score"), c=Avg("confidence"), lat=Avg("duration_ms"))
    success_rate = succeeded / total
    reliability = _clamp(
        0.45 * success_rate * 100
        + 0.30 * (agg["q"] or 60)
        + 0.25 * (agg["c"] or 60)
        - 15 * (val_fail / total)
    )
    return {
        "agent": agent_name, "runs": total, "reliability": reliability,
        "success_rate": round(success_rate, 2),
        "avg_quality": round(agg["q"], 1) if agg["q"] else None,
        "avg_confidence": round(agg["c"], 1) if agg["c"] else None,
        "avg_latency_ms": round(agg["lat"]) if agg["lat"] else None,
    }
