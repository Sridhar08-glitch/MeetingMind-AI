"""PublicVideoProvider — yt-dlp-backed import for public video/audio platforms.

Covers YouTube, Vimeo, and the ~1000 public sites yt-dlp supports, so this is a
generic provider, not a per-site module. It ONLY downloads a local file (reusing
the configured ffmpeg); all transcription/AI happens later in the existing
pipeline. Private/DRM/age-gated/live content is refused — public content only.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from django.conf import settings

from apps.meetings.enums import MeetingSource, MediaKind
from .base import (
    MediaFetchResult,
    MediaProvider,
    MediaProviderError,
    MediaSourceInfo,
    ProgressCallback,
)
from .guards import assert_public_url

logger = logging.getLogger("meetingmind.ingest")

# Direct-media / feed extensions this provider should NOT claim (handled by the
# DirectUrl / RSS providers). Everything else http(s) is a candidate web page.
_NON_VIDEO_SUFFIXES = (
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".xml", ".rss",
)


def _ffmpeg_location() -> str:
    """yt-dlp wants the ffmpeg *directory* (or binary). Reuse the configured one."""
    binary = getattr(settings, "FFMPEG_BINARY", "ffmpeg")
    directory = os.path.dirname(binary)
    return directory or binary


class PublicVideoProvider(MediaProvider):
    id = "public_video"
    label = "Public video (YouTube, Vimeo, and more)"
    source_type = MeetingSource.PUBLIC_VIDEO
    supports_resume = True  # yt-dlp continuedl

    @classmethod
    def available(cls) -> bool:
        try:
            import yt_dlp  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def can_handle(self, url: str) -> bool:
        parsed = urlparse((url or "").strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        path = parsed.path.lower()
        # Let the direct-file / RSS providers take obvious media/feed URLs.
        return not path.endswith(_NON_VIDEO_SUFFIXES)

    # --- analyze ---------------------------------------------------------
    def analyze(self, url: str) -> MediaSourceInfo:
        assert_public_url(url)
        info = self._extract(url, download=False)
        return self._info_to_source(url, info)

    def _extract(self, url: str, *, download: bool, ydl_opts: dict | None = None):
        import yt_dlp

        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": not download}
        if ydl_opts:
            opts.update(ydl_opts)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as exc:  # private/unavailable/DRM/geo
            raise MediaProviderError(
                f"This media can't be imported (it may be private, removed, or restricted): {exc}",
                code="content_unavailable", blocked=True,
            ) from exc

    def _info_to_source(self, url: str, info: dict) -> MediaSourceInfo:
        if info is None:
            raise MediaProviderError("No media found at that URL.", code="not_found", blocked=True)
        if info.get("is_live"):
            raise MediaProviderError("Live streams can't be imported.", code="is_live", blocked=True)
        duration = info.get("duration")
        self._enforce_duration(duration)
        published = info.get("upload_date") or ""
        if published and len(published) == 8:  # yt-dlp gives YYYYMMDD
            published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
        thumb = info.get("thumbnail") or ""
        if not thumb and info.get("thumbnails"):
            thumb = info["thumbnails"][-1].get("url", "")
        return MediaSourceInfo(
            source_type=self.source_type,
            webpage_url=info.get("webpage_url") or url,
            platform=(info.get("extractor_key") or info.get("extractor") or "").replace("_", " ").strip(),
            platform_id=str(info.get("id") or ""),
            title=info.get("title") or "",
            author=info.get("uploader") or info.get("channel") or info.get("creator") or "",
            duration=int(duration) if duration else None,
            thumbnail_url=thumb,
            published_at=published,
            license=info.get("license") or "",
            media_kind=MediaKind.VIDEO,
        )

    def _enforce_duration(self, duration) -> None:
        cap = getattr(settings, "MEDIA_IMPORT_MAX_DURATION_SECONDS", None)
        if cap and duration and duration > cap:
            raise MediaProviderError(
                f"That media is {int(duration) // 60} min, over the {cap // 60} min import limit.",
                code="too_long", blocked=True,
            )

    # --- fetch -----------------------------------------------------------
    def fetch(
        self,
        url: str,
        dest_dir: str,
        *,
        requested_media: str = "video",
        episode_id: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> MediaFetchResult:
        assert_public_url(url)

        def hook(d: dict):
            if progress_cb is None:
                return
            if d.get("status") == "downloading":
                done = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                pct = (done / total * 100.0) if total else 0.0
                progress_cb(min(pct, 99.0), done, total)
            elif d.get("status") == "finished":
                progress_cb(100.0, d.get("downloaded_bytes") or 0, d.get("total_bytes"))

        want_audio = requested_media == "audio"
        fmt = "bestaudio[ext=m4a]/bestaudio/best" if want_audio else "best[ext=mp4]/bestvideo+bestaudio/best"
        max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_MB", 2048) * 1024 * 1024
        opts = {
            "format": fmt,
            "outtmpl": os.path.join(dest_dir, "%(id)s.%(ext)s"),
            "continuedl": True,               # resume interrupted downloads
            "retries": 3,
            "max_filesize": max_bytes,
            "ffmpeg_location": _ffmpeg_location(),
            "progress_hooks": [hook],
        }
        info = self._extract(url, download=True, ydl_opts=opts)
        path = self._locate_output(dest_dir)
        if path is None:
            raise MediaProviderError("Download produced no file.", code="no_output")
        kind = MediaKind.AUDIO if want_audio else MediaKind.VIDEO
        return MediaFetchResult(
            file_path=path,
            filename=os.path.basename(path),
            media_kind=kind,
            metadata=self._info_to_source(url, info).provenance(),
        )

    @staticmethod
    def _locate_output(dest_dir: str) -> str | None:
        """Pick the largest fully-downloaded file (ignore .part / .ytdl scraps)."""
        best, best_size = None, -1
        for name in os.listdir(dest_dir):
            if name.endswith((".part", ".ytdl", ".temp")):
                continue
            full = os.path.join(dest_dir, name)
            if os.path.isfile(full):
                size = os.path.getsize(full)
                if size > best_size:
                    best, best_size = full, size
        return best
