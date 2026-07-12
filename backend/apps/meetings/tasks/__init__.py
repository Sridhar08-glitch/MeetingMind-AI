"""Meetings task package.

Meeting processing now runs through the generic engine
(``apps.jobs.tasks.run_pipeline_job``) driving the ``meeting_processing``
pipeline. The stages live in :mod:`apps.meetings.pipeline`.

Phase 14 adds media import as its own Celery task; re-exported here so Celery's
``autodiscover_tasks()`` (which imports ``apps.meetings.tasks``) registers it.
"""
from apps.meetings.ingest.tasks import run_media_import  # noqa: F401

