"""Celery entry point for media import — download in the background, then hand
off to the existing pipeline. Kept thin; all logic lives in ``service.run_import``.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("meetingmind.ingest")


@shared_task(
    name="meetings.run_media_import",
    acks_late=True,
    max_retries=0,
    ignore_result=True,
)
def run_media_import(session_id: str) -> None:
    from .service import run_import

    run_import(session_id)
