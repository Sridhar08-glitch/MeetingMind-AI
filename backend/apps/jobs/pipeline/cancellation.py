"""Cooperative cancellation for long-running pipelines."""
from __future__ import annotations


class JobCancelled(Exception):
    """Raised inside a stage/engine when the job has been asked to cancel."""


class CancellationToken:
    """Re-reads the job's status so a stage sees a cancel issued elsewhere.

    Stages doing long work should call :meth:`check` periodically (e.g. between
    chunks) so cancellation is timely and graceful — no killing mid-write.
    """

    def __init__(self, job) -> None:
        self._job = job

    @property
    def is_cancelled(self) -> bool:
        return self._job.is_cancellation_requested()

    def check(self) -> None:
        if self.is_cancelled:
            raise JobCancelled()
