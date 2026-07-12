"""Test-only stages + pipelines, registered once for the jobs test suite."""
from __future__ import annotations

from collections import defaultdict

from apps.jobs.pipeline import (
    NonRetryableStageError,
    PipelineDefinition,
    Stage,
    StageError,
    StageResult,
    register_pipeline,
    register_stage,
)

# Counts run() invocations per stage key across a test — used to prove
# idempotency (a resumed job must not re-run a completed stage).
RUN_COUNTS: dict[str, int] = defaultdict(int)


def reset_counts() -> None:
    RUN_COUNTS.clear()


class _Recorder(Stage):
    """Appends its letter to the shared trail and bumps the run counter."""

    def run(self, ctx) -> StageResult:
        RUN_COUNTS[self.key] += 1
        ctx.set("trail", ctx.get("trail", []) + [self.key])
        return StageResult(message=self.key)


@register_stage
class StageA(_Recorder):
    key = "t_a"
    name = "A"


@register_stage
class StageB(_Recorder):
    key = "t_b"
    name = "B"


@register_stage
class StageC(_Recorder):
    key = "t_c"
    name = "C"


@register_stage
class StageD(_Recorder):
    key = "t_d"
    name = "D"


@register_stage
class StageE(_Recorder):
    key = "t_e"
    name = "E"


@register_stage
class FlakyStage(Stage):
    """Fails ``config['flaky_fail_times']`` times, then succeeds (transient)."""

    key = "t_flaky"
    name = "Flaky"
    max_retries = 3

    def __init__(self) -> None:
        self._calls = 0

    def run(self, ctx) -> StageResult:
        RUN_COUNTS[self.key] += 1
        self._calls += 1
        if self._calls <= ctx.config.get("flaky_fail_times", 2):
            raise StageError(f"transient failure #{self._calls}")
        return StageResult(message="recovered")


@register_stage
class FatalStage(Stage):
    key = "t_fatal"
    name = "Fatal"
    retryable = False

    def run(self, ctx) -> StageResult:
        RUN_COUNTS[self.key] += 1
        raise NonRetryableStageError("permanent failure")


@register_stage
class CancelSelfStage(Stage):
    key = "t_cancel"
    name = "CancelSelf"

    def run(self, ctx) -> StageResult:
        ctx.job.request_cancellation()
        ctx.cancellation.check()  # raises JobCancelled
        return StageResult()


# Pipelines --------------------------------------------------------------
register_pipeline(PipelineDefinition("t_linear", ["t_a", "t_b", "t_c"]))
register_pipeline(PipelineDefinition("t_flaky", ["t_a", "t_flaky", "t_c"]))
register_pipeline(PipelineDefinition("t_fatal", ["t_a", "t_fatal", "t_c"]))
register_pipeline(PipelineDefinition("t_cancel", ["t_a", "t_cancel", "t_c"]))
# Diamond: b and c both depend on a; d depends on both; e after d.
register_pipeline(PipelineDefinition(
    "t_branch",
    stages=["t_a", "t_b", "t_c", "t_d", "t_e"],
    dependencies={"t_b": ["t_a"], "t_c": ["t_a"], "t_d": ["t_b", "t_c"], "t_e": ["t_d"]},
))
