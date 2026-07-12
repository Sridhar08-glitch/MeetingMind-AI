"""Pluggable storage abstraction.

Upload code never touches Django's storage or the filesystem directly — it goes
through a :class:`StorageService`. Today the only implementation is
:class:`LocalStorage` (wrapping the configured Django storage), but adding S3 or
Azure later means writing one new subclass and flipping ``STORAGE_BACKEND`` —
nothing in the domain layer changes.

Keys are opaque, randomized and date-bucketed (``<prefix>/YYYY/MM/<uuid>.<ext>``)
so no single directory accumulates every file and the original (untrusted) name
is never used to build a path.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone


def build_object_key(prefix: str, filename: str) -> str:
    """Return a randomized, date-bucketed storage key derived only from the ext."""
    ext = PurePosixPath(filename).suffix.lower().lstrip(".")
    name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    now = timezone.now()
    return f"{prefix}/{now:%Y}/{now:%m}/{name}"


class StorageService(ABC):
    """Interface every storage backend implements."""

    @abstractmethod
    def save(self, prefix: str, filename: str, content) -> str:
        """Persist ``content`` under a fresh key and return the stored key."""

    @abstractmethod
    def open(self, key: str, mode: str = "rb"):
        """Return a readable file object for ``key``."""

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def url(self, key: str) -> str: ...

    def path(self, key: str) -> str | None:
        """Absolute filesystem path when the backend is local, else ``None``."""
        return None


class LocalStorage(StorageService):
    """Local-filesystem backend backed by Django's configured default storage."""

    def __init__(self, backend=None):
        self._backend = backend or default_storage

    def save(self, prefix: str, filename: str, content) -> str:
        key = build_object_key(prefix, filename)
        return self._backend.save(key, content)

    def open(self, key: str, mode: str = "rb"):
        return self._backend.open(key, mode)

    def delete(self, key: str) -> None:
        if key and self._backend.exists(key):
            self._backend.delete(key)

    def exists(self, key: str) -> bool:
        return bool(key) and self._backend.exists(key)

    def size(self, key: str) -> int:
        return self._backend.size(key)

    def url(self, key: str) -> str:
        return self._backend.url(key)

    def path(self, key: str) -> str | None:
        try:
            return self._backend.path(key)
        except NotImplementedError:  # non-filesystem backend
            return None


_BACKENDS: dict[str, type[StorageService]] = {
    "local": LocalStorage,
}


def get_storage_service() -> StorageService:
    """Return the configured storage service (defaults to local)."""
    backend = getattr(settings, "STORAGE_BACKEND", "local")
    cls = _BACKENDS.get(backend, LocalStorage)
    return cls()
