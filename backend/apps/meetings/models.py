"""Meetings domain models.

Design notes:

* A :class:`Meeting` is the durable, user-facing record. Its *files* live in
  separate versioned :class:`MeetingFile` rows so a corrected recording can be
  re-uploaded without destroying history.
* Technical media details (codecs, bitrate, sample rate…) live in a dedicated
  :class:`MediaMetadata` table rather than as a swarm of nullable columns.
* Upload state (per file) and processing state (per meeting) are separate
  lifecycles — see :mod:`apps.meetings.enums`.
* Background work is owned by the generic ``apps.jobs.BackgroundJob``; a
  :class:`MeetingJob` links a meeting to its job without coupling the engine to
  the meetings domain.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from .enums import (
    AIOutputKind,
    ChatRole,
    EventSource,
    MediaKind,
    MeetingEventType,
    MeetingSource,
    ProcessingStage,
    ProcessingStatus,
    SpeakerEmbeddingKind,
    StageStatus,
    UploadSessionStatus,
    UploadStatus,
)


def _dated_private_path(prefix: str, filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    random_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    now = timezone.now()
    return f"private/{prefix}/{now:%Y}/{now:%m}/{random_name}"


def meeting_file_path(instance: "MeetingFile", filename: str) -> str:
    return _dated_private_path("meetings", filename)


def thumbnail_path(instance: "MeetingFile", filename: str) -> str:
    return _dated_private_path("thumbnails", filename)


class Meeting(BaseModel):
    """A meeting record. File bytes + technical metadata live in MeetingFile."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meetings"
    )
    # Workspace hierarchy: a meeting may belong to a project (Phase 9).
    project = models.ForeignKey(
        "workspace.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=16, default="en")
    source = models.CharField(
        max_length=32, choices=MeetingSource.choices,
        default=MeetingSource.MANUAL_UPLOAD, db_index=True,
    )

    # Processing lifecycle (transcription/AI). Upload lifecycle lives on MeetingFile.
    processing_status = models.CharField(
        max_length=16, choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING, db_index=True,
    )
    is_archived = models.BooleanField(default=False, db_index=True)
    # Owner can star a meeting to pin it in Favorites.
    is_favorite = models.BooleanField(default=False, db_index=True)

    # Duration of the current recording, cached here for cheap list/dashboard reads.
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    tags = models.JSONField(default=list, blank=True)

    # Multilingual (Phase 13). Three independent concepts:
    #   meeting_language   — spoken-input hint ("" = auto-detect)
    #   transcript_language— "original" or a target code to translate the transcript into
    #   ai_language        — AI-output language ("" = same as transcript)
    meeting_language = models.CharField(max_length=16, blank=True)
    transcript_language = models.CharField(max_length=16, default="original")
    ai_language = models.CharField(max_length=16, blank=True)

    # Provenance for imported media (Phase 14). Empty for manual uploads / live.
    # source_metadata holds platform, author/channel, thumbnail, published_at,
    # license, original URL, imported_at, importer_version, etc.
    source_url = models.URLField(max_length=1024, blank=True, db_index=True)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["owner", "processing_status"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.processing_status})"

    @property
    def current_file(self) -> "MeetingFile | None":
        # Prefetch-friendly: callers can prefetch `files`.
        for f in self.files.all():
            if f.is_current:
                return f
        return None


