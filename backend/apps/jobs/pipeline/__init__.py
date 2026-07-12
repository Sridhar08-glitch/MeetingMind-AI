"""Reusable pipeline engine (domain-agnostic)."""
from .base import NonRetryableStageError, Stage, StageError, StageResult
from .cancellation import CancellationToken, JobCancelled
from .context import ProcessingContext
from .definitions import PipelineDefinition, pipeline_registry, register_pipeline
from .engine import PipelineEngine, PipelineOutcome
from .registry import register_stage, stage_registry

__all__ = [
    "Stage", "StageResult", "StageError", "NonRetryableStageError",
    "CancellationToken", "JobCancelled",
    "ProcessingContext",
    "PipelineDefinition", "pipeline_registry", "register_pipeline",
    "PipelineEngine", "PipelineOutcome",
    "register_stage", "stage_registry",
]
