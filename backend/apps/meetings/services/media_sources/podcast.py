"""PodcastRssProvider — import episodes from a public podcast / RSS feed.

``analyze`` parses the feed (feedparser) and returns the selectable episodes; the
UI shows a picker. ``fetch(episode_id=…)`` downloads that episode's audio
enclosure. A single podcast episode that is itself a direct audio URL is handled
by ``DirectUrlProvider`` — this provider is specifically for feeds.
"""
from __future__ import annotations

import hashlib
import logging
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings

from apps.meetings.enums import MeetingSource, MediaKind
from .base import (
    EpisodeInfo,
    MediaFetchResult,
    MediaProvider,
    MediaProviderError,
    MediaSourceInfo,
    ProgressCallback,
)
from .download import stream_download
from .guards import assert_public_url

logger = logging.getLogger("meetingmind.ingest")

_UA = "MeetingMind-MediaImport/1.0"
_AUDIO_ENCLOSURE_HINTS = ("audio/", "video/")


def _episode_id(entry) -> str:
    """A stable id for an episode: GUID if present, else a hash of the enclosure."""
    guid = getattr(entry, "id", "") or getattr(entry, "guid", "")
    if guid:
        return hashlib.sha1(guid.encode("utf-8", "ignore")).hexdigest()[:16]
    url = _enclosure_url(entry)
    return hashlib.sha1((url or getattr(entry, "title", "")).encode("utf-8", "ignore")).hexdigest()[:16]


def _enclosure_url(entry) -> str:
    for enc in getattr(entry, "enclosures", []) or []:
        etype = (enc.get("type") or "").lower()
        href = enc.get("href") or enc.get("url") or ""
        if href and (not etype or etype.startswith(_AUDIO_ENCLOSURE_HINTS)):
            return href
    # Some feeds put the media in links rel="enclosure".
    for link in getattr(entry, "links", []) or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return ""


class PodcastRssProvider(MediaProvider):
    id = "podcast_rss"
    label = "Podcast / RSS feed"
    source_type = MeetingSource.PODCAST
    supports_resume = True

    @classmethod
    def available(cls) -> bool:
        try:
            import feedparser  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def can_handle(self, url: str) -> bool:
        parsed = urlparse((url or "").strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        blob = (parsed.path + "?" + (parsed.query or "")).lower()
        host = (parsed.hostname or "").lower()
        return (
            blob.endswith((".xml", ".rss"))
            or "rss" in blob or "feed" in blob
            or host.startswith("feeds.") or "podcast" in host
        )

    def _timeout(self) -> int:
        return int(getattr(settings, "MEDIA_IMPORT_TIMEOUT", 60))

    def _parse(self, url: str):
        import feedparser

        # Fetch ourselves (guarded + UA) then hand bytes to feedparser, so the
        # SSRF guard applies and we control the timeout.
        try:
            with urlopen(Request(url, headers={"User-Agent": _UA}), timeout=self._timeout()) as resp:
                raw = resp.read()
        except Exception as exc:  # noqa: BLE001
            raise MediaProviderError(f"Could not read the feed: {exc}", code="feed_error", blocked=True) from exc
        feed = feedparser.parse(raw)
        if feed.bozo and not feed.entries:
            raise MediaProviderError("That URL is not a valid podcast/RSS feed.", code="not_a_feed", blocked=True)
        return feed

    # --- analyze ---------------------------------------------------------
    def analyze(self, url: str) -> MediaSourceInfo:
        assert_public_url(url)
        feed = self._parse(url)
        channel = feed.feed
        episodes: list[EpisodeInfo] = []
        for entry in feed.entries:
            enc = _enclosure_url(entry)
            if not enc:
                continue
            dur = getattr(entry, "itunes_duration", "") or ""
            episodes.append(EpisodeInfo(
                episode_id=_episode_id(entry),
                title=getattr(entry, "title", "") or "Untitled episode",
                guid=getattr(entry, "id", "") or getattr(entry, "guid", ""),
                url=enc,
                duration=_parse_duration(dur),
                published_at=getattr(entry, "published", "") or "",
            ))
        if not episodes:
            raise MediaProviderError("No downloadable episodes found in that feed.", code="no_episodes", blocked=True)
        image = ""
        if getattr(channel, "image", None):
            image = channel.image.get("href", "") if isinstance(channel.image, dict) else getattr(channel.image, "href", "")
        return MediaSourceInfo(
            source_type=self.source_type,
            webpage_url=getattr(channel, "link", "") or url,
            platform="Podcast",
            title=getattr(channel, "title", "") or "Podcast",
            author=getattr(channel, "author", "") or getattr(channel, "title", "") or "",
            thumbnail_url=image,
            license=getattr(channel, "license", "") or "",
            media_kind=MediaKind.AUDIO,
            is_playlist=True,
            episodes=episodes,
            extra={"podcast": getattr(channel, "title", "") or ""},
        )

    # --- fetch -----------------------------------------------------------
    def fetch(
        self,
        url: str,
        dest_dir: str,
        *,
        requested_media: str = "audio",
        episode_id: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> MediaFetchResult:
        source = self.analyze(url)
        episode = None
        if episode_id:
            episode = next((e for e in source.episodes if e.episode_id == episode_id), None)
        episode = episode or (source.episodes[0] if source.episodes else None)
        if episode is None or not episode.url:
            raise MediaProviderError("That episode could not be found in the feed.", code="episode_not_found", blocked=True)

        assert_public_url(episode.url)
        ext = os.path.splitext(urlparse(episode.url).path)[1].lstrip(".").lower() or "mp3"
        dest = os.path.join(dest_dir, f"{episode.episode_id}.{ext}")
        cap = getattr(settings, "MAX_UPLOAD_SIZE_MB", 2048) * 1024 * 1024
        stream_download(episode.url, dest, cap_bytes=cap, timeout=self._timeout(), progress_cb=progress_cb)

        meta = MediaSourceInfo(
            source_type=self.source_type,
            webpage_url=source.webpage_url,
            platform="Podcast",
            title=episode.title,
            author=source.author,
            duration=episode.duration,
            thumbnail_url=source.thumbnail_url,
            published_at=episode.published_at,
            media_kind=MediaKind.AUDIO,
            extra={"podcast": source.title, "episode": episode.title, "episode_guid": episode.guid},
        )
        return MediaFetchResult(
            file_path=dest, filename=os.path.basename(dest),
            media_kind=MediaKind.AUDIO, metadata=meta.provenance(),
        )


def _parse_duration(value: str) -> int | None:
    """iTunes duration is either seconds or HH:MM:SS / MM:SS."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    parts = value.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds
