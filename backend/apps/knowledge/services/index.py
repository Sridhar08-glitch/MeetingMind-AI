"""Incremental, append-only knowledge indexing (Phase 11A).

Re-indexing a meeting never deletes history. For each knowledge entity we:
  * leave unchanged rows exactly as they are (idempotent — no churn, no re-embed),
  * SUPERSEDE a changed row (close its valid window) and append a new version,
  * ARCHIVE an entity that no longer exists in the source.
Every mutation emits an immutable KnowledgeEvent and is stamped with the
knowledge version + embedding version it was written under.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.knowledge.models import (
    ChangeSource,
    KnowledgeEntityType,
    KnowledgeEventType,
    KnowledgeItem,
    KnowledgeVersion,
)
from apps.knowledge.services import versioning
from apps.meetings.services.embeddings import get_embedding_provider

logger = logging.getLogger("meetingmind.ai")


@dataclass
class _Item:
    entity_type: str
    entity_id: str
    title: str
    text: str
    speaker: str = ""
    start_time: float | None = None


def _collect(meeting) -> list[_Item]:
    items: list[_Item] = [
        _Item(KnowledgeEntityType.MEETING, str(meeting.id), meeting.title,
              f"{meeting.title}. {meeting.description}".strip()),
    ]
    for seg in meeting.segments.order_by("index"):
        if seg.text.strip():
            items.append(_Item(KnowledgeEntityType.SEGMENT, str(seg.id), seg.text[:80],
                               seg.text, speaker=seg.speaker, start_time=seg.start_time))
    analysis = meeting.analyses.filter(is_current=True).order_by("-version").first()
    if analysis and (analysis.executive_summary or analysis.detailed_summary):
        items.append(_Item(KnowledgeEntityType.SUMMARY, str(analysis.id), "Summary",
                           f"{analysis.executive_summary}\n{analysis.detailed_summary}".strip()))
    for t in meeting.tasks.all():
        items.append(_Item(KnowledgeEntityType.TASK, str(t.id), t.title, f"{t.title}. {t.description}".strip()))
    for d in meeting.decisions.all():
        items.append(_Item(KnowledgeEntityType.DECISION, str(d.id), d.decision[:80],
                           f"{d.decision}. {d.reason}".strip()))
    for r in meeting.risks.all():
        items.append(_Item(KnowledgeEntityType.RISK, str(r.id), r.risk[:80],
                           f"{r.risk}. {r.mitigation}".strip()))
    for i in meeting.issues.all():
        items.append(_Item(KnowledgeEntityType.ISSUE, str(i.id), i.title, f"{i.title}. {i.description}".strip()))
    for rep in meeting.reports.all():
        items.append(_Item(KnowledgeEntityType.REPORT, str(rep.id), rep.title, rep.content[:2000]))
    return items


class KnowledgeIndexService:
    def __init__(self, embedder=None):
        self.embedder = embedder or get_embedding_provider()

    def index_meeting(self, meeting, *, change_source: str = ChangeSource.MEETING_REINDEX,
                      changed_by=None, reason: str = "") -> int:
        """Append-only re-index of a single meeting. Returns rows changed."""
        owner = meeting.owner
        collected = _collect(meeting)
        now = timezone.now()
        workspace = getattr(getattr(meeting, "project", None), "workspace", None)

        # Currently-valid rows for this meeting, keyed by (type, id).
        current = {
            (i.entity_type, str(i.entity_id)): i
            for i in KnowledgeItem.objects.current().filter(owner=owner, meeting=meeting)
        }

        # Diff: what actually changed? Only those get (re-)embedded.
        seen: set[tuple] = set()
        plan: list[tuple[_Item, KnowledgeItem | None]] = []
        for c in collected:
            key = (c.entity_type, str(c.entity_id))
            seen.add(key)
            prev = current.get(key)
            if prev is not None and prev.text == c.text:
                continue  # unchanged — keep the existing current row
            plan.append((c, prev))
        archived = [(key, prev) for key, prev in current.items() if key not in seen]

        if not plan and not archived:
            return 0  # fully idempotent — no version bump, no events

        embeddings = self.embedder.embed([c.text for c, _ in plan]) if plan else []
        dims = len(embeddings[0]) if embeddings else None
        emb_ver = versioning.register_embedding_version(self.embedder, dimensions=dims)

        with transaction.atomic():
            kv = versioning.bump_knowledge_version(
                owner, trigger=str(change_source), embedding_version=emb_ver,
                reason=reason or f"Re-index meeting {meeting.id}",
            )
            changed = 0
            for (c, prev), emb in zip(plan, embeddings):
                prev_version = prev.version if prev else 0
                if prev is not None:
                    prev.is_current = False
                    prev.valid_to = now
                    prev.save(update_fields=["is_current", "valid_to", "updated_at"])
                    versioning.emit_event(
                        owner=owner, item=prev, entity_type=c.entity_type, entity_id=c.entity_id,
                        event_type=KnowledgeEventType.SUPERSEDED, version=prev_version,
                        knowledge_version=kv.version, change_source=change_source,
                        changed_by=changed_by, meeting=meeting,
                    )
                new = KnowledgeItem(
                    owner=owner, workspace=workspace, project=meeting.project, meeting=meeting,
                    entity_type=c.entity_type, entity_id=c.entity_id,
                    title=c.title[:500], text=c.text, speaker=c.speaker,
                    source_start_time=c.start_time, occurred_at=meeting.created_at,
                    language=meeting.language, embedding=emb,
                    version=prev_version + 1, knowledge_version=kv.version,
                    embedding_version=emb_ver, valid_from=now, valid_to=None, recorded_at=now,
                    is_current=True, supersedes_version=(prev_version or None),
                    change_source=change_source, changed_by=changed_by,
                    change_reason=reason,
                )
                if changed_by is not None:
                    new.set_acting_user(changed_by)
                new.save()
                versioning.emit_event(
                    owner=owner, item=new, entity_type=c.entity_type, entity_id=c.entity_id,
                    event_type=(KnowledgeEventType.UPDATED if prev else KnowledgeEventType.CREATED),
                    version=new.version, supersedes_version=(prev_version or None),
                    knowledge_version=kv.version, change_source=change_source,
                    changed_by=changed_by, meeting=meeting,
                )
                changed += 1

            for (etype, eid), prev in archived:
                prev.is_current = False
                prev.valid_to = now
                prev.save(update_fields=["is_current", "valid_to", "updated_at"])
                versioning.emit_event(
                    owner=owner, item=prev, entity_type=etype, entity_id=eid,
                    event_type=KnowledgeEventType.ARCHIVED, version=prev.version,
                    knowledge_version=kv.version, change_source=change_source,
                    changed_by=changed_by, meeting=meeting,
                )
                changed += 1

        versioning.refresh_counts(kv)
        logger.info("Re-indexed meeting %s: %d knowledge change(s) at knowledge v%d.",
                    meeting.id, changed, kv.version)
        return changed

    def stats(self, owner) -> dict:
        """Knowledge Freshness + Versioning surface (feature #1)."""
        qs = KnowledgeItem.objects.current().filter(owner=owner)
        latest = KnowledgeVersion.objects.filter(owner=owner).order_by("-version").first()
        return {
            "knowledge_version": latest.version if latest else 0,
            "indexed_at": latest.indexed_at if latest else qs.aggregate(m=Max("updated_at"))["m"],
            "embedding_version": latest.embedding_version.label if latest and latest.embedding_version else None,
            "items_indexed": qs.count(),
            "meetings_indexed": qs.exclude(meeting=None).values("meeting").distinct().count(),
            "projects_included": qs.exclude(project=None).values("project").distinct().count(),
            "meetings": latest.meetings if latest else 0,
            "projects": latest.projects if latest else 0,
            "tasks": latest.tasks if latest else 0,
            "decisions": latest.decisions if latest else 0,
            "risks": latest.risks if latest else 0,
            "last_updated": qs.aggregate(m=Max("updated_at"))["m"],
        }
