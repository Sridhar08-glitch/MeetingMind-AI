"""Stage registry — stages self-register; the engine discovers them by key.

Adding a new stage requires only defining a :class:`Stage` subclass decorated
with :func:`register_stage`. No engine changes.
"""
from __future__ import annotations

from .base import Stage


class StageRegistry:
    def __init__(self) -> None:
        self._stages: dict[str, type[Stage]] = {}

    def register(self, stage_cls: type[Stage]) -> type[Stage]:
        key = stage_cls.key
        if not key:
            raise ValueError(f"{stage_cls.__name__} must define a non-empty `key`.")
        if key in self._stages and self._stages[key] is not stage_cls:
            raise ValueError(f"Stage key '{key}' is already registered.")
        self._stages[key] = stage_cls
        return stage_cls

    def get(self, key: str) -> Stage:
        """Return a fresh stage instance for ``key``."""
        try:
            return self._stages[key]()
        except KeyError as exc:
            raise KeyError(f"No stage registered for key '{key}'.") from exc

    def has(self, key: str) -> bool:
        return key in self._stages

    def all(self) -> dict[str, type[Stage]]:
        return dict(self._stages)


stage_registry = StageRegistry()


def register_stage(stage_cls: type[Stage]) -> type[Stage]:
    """Class decorator that registers a stage on the default registry."""
    return stage_registry.register(stage_cls)
