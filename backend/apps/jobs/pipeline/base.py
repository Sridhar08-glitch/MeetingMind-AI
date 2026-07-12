"""Stage base classes and results.

A *stage* is an independently executable, retryable, cancellable, idempotent unit
of work. Stages never know about pipelines, ordering, retries, or transport —
the engine owns all of that. A stage just does its job with the
:class:`ProcessingContext` it's handed and returns a :class:`StageResult`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import ProcessingContext


@dataclass
class StageResult:
    ok: bool = True
    skipped: bool = False
    message: str = ""
    data: dict = field(default_factory=dict)


class StageError(Exception):
    """A stage failure. Retryable by default (transient)."""


class NonRetryableStageError(StageError):
    """A permanent failure (e.g. validation) that must NOT be retried."""


class Stage(ABC):
    """Base class for all processing stages.

    Subclasses set ``key`` (unique, used in registry + pipeline definitions) and
    ``name`` (human label), and implement :meth:`run`. Keep :meth:`run`
    idempotent — the engine may re-execute a stage after a resume/retry, and that
    must not corrupt data.
    """

    key: str = ""
    name: str = ""
    max_retries: int = 3
    retryable: bool = True

    @abstractmethod
    def run(self, context: "ProcessingContext") -> StageResult:  # pragma: no cover - interface
        ...

    def should_retry(self, exc: Exception) -> bool:
        """Whether ``exc`` is a transient failure worth retrying."""
        if isinstance(exc, NonRetryableStageError):
            return False
        return self.retryable
