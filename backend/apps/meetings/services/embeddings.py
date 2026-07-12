"""Local embeddings for semantic retrieval (RAG chat).

Default is Ollama's ``nomic-embed-text`` model — free, offline, no paid API. A
deterministic dummy provider is used in tests (config-only), so retrieval is
testable without a running Ollama server.
"""
from __future__ import annotations

import hashlib
import json as jsonlib
import logging
import math
import urllib.request
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("meetingmind.ai")

_DIM = 64  # dummy-vector dimension


class EmbeddingProvider(ABC):
    # Identity — recorded in knowledge.EmbeddingVersion so we always know which
    # model produced a given vector (safe for future model swaps + audit).
    name = "embedding"
    model_name = ""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OllamaEmbeddingProvider(EmbeddingProvider):
    name = "ollama"

    def __init__(self):
        self._base = settings.OLLAMA_BASE_URL.rstrip("/")
        self._model = settings.EMBEDDING_MODEL
        self.model_name = self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Prefer the batch endpoint; fall back to per-text /api/embeddings.
        try:
            req = urllib.request.Request(
                f"{self._base}/api/embed",
                data=jsonlib.dumps({"model": self._model, "input": texts}).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=settings.AI_REQUEST_TIMEOUT) as resp:
                data = jsonlib.loads(resp.read().decode())
            embs = data.get("embeddings")
            if embs and len(embs) == len(texts):
                return embs
        except Exception:  # noqa: BLE001
            logger.debug("Ollama /api/embed unavailable; using per-text embeddings.", exc_info=True)

        out = []
        for t in texts:
            req = urllib.request.Request(
                f"{self._base}/api/embeddings",
                data=jsonlib.dumps({"model": self._model, "prompt": t}).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=settings.AI_REQUEST_TIMEOUT) as resp:
                out.append(jsonlib.loads(resp.read().decode())["embedding"])
        return out


class DummyEmbeddingProvider(EmbeddingProvider):
    """Deterministic bag-of-words hashed vectors — good enough for tests."""

    name = "dummy"
    model_name = f"dummy-{_DIM}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for text in texts:
            v = [0.0] * _DIM
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                v[h % _DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / norm for x in v])
        return vecs


def get_embedding_provider() -> EmbeddingProvider:
    provider = (settings.EMBEDDING_PROVIDER or "ollama").lower()
    if provider in {"dummy", "mock"}:
        return DummyEmbeddingProvider()
    return OllamaEmbeddingProvider()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
