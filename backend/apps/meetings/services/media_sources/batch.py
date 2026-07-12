"""Batch import helpers.

Batch import is orchestration, not a downloader: each URL is resolved to its own
provider and imported independently, so one bad URL never blocks the rest. The
API/UI creates one MediaImportSession per resolved item.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import MediaProvider


@dataclass
class BatchItem:
    url: str
    provider_id: str = ""
    source_type: str = ""
    error: str = ""      # set if the URL couldn't be routed to any provider


def expand(urls, resolver) -> list[BatchItem]:
    """Resolve each URL to a provider. ``resolver`` is ``registry.resolve_provider``.

    Never raises for a single bad URL — it is returned as a BatchItem with an
    ``error`` so the caller can report it and still process the good ones.
    """
    items: list[BatchItem] = []
    for raw in urls:
        url = (raw or "").strip()
        if not url:
            continue
        try:
            provider: MediaProvider = resolver(url)
            items.append(BatchItem(url=url, provider_id=provider.id, source_type=provider.source_type))
        except Exception as exc:  # noqa: BLE001
            items.append(BatchItem(url=url, error=str(exc)))
    return items
