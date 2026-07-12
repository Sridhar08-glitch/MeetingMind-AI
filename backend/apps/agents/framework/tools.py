"""Tool interface + registry.

A Tool is the ONLY way an agent reaches data. Each tool wraps an already-built
service (Knowledge Hub, Executive Intelligence, Workspace, …), is owner-scoped
via the AgentContext, and returns evidence + provenance so agent answers stay
explainable. Agents never import services or repositories directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Everything a tool/agent needs, owner-scoped. No service handles here —
    tools resolve services themselves, always filtering by ``owner``."""

    owner: Any                       # the authenticated user (tenant boundary)
    request: str = ""                # the user's natural-language ask
    params: dict = field(default_factory=dict)   # project_id, topic, as_of, …
    cache: dict | None = None        # shared tool-result cache (set by the planner; not persisted)


@dataclass
class ToolResult:
    data: Any
    evidence: list[dict] = field(default_factory=list)   # [{type,id,title,source,...}]
    meta: dict = field(default_factory=dict)             # {knowledge_version, ...}
    summary: str = ""                                    # short text for the LLM prompt


class Tool(ABC):
    name: str = ""
    description: str = ""
    capability: str = ""             # required AgentCapability

    @abstractmethod
    def run(self, context: AgentContext, **kwargs) -> ToolResult: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if not tool.name:
            raise ValueError("Tool must define a name.")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"No tool registered under '{name}'.") from exc

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self) -> list[Tool]:
        return list(self._tools.values())


tool_registry = ToolRegistry()


def register_tool(tool: Tool) -> Tool:
    return tool_registry.register(tool)
