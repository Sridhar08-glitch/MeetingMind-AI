"""Pipeline definitions + registry.

A pipeline is a *named* set of stage keys plus an optional dependency graph.
Processing order is never hardcoded in the engine — it's derived by topologically
sorting the graph, which supports linear flows *and* branching (e.g. keywords and
action-items both depend on summary, and finalize depends on both).

Defining a new pipeline (OCR, PDF, email, video…) is pure data — no engine change.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineDefinition:
    name: str
    stages: list[str]
    # stage_key -> list of prerequisite stage keys (defaults to none).
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    description: str = ""

    def ordered(self) -> list[str]:
        """Return stage keys in a valid execution order (Kahn topological sort).

        Ties are broken by the order stages were declared, so a linear pipeline
        with no explicit dependencies runs exactly as written.
        """
        indegree: dict[str, int] = {s: 0 for s in self.stages}
        adjacency: dict[str, list[str]] = {s: [] for s in self.stages}
        for stage, deps in self.dependencies.items():
            for dep in deps:
                if dep not in indegree:
                    raise ValueError(f"Stage '{stage}' depends on unknown stage '{dep}'.")
                adjacency[dep].append(stage)
                indegree[stage] += 1

        # Ready set preserves declaration order for deterministic output.
        ready = [s for s in self.stages if indegree[s] == 0]
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for nxt in adjacency[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    # Insert keeping declaration order.
                    ready.append(nxt)
                    ready.sort(key=self.stages.index)
        if len(order) != len(self.stages):
            raise ValueError(f"Pipeline '{self.name}' has a dependency cycle.")
        return order


class PipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}

    def register(self, definition: PipelineDefinition) -> PipelineDefinition:
        # Validate the graph eagerly so a bad pipeline fails at import, not run time.
        definition.ordered()
        self._pipelines[definition.name] = definition
        return definition

    def get(self, name: str) -> PipelineDefinition:
        try:
            return self._pipelines[name]
        except KeyError as exc:
            raise KeyError(f"No pipeline registered as '{name}'.") from exc

    def has(self, name: str) -> bool:
        return name in self._pipelines

    def all(self) -> dict[str, PipelineDefinition]:
        return dict(self._pipelines)


pipeline_registry = PipelineRegistry()


def register_pipeline(definition: PipelineDefinition) -> PipelineDefinition:
    return pipeline_registry.register(definition)