class MeetingFile(BaseModel):
    """One uploaded version of a meeting's recording.

    Re-uploading a corrected recording creates a new version and flips
    ``is_current`` — old versions are retained for history/audit.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="files")
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)

    file = models.FileField(upload_to=meeting_file_path, null=True, blank=True)
    storage_key = models.CharField(max_length=512, blank=True)

    original_filename = models.CharField(max_length=255, blank=True)
    stored_filename = models.CharField(max_length=255, blank=True)
    file_extension = models.CharField(max_length=16, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    media_kind = models.CharField(max_length=16, choices=MediaKind.choices, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)

    upload_status = models.CharField(
        max_length=16, choices=UploadStatus.choices, default=UploadStatus.PENDING, db_index=True,
    )
    # Full structured result of validation (per-check pass/fail/skip).
    validation_report = models.JSONField(default=dict, blank=True)

    thumbnail = models.ImageField(upload_to=thumbnail_path, null=True, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("meeting", "-version")
        constraints = [
            models.UniqueConstraint(fields=["meeting", "version"], name="uniq_file_version_per_meeting"),
        ]
        indexes = [
            models.Index(fields=["meeting", "is_current"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} v{self.version}"


class MediaMetadata(BaseModel):
    """Technical media properties for a file, kept out of the Meeting model."""

    file = models.OneToOneField(
        MeetingFile, on_delete=models.CASCADE, related_name="media_metadata"
    )
    container = models.CharField(max_length=32, blank=True)
    audio_codec = models.CharField(max_length=32, blank=True)
    video_codec = models.CharField(max_length=32, blank=True)
    bitrate = models.PositiveIntegerField(null=True, blank=True)          # bits/sec
    sample_rate = models.PositiveIntegerField(null=True, blank=True)      # Hz
    channels = models.PositiveIntegerField(null=True, blank=True)
    frame_rate = models.FloatField(null=True, blank=True)                 # video fps
    width = models.PositiveIntegerField(null=True, blank=True)            # video px
    height = models.PositiveIntegerField(null=True, blank=True)           # video px
    # Anything the probe returns that we don't model as a first-class column.
    extra = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"metadata for {self.file_id}"


class MeetingJob(BaseModel):
    """Links a meeting to a generic BackgroundJob (decoupled processing engine)."""

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="meeting_jobs")
    background_job = models.OneToOneField(
        "jobs.BackgroundJob", on_delete=models.CASCADE, related_name="meeting_link"
    )

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["meeting", "-created_at"])]

    def __str__(self) -> str:
        return f"MeetingJob {self.meeting_id} → {self.background_job_id}"


class UploadSession(BaseModel):
    """Tracks an upload attempt end-to-end.

    Single-shot uploads create one of these too (foundation for future chunked /
    resumable uploads: ``received_bytes``/``received_chunks`` and ``expires_at``
    are already here to support progress recovery).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="upload_sessions"
    )
    status = models.CharField(
        max_length=16, choices=UploadSessionStatus.choices,
        default=UploadSessionStatus.INITIATED, db_index=True,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    declared_size = models.BigIntegerField(null=True, blank=True)
    received_bytes = models.BigIntegerField(default=0)
    total_chunks = models.PositiveIntegerField(null=True, blank=True)
    received_chunks = models.PositiveIntegerField(default=0)
    storage_key = models.CharField(max_length=512, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="upload_sessions"
    )

    def __str__(self) -> str:
        return f"UploadSession {self.id} ({self.status})"


class MeetingEvent(BaseModel):
    """A structured, human-facing timeline entry.

    Richer than a bare message: captures who/what triggered it (``source`` +
    audit ``created_by``), structured ``details``, and how long the step took.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, choices=MeetingEventType.choices)
    source = models.CharField(max_length=16, choices=EventSource.choices, default=EventSource.SYSTEM)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        indexes = [models.Index(fields=["meeting", "created_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.meeting_id}"


class Transcript(BaseModel):
    """The transcript-level record for a meeting's current file.

    Segments live in :class:`TranscriptSegment` (never a single blob). This row
    holds the roll-up: raw + cleaned full text, counts, timings, confidence,
    detected language, and which Whisper model produced it.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="transcripts")
    file = models.OneToOneField(
        "MeetingFile", on_delete=models.CASCADE, related_name="transcript", null=True, blank=True
    )

    raw_text = models.TextField(blank=True)
    clean_text = models.TextField(blank=True)
    word_count = models.PositiveIntegerField(default=0)
    char_count = models.PositiveIntegerField(default=0)

    detected_language = models.CharField(max_length=16, blank=True)
    language_confidence = models.FloatField(null=True, blank=True)
    avg_confidence = models.FloatField(null=True, blank=True)

    model_used = models.CharField(max_length=32, blank=True)
    provider = models.CharField(max_length=32, blank=True)
    processing_ms = models.PositiveIntegerField(null=True, blank=True)
    audio_duration_seconds = models.FloatField(null=True, blank=True)

    # Translation (Phase 13). The original text above is IMMUTABLE; a translation
    # is stored separately so the two can be switched without losing the original.
    translated_text = models.TextField(blank=True)
    target_language = models.CharField(max_length=16, blank=True)
    translation_provider = models.CharField(max_length=32, blank=True)
    translation_confidence = models.FloatField(null=True, blank=True)
    translation_ms = models.PositiveIntegerField(null=True, blank=True)

    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Transcript for {self.meeting_id} ({self.word_count} words)"

    @property
    def transcription_speed(self) -> float | None:
        """Audio-seconds transcribed per wall-clock second (>1 = faster than real time)."""
        if self.processing_ms and self.audio_duration_seconds:
            return round(self.audio_duration_seconds / (self.processing_ms / 1000), 2)
        return None


