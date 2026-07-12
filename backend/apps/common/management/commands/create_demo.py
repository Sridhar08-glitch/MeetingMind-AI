"""`python manage.py create_demo` — build/reset the MeetingMind demo workspace.

Seeds a single demo account with a full, realistic dataset (meetings with audio AND
video, transcripts, AI analyses, chat, workspace items, knowledge index, executive
dashboards) so an evaluator can experience the whole product with no uploads.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


class Command(BaseCommand):
    help = "Create or reset the MeetingMind AI demo workspace with realistic seeded data."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding the MeetingMind AI demo workspace…"))
        counts = seed_demo(log=self.stdout.write)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo workspace is ready."))
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("  Login:"))
        self.stdout.write(f"    email:    {DEMO_EMAIL}")
        self.stdout.write(f"    password: {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("  Seeded:"))
        for key, val in counts.items():
            self.stdout.write(f"    {key:<14} {val}")
