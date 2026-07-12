"""Intelligent transcript chunking for long meetings.

Splits on sentence boundaries near the target size and carries an overlap window
between chunks to preserve context. Short transcripts return a single chunk (the
common case with llama3.2's large context), so no information is lost.
"""
from __future__ import annotations

from django.conf import settings


def chunk_text(text: str, *, size: int | None = None, overlap: int | None = None) -> list[str]:
    text = (text or "").strip()
    size = size or settings.AI_CHUNK_SIZE
    overlap = overlap or settings.AI_CHUNK_OVERLAP
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:
            # Prefer to break at a sentence boundary in the latter half.
            boundary = text.rfind(". ", start + size // 2, end)
            if boundary != -1:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
