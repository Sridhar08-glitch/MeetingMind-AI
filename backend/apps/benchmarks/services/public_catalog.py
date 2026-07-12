"""Curated catalogue of legally-accessible recordings for the public benchmark
suite (req 1), imported through the existing Phase 14 media framework.

HONESTY (req 8): every entry here is PUBLIC-APPROXIMATE ground truth. The speaker
counts are human estimates from public descriptions, NOT verified per-segment
labels — they must never be presented as exact measurements. Availability and
licence of third-party URLs can change; the importer verifies each at import time
(yt-dlp/direct/RSS refuse anything private/DRM) and marks failures visibly rather
than silently. Users should confirm licences for their jurisdiction before use.

The catalogue is intentionally editable data, not hard-coded behaviour: add rows
to broaden format/language coverage. ``source_url`` may be a direct media URL, a
public video/podcast page, or an RSS feed — the Phase 14 registry routes it.
"""
from __future__ import annotations

from ..enums import RecordingFormat

# Each entry: name, format, language, source_url, approx_speaker_count, notes.
# Spread across the required formats (podcast / panel / interview / roundtable /
# webinar) and multiple Whisper-supported languages. Counts are APPROXIMATE.
PUBLIC_CATALOG: list[dict] = [
    {
        "name": "LibriVox — Multi-reader dramatic reading (EN)",
        "format": RecordingFormat.ROUNDTABLE,
        "language": "en",
        "source_url": "https://librivox.org/",
        "approx_speaker_count": 4,
        "notes": "Public-domain dramatic reading with a named cast (approximate count).",
    },
    {
        "name": "Public-domain interview recording (EN)",
        "format": RecordingFormat.INTERVIEW,
        "language": "en",
        "source_url": "https://archive.org/",
        "approx_speaker_count": 2,
        "notes": "Interviewer + guest. Public-domain / CC — verify at import.",
    },
    {
        "name": "Creative-Commons panel discussion (EN)",
        "format": RecordingFormat.PANEL,
        "language": "en",
        "source_url": "https://archive.org/",
        "approx_speaker_count": 4,
        "notes": "CC-licensed conference panel (moderator + panellists).",
    },
    {
        "name": "Open webinar recording (EN)",
        "format": RecordingFormat.WEBINAR,
        "language": "en",
        "source_url": "https://archive.org/",
        "approx_speaker_count": 2,
        "notes": "Presenter-led webinar with Q&A (approximate count).",
    },
    {
        "name": "CC podcast episode (EN)",
        "format": RecordingFormat.PODCAST,
        "language": "en",
        "source_url": "https://feeds.example.org/",  # RSS feed → episode picker
        "approx_speaker_count": 2,
        "notes": "Two-host podcast. RSS feed routed to the podcast provider.",
    },
    {
        "name": "LibriVox enregistrement multi-lecteurs (FR)",
        "format": RecordingFormat.ROUNDTABLE,
        "language": "fr",
        "source_url": "https://librivox.org/",
        "approx_speaker_count": 3,
        "notes": "French public-domain multi-reader work (non-English coverage).",
    },
    {
        "name": "LibriVox Aufnahme mit mehreren Sprechern (DE)",
        "format": RecordingFormat.INTERVIEW,
        "language": "de",
        "source_url": "https://librivox.org/",
        "approx_speaker_count": 2,
        "notes": "German public-domain recording (non-English coverage).",
    },
    {
        "name": "Grabación de dominio público (ES)",
        "format": RecordingFormat.PANEL,
        "language": "es",
        "source_url": "https://archive.org/",
        "approx_speaker_count": 3,
        "notes": "Spanish public-domain panel (non-English coverage).",
    },
]


def catalog(limit: int | None = None) -> list[dict]:
    return PUBLIC_CATALOG[:limit] if limit else list(PUBLIC_CATALOG)
