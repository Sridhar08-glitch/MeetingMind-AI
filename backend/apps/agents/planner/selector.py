"""Agent selector — scores candidate agents by relevance × reputation under the
active execution policy, and picks the top N."""
from __future__ import annotations

from apps.agents.framework.registry import agent_registry

from .policies import PolicyConfig
from .reputation import agent_reputation


def select_agents(owner, candidate_agents: list[str], policy: PolicyConfig) -> list[dict]:
    """Return [{agent, selection_score, reason, reputation}] limited to the
    policy's max_agents. Order preserves relevance (intent) then reputation."""
    scored = []
    for i, name in enumerate(dict.fromkeys(candidate_agents)):   # dedupe, keep order
        if not agent_registry.has(name):
            continue
        rep = agent_reputation(owner, name)
        relevance = max(20.0, 100.0 - i * 12)   # earlier (more relevant) → higher
        if policy.prefer == "quality":
            score = 0.5 * relevance + 0.5 * rep["reliability"]
        elif policy.prefer == "latency":
            lat = rep["avg_latency_ms"] or 8000
            latency_bonus = max(0.0, 100.0 - lat / 200)   # faster → higher
            score = 0.55 * relevance + 0.2 * rep["reliability"] + 0.25 * latency_bonus
        else:  # balanced
            score = 0.6 * relevance + 0.4 * rep["reliability"]
        scored.append({
            "agent": name, "selection_score": round(score, 1),
            "reason": f"relevance {round(relevance)}, reliability {rep['reliability']}",
            "reputation": rep,
        })
    # Keep intent order for the top slice, but ensure we never drop the single
    # most-relevant agent. Sort by score for the ranking within the cap.
    top = scored[:max(1, policy.max_agents)]
    return top
