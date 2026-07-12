"""ProcessingContext — the single object every stage receives.

Instead of threading a dozen parameters through each stage, the engine builds one
context carrying the job, its payload, storage, logging, config, the pipeline,
the event bus, a cancellation token, and a mutable ``shared`` bag for passing
data between stages (e.g. a chunk list produced by one stage and consumed by the
next).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from apps.jobs.enums import JobLogLevel
from apps.jobs.events import EventBus
from apps.jobs.models import JobLog

from .cancellation import CancellationToken

if TYPE_CHECKING:
    from apps.common.storage import StorageService
    from apps.jobs.models import BackgroundJob
    from .definitions import PipelineDefinition


@dataclass
class ProcessingContext:
    job: "BackgroundJob"
    payload: dict
    config: dict
    pipeline: "PipelineDefinition"
    storage: "StorageService"
    events: EventBus
    cancellation: CancellationToken
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("meetingmind.processing"))
    shared: dict[str, Any] = field(default_factory=dict)

    # --- inter-stage data ------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self.shared.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.shared[key] = value

    # --- events ----------------------------------------------------------
    def emit(self, event: str, **data) -> None:
        self.events.publish(event, job_id=str(self.job.id), **data)

    # --- structured logging ---------------------------------------------
    def log(
        self,
        message: str,
        *,
        stage: str = "",
        level: str = JobLogLevel.INFO,
        progress: int | None = None,
        duration_ms: int | None = None,
        **metadata,
    ) -> JobLog:
        self.logger.log(
            logging.ERROR if level == JobLogLevel.ERROR else logging.INFO,
            "[job %s%s] %s", self.job.id, f"/{stage}" if stage else "", message,
        )
        return JobLog.objects.create(
            job=self.job, stage=stage, level=level, message=message,
            progress=progress, duration_ms=duration_ms, metadata=metadata or {},
        )
