"""MediaProvider registry — the single extension point for new sources.

Adding a future source (Google Drive, Dropbox, OneDrive, network folder-watch,
S3, FTP/SFTP, WebDAV, …) is a new MediaProvider subclass plus one ``register(...)``
call here — no change to the import session, the API, or the AI pipeline.

``resolve_provider(url)`` returns the first *available* provider whose
``can_handle`` matches, checked in priority order (specific → catch-all): dummy →
direct-file → podcast/RSS → public-video.
"""
from __future__ import annotations

import logging

from .base import MediaProvider, MediaProviderError
from .directurl import DirectUrlProvider
from .dummy import DummyMediaProvider
from .podcast import PodcastRssProvider
from .publicvideo import PublicVideoProvider

logger = logging.getLogger("meetingmind.ingest")

# Priority order: most specific first, public-video (catch-all web page) last.
_PROVIDERS: list[MediaProvider] = [
    DummyMediaProvider(),
    DirectUrlProvider(),
    PodcastRssProvider(),
    PublicVideoProvider(),
]

# Providers that never appear in capabilities/UI (test-only).
_HIDDEN_IDS = {"dummy"}


def register(provider: MediaProvider, *, priority: int | None = None) -> None:
    """Add a provider. ``priority`` inserts before that index (default: append)."""
    if priority is None:
        _PROVIDERS.append(provider)
    else:
        _PROVIDERS.insert(priority, provider)


def all_providers() -> list[MediaProvider]:
    return list(_PROVIDERS)


def enabled_providers() -> list[MediaProvider]:
    """User-facing providers that are actually usable in this install."""
    return [p for p in _PROVIDERS if p.id not in _HIDDEN_IDS and type(p).available()]


def provider_by_id(provider_id: str) -> MediaProvider | None:
    return next((p for p in _PROVIDERS if p.id == provider_id), None)


def resolve_provider(url: str) -> MediaProvider:
    """Pick the provider for a URL, or raise MediaProviderError if none applies."""
    for provider in _PROVIDERS:
        try:
            if provider.can_handle(url) and type(provider).available():
                return provider
        except Exception:  # noqa: BLE001 — a bad matcher must not break routing
            continue
    raise MediaProviderError(
        "No media importer can handle that URL.", code="unsupported_url", blocked=True
    )


def import_available() -> bool:
    """True if at least one non-test provider can run (deps installed)."""
    return any(type(p).available() for p in _PROVIDERS if p.id not in _HIDDEN_IDS)
