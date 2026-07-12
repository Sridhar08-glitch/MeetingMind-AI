"""Shared agent memory — reads EXISTING stores; never duplicates storage.

Agents share the same memory surfaces the rest of the app uses:
  * Workspace/Knowledge memory  → KnowledgeIndexService.stats + ai_insights
  * Project memory              → knowledge.selectors.project_memory
  * Conversation/run memory     → AgentRun history
"""
from __future__ import annotations


class AgentMemory:
    def __init__(self, owner):
        self.owner = owner

    def knowledge_state(self) -> dict:
        from apps.knowledge.services.index import KnowledgeIndexService
        return KnowledgeIndexService().stats(self.owner)

    def workspace_memory(self) -> dict:
        from apps.knowledge.services.insights import ai_insights
        ins = ai_insights(self.owner)
        return {
            "top_topics": [t["label"] for t in ins["top_topics"][:6]],
            "open_risks": len(ins["recurring_risks"]),
            "overdue_tasks": ins["overdue_tasks"]["count"],
            "blocked_tasks": ins["blocked_tasks"]["count"],
        }

    def recent_runs(self, agent_name: str | None = None, n: int = 5) -> list[dict]:
        from apps.agents.models import AgentRun
        qs = AgentRun.objects.filter(owner=self.owner)
        if agent_name:
            qs = qs.filter(agent_name=agent_name)
        return [
            {"agent": r.agent_name, "request": r.request[:120], "answer": r.answer[:200],
             "at": r.created_at}
            for r in qs.order_by("-created_at")[:n]
        ]