class Speaker(BaseModel):
    """A first-class speaker within ONE meeting (Phase 15).

    Deliberately per-meeting and editable; renaming it cascades to every segment.
    A voice ``embedding`` is stored now (even though cross-meeting matching is
    deferred to Phase 15B) so historical meetings need no reprocessing later. The
    optional ``voice_person`` FK links this meeting-speaker to a cross-meeting
    identity — the two are kept separate to avoid wrong identity propagation.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="speakers")
    label = models.CharField(max_length=32)                 # "Speaker 1", "Speaker 2"…
    diarization_label = models.CharField(max_length=32, blank=True)  # raw cluster id
    display_name = models.CharField(max_length=120, blank=True)
    confirmed = models.BooleanField(default=False)          # user confirmed the name

    # Editable identity metadata (speaker card).
    color = models.CharField(max_length=16, blank=True)
    role = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    avatar = models.URLField(max_length=512, blank=True)
    aliases = models.JSONField(default=list, blank=True)

    # AI name suggestion (never auto-applied — user must confirm).
    suggested_name = models.CharField(max_length=120, blank=True)
    suggested_confidence = models.FloatField(null=True, blank=True)

    # Voice embedding — persisted NOW; cross-meeting matching is Phase 15B.
    embedding = models.JSONField(null=True, blank=True)
    recognition_confidence = models.FloatField(null=True, blank=True)  # set in 15B

    # Per-meeting analytics (computed at store time; power Executive later).
    talk_time_seconds = models.FloatField(default=0.0)
    segment_count = models.PositiveIntegerField(default=0)
    word_count = models.PositiveIntegerField(default=0)
    avg_confidence = models.FloatField(null=True, blank=True)

    # Optional attribution hint — kept SEPARATE from the meeting speaker.
    workspace_person = models.CharField(max_length=120, blank=True)
    # Cross-meeting identity (Phase 15B). Optional + SET_NULL so a Speaker always
    # belongs to exactly one meeting and owns its segments; the VoicePerson link is
    # a user-confirmed overlay that never propagates into transcripts.
    voice_person = models.ForeignKey(
        "workspace.VoicePerson", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="speakers",
    )

    class Meta(BaseModel.Meta):
        ordering = ("meeting", "label")
        indexes = [models.Index(fields=["meeting", "label"])]

    def __str__(self) -> str:
        return f"{self.display_name or self.label} ({self.meeting_id})"

    @property
    def name(self) -> str:
        return self.display_name or self.label


class SpeakerEmbedding(BaseModel):
    """Multiple voice embeddings per speaker (Phase 15), persisted at processing
    time so Phase 15B VoicePerson recognition never needs to re-embed audio.

    ``Speaker.embedding`` keeps the single centroid for backwards compatibility;
    this table adds the per-segment vectors and a small set of best-N
    representatives, each carrying its own quality so 15B can pick the most
    discriminative signal without reprocessing.
    """

    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name="embeddings")
    kind = models.CharField(max_length=16, choices=SpeakerEmbeddingKind.choices)
    vector = models.JSONField()  # list[float], L2-normalized
    dimensions = models.PositiveIntegerField(default=0)
    # Provenance for kind=segment / best_n (null for the centroid).
    segment_index = models.IntegerField(null=True, blank=True)
    start_time = models.FloatField(null=True, blank=True)
    end_time = models.FloatField(null=True, blank=True)
    duration = models.FloatField(default=0.0)
    # Per-vector quality (0-100): agreement with the speaker centroid + duration.
    quality = models.FloatField(null=True, blank=True)
    rank = models.PositiveSmallIntegerField(null=True, blank=True)  # best_n ordering (1 = best)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=128, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("speaker", "kind", "rank", "segment_index")
        indexes = [
            models.Index(fields=["speaker", "kind"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} embedding for {self.speaker_id}"


class SpeakerQualitySignal(BaseModel):
    """Per-speaker acoustic/quality metrics (Phase 15), persisted now so future
    VoicePerson matching and the benchmarking suite can score match reliability
    without reprocessing. All fields are best-effort and honestly approximate
    when derived from transcript geometry rather than raw acoustics.
    """

    speaker = models.OneToOneField(Speaker, on_delete=models.CASCADE, related_name="quality")
    signal_quality = models.FloatField(null=True, blank=True)       # 0-100 composite
    noise_score = models.FloatField(null=True, blank=True)          # 0-1 (higher = noisier)
    speech_duration = models.FloatField(default=0.0)               # seconds of attributed speech
    avg_confidence = models.FloatField(null=True, blank=True)       # 0-1 mean STT confidence
    overlap_ratio = models.FloatField(null=True, blank=True)        # 0-1 of speech overlapping others
    silence_ratio = models.FloatField(null=True, blank=True)        # 0-1 silence within the span envelope
    embedding_quality_score = models.FloatField(null=True, blank=True)  # 0-100 embedding consistency
    usable_segments = models.PositiveIntegerField(default=0)        # segments long enough to embed
    total_segments = models.PositiveIntegerField(default=0)
    # True when noise/overlap/silence are geometric approximations, not measured
    # from raw acoustics — surfaced in reports so nothing is overstated (req 8).
    approximate = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        ordering = ("-signal_quality",)

    def __str__(self) -> str:
        return f"quality({self.signal_quality}) for {self.speaker_id}"


class TranscriptSegment(BaseModel):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="segments")
    index = models.PositiveIntegerField(help_text="Ordinal position within the transcript.")
    start_time = models.FloatField(help_text="Segment start, in seconds.")
    end_time = models.FloatField(help_text="Segment end, in seconds.")
    # `speaker` is a denormalized display cache; `speaker_ref` (Phase 15) is the
    # source of truth. Renaming a Speaker resyncs this string across all segments.
    speaker = models.CharField(max_length=100, blank=True)
    speaker_ref = models.ForeignKey(
        "meetings.Speaker", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="segments",
    )
    text = models.TextField()
    original_text = models.TextField(blank=True)  # preserved for restore-after-edit
    translated_text = models.TextField(blank=True)  # Phase 13: translation of `text`
    confidence = models.FloatField(null=True, blank=True)
    word_count = models.PositiveIntegerField(null=True, blank=True)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("meeting", "index")
        constraints = [
            models.UniqueConstraint(fields=["meeting", "index"], name="uniq_segment_index_per_meeting"),
        ]
        indexes = [models.Index(fields=["meeting", "index"])]

    def __str__(self) -> str:
        return f"[{self.start_time:.1f}-{self.end_time:.1f}] {self.speaker}"


class AIOutput(BaseModel):
    """Stores a single AI-generated artifact with raw + edited variants + metadata."""

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="ai_outputs")
    kind = models.CharField(max_length=32, choices=AIOutputKind.choices, db_index=True)
    raw_output = models.JSONField(default=dict)
    edited_output = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["meeting", "kind"], name="uniq_output_kind_per_meeting"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} for {self.meeting_id}"

    @property
    def current_output(self):
        return self.edited_output if self.edited_output is not None else self.raw_output


class ProcessingLog(BaseModel):
    """Immutable audit trail: one row per pipeline-stage transition."""

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="logs")
    background_job = models.ForeignKey(
        "jobs.BackgroundJob", on_delete=models.SET_NULL, related_name="logs", null=True, blank=True
    )
    stage = models.CharField(max_length=32, choices=ProcessingStage.choices)
    status = models.CharField(max_length=20, choices=StageStatus.choices)
    message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        indexes = [models.Index(fields=["meeting", "stage"])]

    def __str__(self) -> str:
        return f"{self.stage}:{self.status}"


class AIAnalysis(BaseModel):
    """A versioned AI analysis of a meeting (Phase 7).

    Every regeneration creates a new version (``is_current`` flips) — previous AI
    results are never overwritten, preserving full history. All artifacts live in
    one row (produced by a single structured LLM inference).
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="analyses")
    file = models.ForeignKey(
        MeetingFile, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)

    executive_summary = models.TextField(blank=True)
    detailed_summary = models.TextField(blank=True)
    bullet_summary = models.JSONField(default=list, blank=True)
    meeting_minutes = models.TextField(blank=True)
    action_items = models.JSONField(default=list, blank=True)
    decisions = models.JSONField(default=list, blank=True)
    risks = models.JSONField(default=list, blank=True)
    issues = models.JSONField(default=list, blank=True)
    follow_ups = models.JSONField(default=list, blank=True)
    deadlines = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=dict, blank=True)

    # Provenance / observability.
    raw_response = models.TextField(blank=True)
    parsed_response = models.JSONField(default=dict, blank=True)
    model_used = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=32, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    inference_ms = models.PositiveIntegerField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    chunks = models.PositiveIntegerField(default=1)
    output_language = models.CharField(max_length=16, blank=True)  # Phase 13: AI-output language
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("meeting", "-version")
        constraints = [
            models.UniqueConstraint(fields=["meeting", "version"], name="uniq_analysis_version_per_meeting"),
        ]
        indexes = [models.Index(fields=["meeting", "is_current"])]

    def __str__(self) -> str:
        return f"AIAnalysis v{self.version} for {self.meeting_id}"


