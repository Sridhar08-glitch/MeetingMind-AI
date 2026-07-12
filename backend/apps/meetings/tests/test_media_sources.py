"""Phase 14 — MediaProvider abstraction: routing, SSRF guards, batch, dummy.

No network: these tests exercise URL routing, the SSRF/permission guards, batch
expansion, and the deterministic DummyMediaProvider. Real-network imports are
verified separately.
"""
from __future__ import annotations

import os
import wave

import pytest

from apps.meetings.enums import MeetingSource
from apps.meetings.services import media_sources as ms
from apps.meetings.services.media_sources.base import MediaProviderError
from apps.meetings.services.media_sources.guards import assert_public_url


# --- routing ----------------------------------------------------------------
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123", "public_video"),
        ("https://vimeo.com/76979871", "public_video"),
        ("https://example.com/media/talk.mp3", "direct_url"),
        ("https://cdn.example.com/clip.mp4", "direct_url"),
        ("https://feeds.megaphone.fm/show", "podcast_rss"),
        ("https://example.com/podcast/feed.xml", "podcast_rss"),
        ("dummy://sample", "dummy"),
    ],
)
def test_resolve_provider_routes_by_url(url, expected):
    assert ms.resolve_provider(url).id == expected


def test_resolve_provider_rejects_unknown_scheme():
    with pytest.raises(MediaProviderError):
        ms.resolve_provider("ftp://example.com/file.mp3")


def test_enabled_providers_hide_dummy():
    ids = {p.id for p in ms.enabled_providers()}
    assert "dummy" not in ids
    assert ms.import_available() is True


# --- SSRF / permission guards ----------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        "http://127.0.0.1/x.mp4",
        "http://localhost/a",
        "http://10.0.0.5/a",
        "http://192.168.1.10/a",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https:///nohost",
    ],
)
def test_assert_public_url_blocks_unsafe(bad):
    with pytest.raises(MediaProviderError) as exc:
        assert_public_url(bad)
    assert exc.value.blocked is True


def test_assert_public_url_allows_public_host():
    # example.com resolves to public addresses; should not raise.
    assert_public_url("https://example.com/media.mp3")


def test_allow_list_blocks_other_hosts(settings):
    settings.MEDIA_IMPORT_ALLOWED_HOSTS = ["youtube.com"]
    with pytest.raises(MediaProviderError):
        assert_public_url("https://example.com/x.mp4")
    # A subdomain of an allow-listed host is permitted.
    assert_public_url("https://www.youtube.com/watch?v=x")


def test_import_disabled_blocks(settings):
    settings.MEDIA_IMPORT_ENABLED = False
    with pytest.raises(MediaProviderError):
        assert_public_url("https://example.com/x.mp4")


# --- batch expansion --------------------------------------------------------
def test_batch_expand_isolates_bad_urls():
    urls = [
        "https://www.youtube.com/watch?v=ok",
        "not-a-url",
        "https://example.com/a.mp3",
        "",  # skipped
    ]
    items = ms.batch_expand(urls, ms.resolve_provider)
    assert len(items) == 3  # blank skipped
    by_url = {i.url: i for i in items}
    assert by_url["https://www.youtube.com/watch?v=ok"].provider_id == "public_video"
    assert by_url["https://example.com/a.mp3"].provider_id == "direct_url"
    assert by_url["not-a-url"].error  # routed to an error, does not raise


# --- dummy provider ---------------------------------------------------------
def test_dummy_provider_analyze_and_fetch(tmp_path):
    provider = ms.resolve_provider("dummy://sample")
    info = provider.analyze("dummy://sample")
    assert info.source_type == MeetingSource.PUBLIC_VIDEO
    assert info.title and info.license == "CC0"
    assert "platform" in info.provenance()

    seen = []
    result = provider.fetch("dummy://sample", str(tmp_path), progress_cb=lambda p, d, t: seen.append(p))
    assert os.path.isfile(result.file_path)
    assert result.filename.endswith(".wav")
    with wave.open(result.file_path, "rb") as w:  # a real, valid WAV
        assert w.getframerate() == 16000
    assert seen and seen[-1] == 100.0


def test_registry_is_extensible():
    """A new provider is one register() call — no pipeline change."""
    before = len(ms.all_providers())

    class FakeDriveProvider(ms.MediaProvider):
        id = "fake_drive"
        source_type = MeetingSource.OTHER

        def can_handle(self, url):
            return url.startswith("drive://")

        def analyze(self, url):
            raise NotImplementedError

        def fetch(self, url, dest_dir, **kw):
            raise NotImplementedError

    ms.register(FakeDriveProvider())
    try:
        assert ms.resolve_provider("drive://folder/x").id == "fake_drive"
        assert len(ms.all_providers()) == before + 1
    finally:
        ms.registry._PROVIDERS[:] = [p for p in ms.registry._PROVIDERS if p.id != "fake_drive"]
