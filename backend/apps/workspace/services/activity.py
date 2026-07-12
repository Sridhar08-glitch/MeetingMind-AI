"""Workspace activity feed / audit trail + AI duplicate detection."""
from __future__ import annotations

import re

from apps.workspace.enums import ActivityVerb
from apps.workspace.models import ActivityLog, Task


def log_activity(owner, verb: str, entity, *, summary: str, meeting=None, **metadata) -> ActivityLog:
    return ActivityLog.objects.create(
        owner=owner, verb=verb, summary=summary[:500],
        entity_type=type(entity).__name__.lower() if entity is not None else "",
        entity_id=getattr(entity, "id", None),
        meeting=meeting or getattr(entity, "meeting", None),
        metadata=metadata or {},
    )


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", (text or "").lower()) if len(t) > 2}


def find_duplicate_tasks(owner, title: str, *, exclude_id=None) -> list[dict]:
    """Detect likely-duplicate existing tasks before creating a new one.

    Uses local embedding similarity with a lexical fallback — no external service.
    Returns candidates sorted by score (>= 0.6 considered a likely duplicate).
    """
    qs = Task.objects.filter(owner=owner)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    existing = list(qs.values("id", "title"))
    if not existing or not title.strip():
        return []

    scores: list[tuple[float, dict]] = []
    try:
        from apps.meetings.services.embeddings import cosine, get_embedding_provider

        embedder = get_embedding_provider()
        q = embedder.embed_one(title)
        embs = embedder.embed([e["title"] for e in existing])
        for e, emb in zip(existing, embs):
            scores.append((cosine(q, emb), e))
    except Exception:  # noqa: BLE001 — fall back to lexical Jaccard
        qt = _tokens(title)
        for e in existing:
            et = _tokens(e["title"])
            j = len(qt & et) / max(1, len(qt | et))
            scores.append((j, e))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [
        {"id": str(e["id"]), "title": e["title"], "score": round(s, 3)}
        for s, e in scores if s >= 0.6
    ][:5]


# Re-export for convenience.
CREATED = ActivityVerb.CREATED
