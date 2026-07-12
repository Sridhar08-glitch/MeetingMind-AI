"""Versioning primitives for the event-sourced knowledge index (Phase 11A).

* :func:`register_embedding_version` — record which local embedding model + dims
  produced vectors, so future model swaps stay auditable.
* :func:`bump_knowledge_version` — advance the per-owner monotonic knowledge
  version (``v28``) and snapshot the workspace counts at that point.
* :func:`emit_event` — append an immutable :class:`KnowledgeEvent`.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.knowledge.models import (
    EmbeddingVersion,
    KnowledgeEvent,
    KnowledgeItem,
    KnowledgeVersion,
)


def register_embedding_version(embedder, *, dimensions: int | None = None) -> EmbeddingVersion:
    """Get-or-create the EmbeddingVersion row for a provider's current model."""
    provider = getattr(embedder, "name", "") or "unknown"
    model = getattr(embedder, "model_name", "") or "unknown"
    ev = EmbeddingVersion.objects.filter(provider=provider, model=model).order_by("-created_at").first()
    if ev and (dimensions is None or ev.dimensions == dimensions):
        return ev
    ev, _ = EmbeddingVersion.objects.get_or_create(
        provider=provider, model=model, dimensions=dimensions or 0,
        defaults={"status": EmbeddingVersion.STATUS_ACTIVE},
    )
    return ev


def _snapshot_counts(owner) -> dict:
    # Local imports avoid an app-loading cycle (workspace ↔ knowledge).
    from apps.meetings.models import Meeting
    from apps.workspace.models import Decision, Risk, Task

    return {
        "meetings": Meeting.objects.filter(owner=owner, is_deleted=False).count(),
        "projects": (KnowledgeItem.objects.current().filter(owner=owner)
                     .exclude(project=None).values("project").distinct().count()),
        "tasks": Task.objects.filter(owner=owner).count(),
        "decisions": Decision.objects.filter(owner=owner).count(),
        "risks": Risk.objects.filter(owner=owner).count(),
        "items": KnowledgeItem.objects.current().filter(owner=owner).count(),
    }


def bump_knowledge_version(owner, *, trigger: str = "", reason: str = "",
                           embedding_version: EmbeddingVersion | None = None) -> KnowledgeVersion:
    """Advance the owner's monotonic knowledge version and snapshot counts.

    The counts snapshot reflects state AFTER the caller's index write when this
    is invoked at the end of a re-index; callers may also refresh counts.
    """
    with transaction.atomic():
        last = (KnowledgeVersion.objects.select_for_update()
                .filter(owner=owner).aggregate(m=Max("version"))["m"] or 0)
        kv = KnowledgeVersion.objects.create(
            owner=owner, version=last + 1, indexed_at=timezone.now(),
            trigger=trigger[:32], reason=reason, embedding_version=embedding_version,
            **_snapshot_counts(owner),
        )
    return kv


def refresh_counts(kv: KnowledgeVersion) -> KnowledgeVersion:
    """Recompute + persist the snapshot counts on an existing version row."""
    counts = _snapshot_counts(kv.owner)
    for k, v in counts.items():
        setattr(kv, k, v)
    kv.save(update_fields=[*counts.keys(), "updated_at"])
    return kv


def current_version(owner) -> int:
    return KnowledgeVersion.objects.filter(owner=owner).aggregate(m=Max("version"))["m"] or 0


def emit_event(*, owner, item: KnowledgeItem | None, entity_type: str, entity_id,
               event_type: str, version: int | None = None,
               supersedes_version: int | None = None, knowledge_version: int = 0,
               change_source: str = "", change_reason: str = "",
               changed_by=None, meeting=None, metadata: dict | None = None) -> KnowledgeEvent:
    """Append an immutable knowledge-evolution event."""
    return KnowledgeEvent.objects.create(
        owner=owner, item=item, entity_type=entity_type, entity_id=entity_id,
        meeting=meeting, event_type=event_type, version=version,
        supersedes_version=supersedes_version, knowledge_version=knowledge_version,
        change_source=change_source, change_reason=change_reason,
        changed_by=changed_by, metadata=metadata or {},
    )
