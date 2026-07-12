"""`python manage.py generate_demo_media` — build the REAL demo media files.

Synthesises a real audio (WAV) or video (MP4) recording for every scripted demo
meeting using the local Windows SAPI voices + ffmpeg. Files are cached under
``backend/demo_media/``; pass ``--force`` to rebuild them all.

Run this once before ``create_demo`` (which uploads these files through the real
Faster-Whisper → Ollama pipeline).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common import demo_media


class Command(BaseCommand):
    help = "Generate the real demo audio/video files (local TTS + ffmpeg)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Rebuild every file even if it already exists.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Generating real demo media (local TTS + ffmpeg)…"))
        rows = demo_media.generate_all(force=options["force"], log=self.stdout.write)
        audio = sum(1 for r in rows if r["media"] == "audio")
        video = sum(1 for r in rows if r["media"] == "video")
        total_mb = sum(r["size_bytes"] for r in rows) / 1024 / 1024
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Generated {len(rows)} files ({audio} audio, {video} video, {total_mb:.1f} MB)."
        ))
