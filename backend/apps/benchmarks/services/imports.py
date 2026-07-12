"""Seed benchmark suites (req 1, 2).

* PUBLIC suite — materialise the curated catalogue as recordings (public-approximate
  ground truth) and import each through the existing Phase 14 framework.
* USER suite — turn a user's own already-processed meeting into a recording with
  user-verified ground truth (expected count / participants / meeting type).

Nothing here duplicates the import or AI pipeline — public recordings funnel into
``ingest.create_import`` and the normal meeting pipeline; user recordings just
reference a meeting that already ran.
"""
from __future__ import annotations

from ..enums import (
    BenchmarkDatasetKind,
    GroundTruthType,
    RecordingFormat,
    RecordingStatus,
)
from ..models import BenchmarkDataset, BenchmarkRecording
from . import public_catalog

PUBLIC_DATASET_SLUG = "public-benchmark-suite"


def seed_public_dataset(owner, *, limit: int | None = None) -> BenchmarkDataset:
    """Create/refresh the owner's public benchmark dataset + its recordings.

    Recordings are created in PENDING state (not imported yet) so the caller can
    review the catalogue and trigger imports explicitly. Idempotent by (dataset,
    source_url + name).
    """
    dataset, _ = BenchmarkDataset.objects.get_or_create(
        owner=owner,
        slug=PUBLIC_DATASET_SLUG,
        defaults={
            "kind": BenchmarkDatasetKind.PUBLIC,
            "name": "Public Benchmark Suite",
            "description": (
                "Legally-accessible recordings across formats and languages. "
                "Ground truth is APPROXIMATE (public estimates), not verified labels."
            ),
        },
    )
    for entry in public_catalog.catalog(limit):
        BenchmarkRecording.objects.get_or_create(
            dataset=dataset,
            owner=owner,
            name=entry["name"],
            defaults={
                "format": entry.get("format", RecordingFormat.OTHER),
                "language": entry.get("language", ""),
                "source_url": entry.get("source_url", ""),
                "source_kind": "public",
                "ground_truth_type": GroundTruthType.PUBLIC_APPROXIMATE,
                "expected_speaker_count": entry.get("approx_speaker_count"),
                "notes": entry.get("notes", ""),
                "status": RecordingStatus.PENDING,
            },
        )
    return dataset


def import_recording(recording: BenchmarkRecording, *, requested_media: str = "audio"):
    """Kick off the Phase 14 import for one public recording. Returns the
    MediaImportSession (or None if the recording has no URL)."""
    from apps.meetings.enums import DuplicateAction
    from apps.meetings.ingest import service as ingest

    if not recording.source_url:
        recording.status = RecordingStatus.SKIPPED
        recording.status_detail = "no source url"
        recording.save(update_fields=["status", "status_detail", "updated_at"])
        return None

    try:
        session = ingest.create_import(
            recording.owner,
            url=recording.source_url,
            requested_media=requested_media,
            meeting_language=recording.language,
            on_duplicate=DuplicateAction.KEEP_BOTH,  # benchmark copies stay independent
            title=recording.name,
        )
    except Exception as exc:  # noqa: BLE001 — surface the failure honestly on the row
        recording.status = RecordingStatus.FAILED
        recording.status_detail = f"import refused: {exc}"[:255]
        recording.save(update_fields=["status", "status_detail", "updated_at"])
        return None

    recording.import_session = session
    recording.status = RecordingStatus.IMPORTING
    recording.status_detail = ""
    recording.save(update_fields=["import_session", "status", "status_detail", "updated_at"])
    return session


def create_user_recording_from_meeting(
    owner,
    *,
    meeting,
    dataset: BenchmarkDataset | None = None,
    name: str = "",
    format: str = RecordingFormat.MEETING,
    expected_speaker_count: int | None = None,
    known_participants: list[str] | None = None,
    meeting_type: str = "",
    reference_segments: list[dict] | None = None,
) -> BenchmarkRecording:
    """Register a user's own processed meeting as a high-confidence benchmark
    recording (req 2). Ground truth is USER_VERIFIED — distinct from the
    public-approximate suite (req 8)."""
    if meeting.owner_id != owner.id:
        raise PermissionError("Meeting does not belong to this user.")

    if dataset is None:
        dataset, _ = BenchmarkDataset.objects.get_or_create(
            owner=owner, slug="my-benchmark-suite",
            defaults={"kind": BenchmarkDatasetKind.USER, "name": "My Benchmark Suite"},
        )

    ready = str(getattr(meeting, "processing_status", "")) == "completed"
    return BenchmarkRecording.objects.create(
        dataset=dataset,
        owner=owner,
        name=name or meeting.title,
        format=format,
        language=meeting.language,
        source_kind="upload",
        ground_truth_type=GroundTruthType.USER_VERIFIED,
        expected_speaker_count=expected_speaker_count,
        known_participants=known_participants or [],
        meeting_type=meeting_type,
        reference_segments=reference_segments or [],
        meeting=meeting,
        status=RecordingStatus.READY if ready else RecordingStatus.PROCESSING,
    )
