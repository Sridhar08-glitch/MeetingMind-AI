"""Standalone MeetingMind AI demo seeder.

Populates a demo account with a complete, realistic workspace so anyone can explore
the product without uploading anything.

Usage (from the repo root, with the backend venv active or by full path):

    python scripts/create_demo.py

Equivalent to `python manage.py create_demo` run from the backend directory.
"""
from __future__ import annotations

import os
import sys

# Make the Django project importable and configured.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "backend")
sys.path.insert(0, os.path.abspath(_BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.common.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo  # noqa: E402


def main() -> None:
    print("Seeding the MeetingMind AI demo workspace…")
    counts = seed_demo(log=print)
    print("\nDemo workspace is ready.")
    print(f"\n  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}\n")
    for key, val in counts.items():
        print(f"    {key:<14} {val}")


if __name__ == "__main__":
    main()
