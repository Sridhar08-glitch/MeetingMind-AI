"""Enumerations for the speaker-diarization benchmarking suite (Phase 15)."""
from __future__ import annotations

from django.db import models


class BenchmarkDatasetKind(models.TextChoices):
    """A dataset's provenance drives how much to trust its ground truth (req 8)."""

    PUBLIC = "public", "Public"  # legally-accessible recordings, approximate truth
    USER = "user", "User"        # user's own meetings, highest-confidence truth


class GroundTruthType(models.TextChoices):
    """How the expected speaker count / identities were established.

    Public videos/podcasts are APPROXIMATE unless a human verified them; user
    recordings with known participants are the highest-confidence benchmark.
    """

    USER_VERIFIED = "user_verified", "User verified"
    PUBLIC_APPROXIMATE = "public_approximate", "Public approximate"
    UNKNOWN = "unknown", "Unknown"


class RecordingFormat(models.TextChoices):
    PODCAST = "podcast", "Podcast"
    PANEL = "panel", "Panel discussion"
    INTERVIEW = "interview", "Interview"
    ROUNDTABLE = "roundtable", "Round-table discussion"
    WEBINAR = "webinar", "Webinar"
    MEETING = "meeting", "Meeting"
    OTHER = "other", "Other"


class RecordingStatus(models.TextChoices):
    """Ingestion state of a benchmark recording (mirrors the import/pipeline)."""

    PENDING = "pending", "Pending"
    IMPORTING = "importing", "Importing"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"       # meeting processed → transcript/diarization available
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class BenchmarkRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class OverlapHandling(models.TextChoices):
    """How overlapping speech is attributed when scoring/clustering."""

    LONGEST = "longest", "Assign to longest overlap"
    IGNORE = "ignore", "Ignore overlapped segments"
    SPLIT = "split", "Split across speakers"
