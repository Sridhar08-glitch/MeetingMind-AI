"""Agent permission engine.

Two guarantees:
  1. An agent may only invoke tools declared in its profile (capability gate).
  2. Every tool runs owner-scoped via the AgentContext — the underlying services
     already filter by owner, so there is no cross-workspace/knowledge leakage.
"""
from __future__ import annotations

from .registry import AgentProfile
from .tools import AgentContext, Tool


class PermissionDenied(Exception):
    pass


class AgentPermissionEngine:
    def can_use_tool(self, profile: AgentProfile, tool_name: str) -> bool:
        return tool_name in profile.tools

    def check_tool(self, context: AgentContext, profile: AgentProfile, tool: Tool) -> None:
        if not self.can_use_tool(profile, tool.name):
            raise PermissionDenied(
                f"Agent '{profile.name}' is not permitted to use tool '{tool.name}'."
            )
        if context.owner is None or not getattr(context.owner, "is_authenticated", False):
            raise PermissionDenied("Agent context has no authenticated owner.")


permission_engine = AgentPermissionEngine()
