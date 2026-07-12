"""Seed the public benchmark suite for a user and optionally import the media.

    python manage.py seed_public_benchmark --user demo@meetingmind.ai
    python manage.py seed_public_benchmark --user demo@meetingmind.ai --import --limit 3

Import routes each catalogue entry through the Phase 14 framework (yt-dlp / direct
/ RSS), which refuses anything private/DRM. Public ground truth is APPROXIMATE —
this command never presents it as exact. Requires a running Celery worker (+ deps)
for the imports to actually download and process.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.benchmarks.services import imports


class Command(BaseCommand):
    help = "Create the public benchmark dataset for a user (optionally importing the media)."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Owner email.")
        parser.add_argument("--limit", type=int, default=None, help="Only seed the first N entries.")
        parser.add_argument("--import", action="store_true", dest="do_import",
                            help="Also start importing each recording via Phase 14.")

    def handle(self, *args, **opts):
        try:
            owner = User.objects.get(email=opts["user"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user {opts['user']!r}") from exc

        dataset = imports.seed_public_dataset(owner, limit=opts["limit"])
        recordings = list(dataset.recordings.all())
        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{dataset.name}' with {len(recordings)} recording(s) "
            f"(ground truth: PUBLIC-APPROXIMATE)."
        ))

        if opts["do_import"]:
            for rec in recordings:
                session = imports.import_recording(rec)
                state = f"session {session.id}" if session else f"skipped/failed ({rec.status})"
                self.stdout.write(f"  - {rec.name}: {state}")
            self.stdout.write("Imports dispatched. Watch /api/benchmarks/recordings/ for status.")
        else:
            self.stdout.write("Run with --import to download + process the recordings.")
