"""MediaProvider abstraction — the ONLY new work in universal media import.

A provider has exactly one responsibility: **acquire media and produce a local
file.** It never transcribes, summarizes, indexes, or touches Knowledge /
Workspace / Executive / Agents / Planner / Collaboration. Once a local file
exists, the caller hands it to the existing ``create_upload()`` entry point and
the established Phase 6–13 pipeline takes over as the single source of truth.

This mirrors the STT / LLM / Translation provider pattern (an ABC + a factory +
concrete providers) so adding a future source (Drive, Dropbox, S3, SFTP, …) is a
new class + one ``registry.register(...)`` call — no pipeline change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from apps.meetings.enums import MediaKind

# A progress callback: (percent 0-100, bytes_done, bytes_total|None).
ProgressCallback = Callable[[float, int, int | None], None]


@dataclass
class EpisodeInfo:
    """One selectable item from a playlist/feed (e.g. a podcast episode)."""

    episode_id: str          # stable id used to fetch (GUID / enclosure url / index)
    title: str = ""
    guid: str = ""
    url: str = ""            # enclosure / media url
    duration: int | None = None
    published_at: str = ""   # ISO-8601 if known


@dataclass
class MediaSourceInfo:
    """Metadata gathered by ``analyze()`` WITHOUT downloading the media."""

    source_type: str                       # MeetingSource value (public_video/podcast/…)
    webpage_url: str = ""
    platform: str = ""                     # "YouTube", "Vimeo", "" for a plain file
    platform_id: str = ""                  # provider-native id (video id / feed id)
    title: str = ""
    author: str = ""                       # channel / uploader / podcast name
    duration: int | None = None
    thumbnail_url: str = ""
    published_at: str = ""
    license: str = ""
    media_kind: str = MediaKind.VIDEO
    is_playlist: bool = False
    episodes: list[EpisodeInfo] = field(default_factory=list)
    # Free-form extras a provider wants preserved on the Meeting.
    extra: dict = field(default_factory=dict)

    def provenance(self) -> dict:
        """The subset persisted to ``Meeting.source_metadata`` (JSON-safe)."""
        data = {
            "source_type": self.source_type,
            "platform": self.platform,
            "platform_id": self.platform_id,
            "original_url": self.webpage_url,
            "author": self.author,
            "title": self.title,
            "thumbnail": self.thumbnail_url,
            "published_at": self.published_at,
            "license": self.license,
            "duration": self.duration,
        }
        if self.extra:
            data.update(self.extra)
        # Drop empties so the stored metadata stays tidy.
        return {k: v for k, v in data.items() if v not in ("", None)}


@dataclass
class MediaFetchResult:
    """A downloaded local file, ready to hand to ``create_upload()``."""

    file_path: str
    filename: str
    media_kind: str = MediaKind.VIDEO
    content_type: str = ""
    metadata: dict = field(default_factory=dict)   # provenance to persist


class MediaProviderError(Exception):
    """A provider could not acquire the media.

    ``blocked=True`` means the content is private/DRM/unavailable or the URL was
    rejected by the SSRF/permission guards — a permanent refusal, never retried.
    """

    def __init__(self, message: str, *, code: str = "import_failed", blocked: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.blocked = blocked


class MediaProvider(ABC):
    """Base class every media source implements."""

    # Stable identifier used in settings/logs and to re-select a provider.
    id: str = ""
    # Human-facing label for the capabilities endpoint / UI.
    label: str = ""
    # The MeetingSource this provider produces.
    source_type: str = ""
    # Whether an interrupted download can be resumed (informational).
    supports_resume: bool = False
    # Whether the source URL is fetched over http(s) and must pass the SSRF /
    # public-URL guard. Providers that read local/other transports set False.
    requires_public_url: bool = True

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """True if this provider claims the given URL."""

    @abstractmethod
    def analyze(self, url: str) -> MediaSourceInfo:
        """Return metadata (and any playlist episodes) WITHOUT downloading."""

    @abstractmethod
    def fetch(
        self,
        url: str,
        dest_dir: str,
        *,
        requested_media: str = "video",
        episode_id: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> MediaFetchResult:
        """Download the media into ``dest_dir`` and return the local file."""

    # Convenience: whether this provider is usable in the current install
    # (e.g. an optional dependency is importable). Default: always available.
    @classmethod
    def available(cls) -> bool:
        return True
