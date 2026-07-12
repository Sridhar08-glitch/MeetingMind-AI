"""Universal media import — the MediaProvider abstraction.

A provider's ONLY job is to acquire media and produce a local file. Everything
after that (transcription, translation, AI, Knowledge, Workspace, Executive,
Agents, Planner, Collaboration) is the existing pipeline, entered via
``create_upload()``. Providers must never call any of that themselves.
"""
from __future__ import annotations

from .base import (
    EpisodeInfo,
    MediaFetchResult,
    MediaProvider,
    MediaProviderError,
    MediaSourceInfo,
    ProgressCallback,
)
from .batch import BatchItem, expand as batch_expand
from .guards import assert_public_url
from .registry import (
    all_providers,
    enabled_providers,
    import_available,
    provider_by_id,
    register,
    resolve_provider,
)

__all__ = [
    "EpisodeInfo",
    "MediaFetchResult",
    "MediaProvider",
    "MediaProviderError",
    "MediaSourceInfo",
    "ProgressCallback",
    "BatchItem",
    "batch_expand",
    "assert_public_url",
    "all_providers",
    "enabled_providers",
    "import_available",
    "provider_by_id",
    "register",
    "resolve_provider",
]
