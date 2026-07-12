"""A tiny versioned prompt registry.

Prompts live here (and in ``definitions.py``), NOT hardcoded inside services.
Each prompt is versioned; services fetch the latest (or a pinned) version and the
version is recorded on every stored AI result for reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    template: str

    def render(self, **kwargs) -> tuple[str, str]:
        """Return (system, user) with the template filled in."""
        return self.system, self.template.format(**kwargs)


class PromptRegistry:
    def __init__(self) -> None:
        # name -> {version -> Prompt}, plus insertion order for "latest".
        self._prompts: dict[str, dict[str, Prompt]] = {}
        self._latest: dict[str, str] = {}

    def register(self, prompt: Prompt) -> Prompt:
        self._prompts.setdefault(prompt.name, {})[prompt.version] = prompt
        self._latest[prompt.name] = prompt.version  # last registered wins
        return prompt

    def get(self, name: str, version: str | None = None) -> Prompt:
        versions = self._prompts.get(name)
        if not versions:
            raise KeyError(f"No prompt registered under '{name}'.")
        v = version or self._latest[name]
        try:
            return versions[v]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' has no version '{v}'.") from exc

    def versions(self, name: str) -> list[str]:
        return sorted(self._prompts.get(name, {}))


prompt_registry = PromptRegistry()


def register_prompt(prompt: Prompt) -> Prompt:
    return prompt_registry.register(prompt)
