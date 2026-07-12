"""Hybrid organization search — authorization-first, then FTS + semantic + recency."""
from __future__ import annotations

import re

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.utils import timezone

from apps.knowledge.models import KnowledgeItem
from apps.meetings.services.embeddings import cosine, get_embedding_provider

_CANDIDATE_CAP = 400


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", (text or "").lower()) if len(t) > 2}


class OrgSearchService:
    def __init__(self, embedder=None):
        self.embedder = embedder or get_embedding_provider()

    def search(self, owner, query: str, *, filters: dict | None = None, k: int = 12) -> list[dict]:
        # AUTHORIZATION ENFORCED BEFORE ANY EMBEDDING/SEARCH.
        f = filters or {}
        # Time-Travel: `as_of` restricts to the knowledge valid at that instant;
        # otherwise only currently-valid rows are searched.
        as_of = f.get("as_of")
        base = KnowledgeItem.objects.as_of(as_of) if as_of else KnowledgeItem.objects.current()
        qs = base.filter(owner=owner).select_related("meeting", "project")
        if f.get("project"):
            qs = qs.filter(project_id=f["project"])
        if f.get("meeting"):
            qs = qs.filter(meeting_id=f["meeting"])
        if f.get("entity_type"):
            qs = qs.filter(entity_type=f["entity_type"])
        if f.get("speaker"):
            qs = qs.filter(speaker__icontains=f["speaker"])
        if f.get("language"):
            qs = qs.filter(language=f["language"])
        if f.get("date_from"):
            qs = qs.filter(occurred_at__gte=f["date_from"])
        if f.get("date_to"):
            qs = qs.filter(occurred_at__lte=f["date_to"])

        if not query.strip():
            items = list(qs.order_by("-occurred_at")[:k])
            return [self._result(i, 0.0) for i in items]

        # PostgreSQL full-text search narrows the candidate set; embeddings re-rank.
        sq = SearchQuery(query, search_type="websearch")
        qs = qs.annotate(rank=SearchRank(SearchVector("title", "text"), sq))
        candidates = list(qs.order_by("-rank", "-occurred_at")[:_CANDIDATE_CAP])
        if not candidates:
            return []

        q_emb = self.embedder.embed_one(query)
        terms = _tokens(query)
        now = timezone.now()
        scored = []
        for item in candidates:
            semantic = cosine(q_emb, item.embedding) if item.embedding else 0.0
            keyword = sum(1 for t in terms if t in item.text.lower())
            fts = float(getattr(item, "rank", 0.0) or 0.0)
            # Mild recency boost (favour newer knowledge on ties).
            age_days = max(0.0, (now - item.occurred_at).total_seconds() / 86400)
            recency = 0.05 * max(0.0, 1 - age_days / 365)
            score = semantic + 0.15 * keyword + 0.3 * fts + recency
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._result(item, score) for score, item in scored[:k]]

    @staticmethod
    def _result(item: KnowledgeItem, score: float) -> dict:
        return {
            "item_id": str(item.id),
            "version": item.version,
            "knowledge_version": item.knowledge_version,
            "entity_type": item.entity_type,
            "entity_id": str(item.entity_id),
            "title": item.title,
            "snippet": item.text[:240],
            "meeting_id": str(item.meeting_id) if item.meeting_id else None,
            "meeting_title": item.meeting.title if item.meeting_id else None,
            "project_id": str(item.project_id) if item.project_id else None,
            "speaker": item.speaker,
            "timestamp": item.source_start_time,
            "occurred_at": item.occurred_at,
            "confidence": round(min(1.0, max(0.0, score)) * 100),
        }
