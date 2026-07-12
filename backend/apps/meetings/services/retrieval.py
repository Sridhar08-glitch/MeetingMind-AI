"""Hybrid RAG retrieval — find the transcript segments relevant to a question.

Combines local semantic similarity (Ollama embeddings) with keyword overlap, so
only the relevant slices of a (possibly long) transcript are sent to the LLM —
never the whole thing. Also supports keyword and timestamp search directly.

Segment embeddings are cached per meeting+version so we embed each transcript
once, not on every question.
"""
from __future__ import annotations

import re

from django.conf import settings

from apps.meetings.models import Meeting, TranscriptSegment
from apps.meetings.services.embeddings import cosine, get_embedding_provider

# Process-wide cache: (meeting_id, segment_count) -> list[embedding]
_EMB_CACHE: dict[tuple, list[list[float]]] = {}
_MAX_CACHE = 64

# Meetings with at most this many segments are fed whole (semantic sub-selection
# only matters for long transcripts).
_FULL_CONTEXT_MAX_SEGMENTS = 25

# Meta/overview questions aren't about one segment — they need the whole meeting.
_OVERVIEW_RE = re.compile(
    r"\b(summar|overview|recap|minutes|whole meeting|entire meeting|"
    r"what (was|were)\s+(discussed|talked|covered)|main points|key points|tl;?dr)\b",
    re.IGNORECASE,
)


def is_overview_query(query: str) -> bool:
    return bool(_OVERVIEW_RE.search(query or ""))


class RetrievalService:
    def __init__(self, embedder=None):
        self.embedder = embedder or get_embedding_provider()

    def _segment_embeddings(self, meeting: Meeting, segments: list[TranscriptSegment]) -> list[list[float]]:
        key = (str(meeting.id), len(segments))
        cached = _EMB_CACHE.get(key)
        if cached is not None and len(cached) == len(segments):
            return cached
        embeddings = self.embedder.embed([s.text for s in segments])
        if len(_EMB_CACHE) >= _MAX_CACHE:
            _EMB_CACHE.pop(next(iter(_EMB_CACHE)))
        _EMB_CACHE[key] = embeddings
        return embeddings

    def retrieve(self, meeting: Meeting, query: str, *, k: int | None = None) -> list[TranscriptSegment]:
        """Return the top-k segments for ``query`` via hybrid semantic+keyword scoring."""
        segments = list(meeting.segments.order_by("index"))
        if not segments:
            return []
        k = k or settings.CHAT_RETRIEVAL_K

        # Overview/summary questions get the FULL transcript — a partial semantic
        # slice can't answer "summarize this meeting". Long transcripts are capped
        # so we never blow the context window.
        if is_overview_query(query):
            return segments[:_FULL_CONTEXT_MAX_SEGMENTS] if len(segments) > _FULL_CONTEXT_MAX_SEGMENTS else segments

        seg_embs = self._segment_embeddings(meeting, segments)
        q_emb = self.embedder.embed_one(query)
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]

        scored: list[tuple[float, TranscriptSegment]] = []
        for seg, emb in zip(segments, seg_embs):
            semantic = cosine(q_emb, emb)
            text_l = seg.text.lower()
            keyword = sum(1 for t in terms if t in text_l)
            scored.append((semantic + 0.15 * keyword, seg))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [seg for _, seg in scored[:k]]
        # Return in transcript order for readable context.
        return sorted(top, key=lambda s: s.index)

    # --- direct searches (exposed for the chat "search" tools) --------------
    @staticmethod
    def keyword_search(meeting: Meeting, query: str) -> list[TranscriptSegment]:
        return list(meeting.segments.filter(text__icontains=query).order_by("index"))

    @staticmethod
    def timestamp_search(meeting: Meeting, start: float, end: float) -> list[TranscriptSegment]:
        return list(
            meeting.segments.filter(end_time__gte=start, start_time__lte=end).order_by("index")
        )
