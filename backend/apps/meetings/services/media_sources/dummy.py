"""DummyMediaProvider — deterministic, no-network provider for tests.

Claims ``dummy://`` URLs and "downloads" a tiny valid WAV so the rest of the
import → create_upload → pipeline path can be exercised without touching the
network or any real platform.
"""
from __future__ import annotations

import os
import struct
import wave

from apps.meetings.enums import MeetingSource, MediaKind
from .base import (
    MediaFetchResult,
    MediaProvider,
    MediaSourceInfo,
    ProgressCallback,
)

_SCHEME = "dummy://"


def _write_tiny_wav(path: str, seconds: float = 1.0) -> None:
    rate = 16000
    frames = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % frames, *([0] * frames)))


class DummyMediaProvider(MediaProvider):
    id = "dummy"
    label = "Dummy (test)"
    source_type = MeetingSource.PUBLIC_VIDEO
    supports_resume = False
    requires_public_url = False  # dummy:// is not fetched over the network

    def can_handle(self, url: str) -> bool:
        return (url or "").startswith(_SCHEME)

    def analyze(self, url: str) -> MediaSourceInfo:
        return MediaSourceInfo(
            source_type=self.source_type,
            webpage_url=url,
            platform="Dummy",
            platform_id=url.replace(_SCHEME, "") or "dummy-1",
            title="Dummy media",
            author="Dummy Channel",
            duration=1,
            thumbnail_url="",
            published_at="2026-01-01",
            license="CC0",
            media_kind=MediaKind.AUDIO,
        )

    def fetch(
        self,
        url: str,
        dest_dir: str,
        *,
        requested_media: str = "audio",
        episode_id: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> MediaFetchResult:
        dest = os.path.join(dest_dir, "dummy.wav")
        _write_tiny_wav(dest)
        if progress_cb:
            progress_cb(100.0, os.path.getsize(dest), os.path.getsize(dest))
        return MediaFetchResult(
            file_path=dest, filename="dummy.wav", media_kind=MediaKind.AUDIO,
            content_type="audio/wav", metadata=self.analyze(url).provenance(),
        )
