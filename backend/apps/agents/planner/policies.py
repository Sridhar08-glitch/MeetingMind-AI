"""Execution policies — tune orchestration WITHOUT changing agents."""
from __future__ import annotations

from dataclasses import dataclass

from apps.agents.enums import ExecutionPolicy


@dataclass(frozen=True)
class PolicyConfig:
    max_agents: int
    prefer: str          # "latency" | "quality" | "balanced"
    merge_llm: bool      # use the LLM to synthesize the merged answer
    parallel: bool
    agent_timeout_s: float


POLICIES: dict[str, PolicyConfig] = {
    ExecutionPolicy.FAST:            PolicyConfig(max_agents=2, prefer="latency", merge_llm=False, parallel=True, agent_timeout_s=25),
    ExecutionPolicy.LOWEST_LATENCY:  PolicyConfig(max_agents=2, prefer="latency", merge_llm=False, parallel=True, agent_timeout_s=20),
    ExecutionPolicy.BALANCED:        PolicyConfig(max_agents=3, prefer="balanced", merge_llm=True, parallel=True, agent_timeout_s=40),
    ExecutionPolicy.HIGHEST_QUALITY: PolicyConfig(max_agents=5, prefer="quality", merge_llm=True, parallel=True, agent_timeout_s=60),
    ExecutionPolicy.RESEARCH:        PolicyConfig(max_agents=6, prefer="quality", merge_llm=True, parallel=True, agent_timeout_s=90),
}


def get_policy(name: str) -> PolicyConfig:
    return POLICIES.get(name, POLICIES[ExecutionPolicy.BALANCED])
