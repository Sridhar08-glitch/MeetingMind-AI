"""Agent profiles + registry. Agents are DECLARATIVE — a profile names the
capabilities, tools and prompt; the generic BaseAgent executes them. No agent
hardcodes business logic."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    name: str                          # "knowledge_agent"
    title: str                         # "Knowledge Agent"
    role: str                          # one-line role for the prompt
    description: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...]             # tool names this agent may use
    prompt: str = "agent_synthesis"    # prompt name in the shared registry
    model: str = ""                    # optional model override
    agent_class: str = ""              # optional custom BaseAgent subclass path


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> AgentProfile:
        self._agents[profile.name] = profile
        return profile

    def get(self, name: str) -> AgentProfile:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"No agent registered under '{name}'.") from exc

    def has(self, name: str) -> bool:
        return name in self._agents

    def all(self) -> list[AgentProfile]:
        return list(self._agents.values())


agent_registry = AgentRegistry()


def register_agent(profile: AgentProfile) -> AgentProfile:
    return agent_registry.register(profile)
