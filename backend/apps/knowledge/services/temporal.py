"""Time-Travel & evolution read-side (Phase 11A).

Read-only, owner-scoped queries over the append-only knowledge history:
  * :func:`time_travel_stats` — what the knowledge base looked like "as of" a date
  * :func:`topic_timeline` — watch a topic evolve across time buckets (feature #5)
  * :func:`entity_history` — the full version chain + events for one entity
  * :func:`decision_evolution` — an entity history specialised for decisions (#6)
  * :func:`knowledge_events` — the raw immutable audit feed
"""
from __future__ import annotations

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.knowledge.models import (
    KnowledgeEntityType,
    KnowledgeEvent,
    KnowledgeItem,
    KnowledgeVersion,
)


def _version_at(owner, when) -> int:
    kv = (KnowledgeVersion.objects.filter(owner=owner, indexed_at__lte=when)
          .order_by("-version").first())
    return kv.version if kv else 0


def time_travel_stats(owner, when) -> dict:
    """Snapshot of the knowledge base valid at ``when`` ("what did we know then?")."""
    qs = KnowledgeItem.objects.as_of(when).filter(owner=owner)
    by_type = {row["entity_type"]: row["n"]
               for row in qs.values("entity_type").annotate(n=Count("id"))}
    return {
        "as_of": when,
        "knowledge_version": _version_at(owner, when),
        "items": qs.count(),
        "meetings": qs.exclude(meeting=None).values("meeting").distinct().count(),
        "by_entity_type": by_type,
    }


def _match(qs, topic: str):
    return qs.filter(Q(title__icontains=topic) | Q(text__icontains=topic)) if topic else qs


def topic_timeline(owner, topic: str, *, entity_type: str | None = None, limit: int = 60) -> dict:
    """How a topic evolved over time — monthly buckets across ALL versions,
    plus the discrete change events that touched it (feature #5)."""
    items = KnowledgeItem.objects.filter(owner=owner)  # all versions (incl. superseded)
    items = _match(items, topic)
    if entity_type:
        items = items.filter(entity_type=entity_type)

    buckets = (items.annotate(month=TruncMonth("occurred_at"))
               .values("month").annotate(n=Count("id")).order_by("month"))
    periods = [{"period": b["month"], "count": b["n"]} for b in buckets if b["month"]]

    events = (KnowledgeEvent.objects.filter(owner=owner)
              .filter(Q(item__title__icontains=topic) | Q(item__text__icontains=topic))
              .select_related("item").order_by("created_at")[:limit]) if topic else []
    milestones = [
        {"at": e.created_at, "event": e.event_type, "entity_type": e.entity_type,
         "entity_id": str(e.entity_id), "version": e.version,
         "knowledge_version": e.knowledge_version,
         "title": (e.item.title if e.item else "")}
        for e in events
    ]
    return {"topic": topic, "periods": periods, "milestones": milestones,
            "total_mentions": items.count()}


def entity_history(owner, entity_type: str, entity_id) -> dict:
    """Full version chain (v1 → current) + audit events for a single entity."""
    versions = list(
        KnowledgeItem.objects.filter(owner=owner, entity_type=entity_type, entity_id=entity_id)
        .order_by("version")
        .values("id", "version", "title", "text", "valid_from", "valid_to", "recorded_at",
                "is_current", "supersedes_version", "change_source", "change_reason",
                "knowledge_version", "confidence")
    )
    events = list(
        KnowledgeEvent.objects.filter(owner=owner, entity_type=entity_type, entity_id=entity_id)
        .order_by("created_at")
        .values("event_type", "version", "supersedes_version", "knowledge_version",
                "change_source", "change_reason", "created_at")
    )
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "versions": [{**v, "id": str(v["id"])} for v in versions],
        "events": events,
        "current_version": next((v["version"] for v in reversed(versions) if v["is_current"]), None),
    }


def decision_evolution(owner, decision) -> dict:
    """Decision-specific history (#6): the knowledge version chain for this
    decision entity, plus its current workspace-record status."""
    hist = entity_history(owner, KnowledgeEntityType.DECISION, decision.id)
    hist["decision"] = {
        "id": str(decision.id),
        "decision": decision.decision,
        "status": decision.status,
        "decided_at": decision.decided_at,
        "project_id": str(decision.project_id) if decision.project_id else None,
        "meeting_id": str(decision.meeting_id) if decision.meeting_id else None,
    }
    return hist


def knowledge_events(owner, *, entity_type: str | None = None, event_type: str | None = None,
                     limit: int = 100) -> list[dict]:
    """Immutable audit feed of knowledge evolution."""
    qs = KnowledgeEvent.objects.filter(owner=owner).select_related("item")
    if entity_type:
        qs = qs.filter(entity_type=entity_type)
    if event_type:
        qs = qs.filter(event_type=event_type)
    return [
        {"id": str(e.id), "event": e.event_type, "entity_type": e.entity_type,
         "entity_id": str(e.entity_id), "version": e.version,
         "supersedes_version": e.supersedes_version, "knowledge_version": e.knowledge_version,
         "change_source": e.change_source, "change_reason": e.change_reason,
         "title": (e.item.title if e.item else ""), "at": e.created_at}
        for e in qs.order_by("-created_at")[:limit]
    ]
