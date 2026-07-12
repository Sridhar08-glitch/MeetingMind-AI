"""DirectUrlProvider — import a public direct media URL (mp3/mp4/wav/m4a/webm/…).

Uses only the standard library (urllib) — no extra dependency. Supports resumable
downloads via an HTTP Range request that appends to a partial file. Acquires the
file only; the existing pipeline does everything else.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

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

_AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "flac", "ogg", "oga", "opus"}
_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm"}
_MEDIA_EXT = _AUDIO_EXT | _VIDEO_EXT
_UA = "MeetingMind-MediaImport/1.0"
_CHUNK = 256 * 1024


def _ext_of(url: str) -> str:
    path = urlparse(url).path
    return os.path.splitext(path)[1].lstrip(".").lower()


def _kind_for(ext: str, content_type: str) -> str | None:
    if ext in _AUDIO_EXT or content_type.startswith("audio/"):
        return MediaKind.AUDIO
    if ext in _VIDEO_EXT or content_type.startswith("video/"):
        return MediaKind.VIDEO
    return None


class DirectUrlProvider(MediaProvider):
    id = "direct_url"
    label = "Direct media URL"
    source_type = MeetingSource.DIRECT_URL
    supports_resume = True

    def can_handle(self, url: str) -> bool:
        parsed = urlparse((url or "").strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        return _ext_of(url) in _MEDIA_EXT

    def _timeout(self) -> int:
        return int(getattr(settings, "MEDIA_IMPORT_TIMEOUT", 60))

    # --- analyze ---------------------------------------------------------
    def analyze(self, url: str) -> MediaSourceInfo:
        assert_public_url(url)
        ext = _ext_of(url)
        content_type, size = self._probe(url)
        kind = _kind_for(ext, content_type)
        if kind is None:
            raise MediaProviderError(
                "That URL doesn't look like a direct audio or video file.",
                code="not_media", blocked=True,
            )
        self._enforce_size(size)
        name = unquote(os.path.basename(urlparse(url).path)) or "download"
        return MediaSourceInfo(
            source_type=self.source_type,
            webpage_url=url,
            platform="Direct URL",
            title=os.path.splitext(name)[0],
            media_kind=kind,
        )

    def _probe(self, url: str) -> tuple[str, int | None]:
        """Best-effort HEAD → (content_type, content_length). Falls back to GET."""
        for method in ("HEAD", "GET"):
            try:
                req = Request(url, method=method, headers={"User-Agent": _UA})
                with urlopen(req, timeout=self._timeout()) as resp:
                    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    clen = resp.headers.get("Content-Length")
                    return ctype, (int(clen) if clen and clen.isdigit() else None)
            except Exception:  # noqa: BLE001 — some servers reject HEAD; try GET
                continue
        return "", None

    def _enforce_size(self, size: int | None) -> None:
        cap = getattr(settings, "MAX_UPLOAD_SIZE_MB", 2048) * 1024 * 1024
        if size and size > cap:
            raise MediaProviderError(
                f"That file is {size // 1024 // 1024} MB, over the {cap // 1024 // 1024} MB limit.",
                code="too_large", blocked=True,
            )

    # --- fetch (resumable) ----------------------------------------------
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
        ext = _ext_of(url) or "bin"
        name = unquote(os.path.basename(urlparse(url).path)) or f"download.{ext}"
        dest = os.path.join(dest_dir, name)
        cap = getattr(settings, "MAX_UPLOAD_SIZE_MB", 2048) * 1024 * 1024

        # Resume: if a partial file exists, ask the server for the remaining bytes.
        existing = os.path.getsize(dest) if os.path.exists(dest) else 0
        headers = {"User-Agent": _UA}
        if existing:
            headers["Range"] = f"bytes={existing}-"

        req = Request(url, headers=headers)
        try:
            resp = urlopen(req, timeout=self._timeout())
        except Exception as exc:  # noqa: BLE001
            raise MediaProviderError(f"Could not download the file: {exc}", code="download_error") from exc

        resuming = existing and resp.status == 206
        total_hdr = resp.headers.get("Content-Length")
        remaining = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
        total = (existing + remaining) if (resuming and remaining is not None) else remaining
        mode = "ab" if resuming else "wb"
        done = existing if resuming else 0

        with resp, open(dest, mode) as fh:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if done > cap:
                    fh.close()
                    os.remove(dest)
                    raise MediaProviderError(
                        f"Download exceeded the {cap // 1024 // 1024} MB limit.",
                        code="too_large", blocked=True,
                    )
                if progress_cb:
                    pct = (done / total * 100.0) if total else 0.0
                    progress_cb(min(pct, 100.0), done, total)

        content_type, _ = self._probe(url)
        kind = _kind_for(ext, content_type) or (
            MediaKind.AUDIO if requested_media == "audio" else MediaKind.VIDEO
        )
        return MediaFetchResult(
            file_path=dest,
            filename=name,
            media_kind=kind,
            content_type=content_type,
            metadata=MediaSourceInfo(
                source_type=self.source_type, webpage_url=url, platform="Direct URL",
                title=os.path.splitext(name)[0], media_kind=kind,
            ).provenance(),
        )