class ChatConversation(BaseModel):
    """A chat thread scoped to a single meeting (Phase 8).

    One meeting can have many conversations; memory never crosses meetings.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=255, default="New conversation")

    class Meta(BaseModel.Meta):
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["meeting", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.title} ({self.meeting_id})"


class ChatMessage(BaseModel):
    """A turn in a per-meeting AI chat conversation."""

    conversation = models.ForeignKey(
        ChatConversation, on_delete=models.CASCADE, related_name="messages", null=True, blank=True
    )
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=16, choices=ChatRole.choices)
    content = models.TextField()
    # Legacy inline citations kept for compatibility; structured citations live
    # in MessageCitation rows.
    citations = models.JSONField(default=list, blank=True)

    # Assistant-message provenance.
    found = models.BooleanField(default=True)      # False → answer not in the meeting
    provider = models.CharField(max_length=32, blank=True)
    model_used = models.CharField(max_length=64, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    inference_ms = models.PositiveIntegerField(null=True, blank=True)
    token_count = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["meeting", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"


class MessageCitation(BaseModel):
    """A transcript-grounded citation attached to an assistant message."""

    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name="message_citations"
    )
    segment = models.ForeignKey(
        TranscriptSegment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    index = models.PositiveIntegerField()          # segment ordinal
    start_time = models.FloatField()
    end_time = models.FloatField()
    snippet = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ("message", "start_time")

    def __str__(self) -> str:
        return f"cite [{self.start_time:.1f}s] {self.snippet[:30]}"


# Phase 13 — live-recording session models (isolated from Meeting until finalize).
from apps.meetings.live.models import (  # noqa: E402,F401
    ACTIVE_LIVE_STATUSES,
    LiveMeetingSession,
    LiveSessionStatus,
    LiveTranscriptSegment,
)

# Phase 14 — universal media import session (isolated from Meeting until done).
from apps.meetings.ingest.models import (  # noqa: E402,F401
    ACTIVE_IMPORT_STATUSES,
    FAILED_IMPORT_STATUSES,
    MediaImportSession,
    MediaImportStatus,
)
