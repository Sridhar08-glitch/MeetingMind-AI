"""Global Knowledge Index (Phase 10) — now an append-only, event-sourced,
bitemporal knowledge system (Phase 11A).

Design contract (do not violate):

* Knowledge is **never overwritten**. Every change to what we know about an
  entity creates a NEW :class:`KnowledgeItem` row (``version`` + 1) and closes
  the previous row (``valid_to`` set, ``is_current`` False).
* Every mutation emits an immutable :class:`KnowledgeEvent` (CREATED, UPDATED,
  SUPERSEDED, ARCHIVED, REINDEXED, REEMBEDDED, MERGED, SPLIT, AI_CORRECTED,
  MANUAL_CORRECTED) — the complete audit history of knowledge evolution.
* Bitemporal: ``valid_from``/``valid_to`` = *valid time* (when the knowledge was
  true), ``recorded_at`` = *transaction time* (when we wrote it). This is what
  powers Time-Travel ("what did we know last month?").
* Every re-index bumps a per-owner monotonic :class:`KnowledgeVersion` (v28) —
  the reproducibility stamp shown on every AI answer.
* Which embedding model produced a vector is tracked via
  :class:`EmbeddingVersion`, so future model swaps stay auditable.
* Every AI retrieval is logged to :class:`KnowledgeRetrieval` (question,
  knowledge_version, embedding_version, retrieved items + scores, timing) so any
  answer can be reproduced and analysed.

Everything is owner-scoped (authorization boundary) — ``workspace`` is carried
denormalised for future team scoping and analytics.
"""
from __future__ import annotations

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from apps.common.managers import SoftDeleteManager, SoftDeleteQuerySet
from apps.common.models import BaseModel


class KnowledgeEntityType(models.TextChoices):
    MEETING = "meeting", "Meeting"
    SEGMENT = "segment", "Transcript Segment"
    SUMMARY = "summary", "Summary"
    DECISION = "decision", "Decision"
    TASK = "task", "Task"
    ISSUE = "issue", "Issue"
    RISK = "risk", "Risk"
    REPORT = "report", "Report"
    PROJECT = "project", "Project"
    PERSON = "person", "Person"


class ChangeSource(models.TextChoices):
    """What triggered a knowledge change (provenance of the edit)."""

    INITIAL = "initial", "Initial index"
    MEETING_REINDEX = "meeting_reindex", "Meeting re-index"
    AI_SUGGESTION = "ai_suggestion", "AI suggestion"
    MANUAL_EDIT = "manual_edit", "Manual edit"
    MERGE = "merge", "Merge"
    SPLIT = "split", "Split"
    REEMBED = "reembed", "Re-embed"


class KnowledgeEventType(models.TextChoices):
    """The immutable knowledge-evolution audit stream."""

    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    SUPERSEDED = "superseded", "Superseded"
    MERGED = "merged", "Merged"
    SPLIT = "split", "Split"
    ARCHIVED = "archived", "Archived"
    REINDEXED = "reindexed", "Re-indexed"
    REEMBEDDED = "reembedded", "Re-embedded"
    AI_CORRECTED = "ai_corrected", "AI corrected"
    MANUAL_CORRECTED = "manual_corrected", "Manually corrected"


class EmbeddingVersion(BaseModel):
    """Registry of embedding models that have produced vectors in the index.

    Referenced by every :class:`KnowledgeItem` so that, when the local embedding
    model is upgraded (e.g. nomic-embed-text → a newer local model), we still
    know exactly which model generated which vector.
    """

    STATUS_ACTIVE = "active"
    STATUS_DEPRECATED = "deprecated"

    provider = models.CharField(max_length=32)          # e.g. "ollama", "dummy"
    model = models.CharField(max_length=128)            # e.g. "nomic-embed-text"
    dimensions = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, default=STATUS_ACTIVE)
    note = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["provider", "model", "dimensions"],
                                    name="uniq_embedding_version"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.model} ({self.dimensions}d)"

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


class KnowledgeVersion(BaseModel):
    """A per-owner monotonic snapshot of the whole knowledge base (``v28``).

    Bumped on every (re-)index. Stamped onto items written under it and onto
    every AI answer, so answers are reproducible ("this used knowledge v28").
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_versions"
    )
    version = models.PositiveIntegerField()
    indexed_at = models.DateTimeField(default=timezone.now, db_index=True)
    trigger = models.CharField(max_length=32, blank=True)   # ChangeSource-ish
    reason = models.TextField(blank=True)
    embedding_version = models.ForeignKey(
        EmbeddingVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Snapshot of the workspace at this version (feature #1 surface).
    meetings = models.PositiveIntegerField(default=0)
    projects = models.PositiveIntegerField(default=0)
    tasks = models.PositiveIntegerField(default=0)
    decisions = models.PositiveIntegerField(default=0)
    risks = models.PositiveIntegerField(default=0)
    items = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "version"], name="uniq_knowledge_version"),
        ]
        indexes = [models.Index(fields=["owner", "-version"])]

    def __str__(self) -> str:
        return f"knowledge v{self.version}"


class KnowledgeItemQuerySet(SoftDeleteQuerySet):
    def current(self):
        """Only the currently-valid version of each entity."""
        return self.filter(is_current=True)

    def as_of(self, when):
        """The knowledge that was valid at ``when`` (Time-Travel)."""
        return self.filter(valid_from__lte=when).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=when)
        )


class KnowledgeItemManager(SoftDeleteManager):
    def get_queryset(self) -> KnowledgeItemQuerySet:
        return KnowledgeItemQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def current(self):
        return self.get_queryset().current()

    def as_of(self, when):
        return self.get_queryset().as_of(when)


class KnowledgeItem(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_items"
    )
    workspace = models.ForeignKey(
        "workspace.Workspace", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    project = models.ForeignKey(
        "workspace.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.CASCADE, null=True, blank=True, related_name="knowledge_items"
    )
    entity_type = models.CharField(max_length=16, choices=KnowledgeEntityType.choices, db_index=True)
    entity_id = models.UUIDField(db_index=True)

    title = models.CharField(max_length=500, blank=True)
    text = models.TextField()
    keywords = models.JSONField(default=list, blank=True)
    embedding = models.JSONField(default=list, blank=True)   # local vector

    # Provenance for citations + jump-to-transcript.
    speaker = models.CharField(max_length=255, blank=True)
    source_start_time = models.FloatField(null=True, blank=True)
    occurred_at = models.DateTimeField(db_index=True)        # when the source happened
    language = models.CharField(max_length=16, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # --- Temporal / versioning (Phase 11A) ---
    version = models.PositiveIntegerField(default=1)                 # per-entity revision
    knowledge_version = models.PositiveIntegerField(default=0, db_index=True)  # KnowledgeVersion.version
    embedding_version = models.ForeignKey(
        EmbeddingVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    valid_from = models.DateTimeField(default=timezone.now, db_index=True)   # valid time (start)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)    # valid time (end); null = open
    recorded_at = models.DateTimeField(default=timezone.now)                 # transaction time
    is_current = models.BooleanField(default=True, db_index=True)
    supersedes_version = models.PositiveIntegerField(null=True, blank=True)
    change_reason = models.TextField(blank=True)
    change_source = models.CharField(
        max_length=20, choices=ChangeSource.choices, default=ChangeSource.INITIAL
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # --- Scores (0–100; consensus/retrieval populated in 11B) ---
    confidence = models.FloatField(default=100.0)
    consensus_score = models.FloatField(null=True, blank=True)
    retrieval_score = models.FloatField(null=True, blank=True)
    confidence_breakdown = models.JSONField(default=dict, blank=True)  # {evidence, recency, agreement, coverage}

    objects = KnowledgeItemManager()

    class Meta(BaseModel.Meta):
        constraints = [
            # Versions coexist; each (entity, version) is unique.
            models.UniqueConstraint(fields=["owner", "entity_type", "entity_id", "version"],
                                    name="uniq_knowledge_entity_version"),
            # At most ONE open/current row per entity.
            models.UniqueConstraint(fields=["owner", "entity_type", "entity_id"],
                                    condition=models.Q(is_current=True, is_deleted=False),
                                    name="uniq_current_knowledge_entity"),
        ]
        indexes = [
            models.Index(fields=["owner", "entity_type"]),
            models.Index(fields=["owner", "meeting"]),
            models.Index(fields=["owner", "project"]),
            models.Index(fields=["owner", "-occurred_at"]),
            models.Index(fields=["owner", "is_current"]),
            models.Index(fields=["owner", "entity_type", "entity_id", "-version"]),
            models.Index(fields=["owner", "valid_from", "valid_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type} v{self.version}: {self.title[:40]}"


class KnowledgeEvent(BaseModel):
    """Immutable knowledge-evolution audit record. Append-only by convention —
    never expose a mutation path; services only ever create these."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_events"
    )
    item = models.ForeignKey(
        KnowledgeItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    entity_type = models.CharField(max_length=16, choices=KnowledgeEntityType.choices, db_index=True)
    entity_id = models.UUIDField(db_index=True)
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    event_type = models.CharField(max_length=20, choices=KnowledgeEventType.choices, db_index=True)
    version = models.PositiveIntegerField(null=True, blank=True)
    supersedes_version = models.PositiveIntegerField(null=True, blank=True)
    knowledge_version = models.PositiveIntegerField(default=0, db_index=True)
    change_source = models.CharField(max_length=20, choices=ChangeSource.choices, blank=True)
    change_reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["owner", "entity_type", "entity_id", "-created_at"]),
            models.Index(fields=["owner", "event_type", "-created_at"]),
            models.Index(fields=["owner", "-knowledge_version"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.entity_type} v{self.version or '-'}"


class KnowledgeRetrieval(BaseModel):
    """Retrieval provenance — exactly what an AI answer was built from, so any
    answer can be reproduced and later analysed (feeds 11B analytics)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_retrievals"
    )
    kind = models.CharField(max_length=24, default="org_chat")   # org_chat | search | copilot
    question = models.TextField(blank=True)
    knowledge_version = models.PositiveIntegerField(default=0, db_index=True)
    embedding_version = models.ForeignKey(
        EmbeddingVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    retrieved_items = models.JSONField(default=list, blank=True)  # [{entity_type, entity_id, item_id, score}]
    ranking_scores = models.JSONField(default=dict, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    llm_provider = models.CharField(max_length=32, blank=True)
    llm_model = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    found = models.BooleanField(default=True)
    answer_preview = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "kind", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.question[:40]}"


# ===========================================================================
# Phase 11B — Organizational Reasoning (consensus + conflict registries)
# ===========================================================================


class ConflictCategory(models.TextChoices):
    TECHNICAL = "technical", "Technical"
    BUSINESS = "business", "Business"
    TIMELINE = "timeline", "Timeline"
    RISK = "risk", "Risk"
    ARCHITECTURE = "architecture", "Architecture"
    SECURITY = "security", "Security"
    CUSTOMER = "customer", "Customer"
    PERFORMANCE = "performance", "Performance"
    COMPLIANCE = "compliance", "Compliance"
    GENERAL = "general", "General"


class ConflictStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    RESOLVED = "resolved", "Resolved"
    DISMISSED = "dismissed", "Dismissed"


class ConsensusTrend(models.TextChoices):
    NEW = "new", "New"
    STABLE = "stable", "Stable"
    STRENGTHENING = "strengthening", "Strengthening"
    WEAKENING = "weakening", "Weakening"
    SHIFTING = "shifting", "Shifting"


class KnowledgeConsensus(BaseModel):
    """The current organizational stance on a topic — cached so the (expensive)
    LLM reasoning isn't recomputed on every request (feature: AI Consensus)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_consensuses"
    )
    topic = models.CharField(max_length=120, db_index=True)
    category = models.CharField(max_length=16, choices=ConflictCategory.choices,
                                default=ConflictCategory.GENERAL)
    current_position = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)           # 0–100
    support_count = models.PositiveIntegerField(default=0)
    opposition_count = models.PositiveIntegerField(default=0)
    last_changed = models.DateTimeField(null=True, blank=True)
    trend = models.CharField(max_length=16, choices=ConsensusTrend.choices, default=ConsensusTrend.NEW)
    stability_score = models.FloatField(default=100.0)    # 0–100
    reason = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)  # {decision_ids, meeting_ids}
    knowledge_version = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "topic"], name="uniq_knowledge_consensus"),
        ]
        indexes = [models.Index(fields=["owner", "topic"])]

    def __str__(self) -> str:
        return f"consensus[{self.topic}]: {self.current_position[:40]}"


class KnowledgeConsensusRevision(BaseModel):
    """An immutable point in a consensus's evolution (feature: Consensus
    Evolution — Jan JWT → Mar OAuth2 → Jun OIDC → current)."""

    consensus = models.ForeignKey(
        KnowledgeConsensus, on_delete=models.CASCADE, related_name="revisions"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    position = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    support_count = models.PositiveIntegerField(default=0)
    opposition_count = models.PositiveIntegerField(default=0)
    knowledge_version = models.PositiveIntegerField(default=0)
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta(BaseModel.Meta):
        ordering = ("recorded_at",)
        indexes = [models.Index(fields=["consensus", "recorded_at"])]

    def __str__(self) -> str:
        return f"{self.position[:40]} @{self.recorded_at:%Y-%m}"


class KnowledgeConflict(BaseModel):
    """A registry of detected contradictions — categorized + resolvable, so
    conflicts aren't re-detected from scratch and can be tracked to resolution."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="knowledge_conflicts"
    )
    topic = models.CharField(max_length=120, db_index=True)
    category = models.CharField(max_length=16, choices=ConflictCategory.choices,
                                default=ConflictCategory.GENERAL, db_index=True)
    status = models.CharField(max_length=16, choices=ConflictStatus.choices,
                              default=ConflictStatus.OPEN, db_index=True)
    positions = models.JSONField(default=list, blank=True)   # [{decision_id, meeting_id, ...}]
    decision_count = models.PositiveIntegerField(default=0)
    meeting_count = models.PositiveIntegerField(default=0)

    consensus = models.ForeignKey(
        KnowledgeConsensus, on_delete=models.SET_NULL, null=True, blank=True, related_name="conflicts"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_decision = models.ForeignKey(
        "workspace.Decision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "topic"], name="uniq_knowledge_conflict"),
        ]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "category"]),
        ]

    def __str__(self) -> str:
        return f"conflict[{self.category}] {self.topic} ({self.status})"


# ===========================================================================
# Phase 11C — Executive Intelligence (materialized; never recomputed per request)
# ===========================================================================


class HealthStatus(models.TextChoices):
    EXCELLENT = "excellent", "Excellent"
    GOOD = "good", "Good"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class AlertSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class AlertStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    RESOLVED = "resolved", "Resolved"
    DISMISSED = "dismissed", "Dismissed"


class AlertType(models.TextChoices):
    KNOWLEDGE_CONFLICT = "knowledge_conflict", "Knowledge conflict"
    DECISION_INSTABILITY = "decision_instability", "Decision instability"
    REPEATED_BLOCKER = "repeated_blocker", "Repeated blocker"
    OVERDUE_RISK = "overdue_risk", "Overdue risk"
    DECLINING_HEALTH = "declining_health", "Declining project health"
    CUSTOMER_COMPLAINT = "customer_complaint", "Repeated customer complaint"
    AI_CONFIDENCE_DROP = "ai_confidence_drop", "AI confidence drop"
    KNOWLEDGE_OUTDATED = "knowledge_outdated", "Knowledge becoming outdated"


class RecommendationStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    IN_PROGRESS = "in_progress", "In progress"
    DONE = "done", "Done"
    DISMISSED = "dismissed", "Dismissed"


class TrendGranularity(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class _SnapshotBase(BaseModel):
    """Shared reproducibility stamp for every materialized snapshot."""

    snapshot_version = models.PositiveIntegerField(default=0)     # monotonic per owner
    knowledge_version = models.PositiveIntegerField(default=0)
    consensus_version = models.PositiveIntegerField(default=0)
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    processing_ms = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        abstract = True


class OrganizationSnapshot(_SnapshotBase):
    """Top-scope materialized executive view for an owner's organization. Rolls
    up stored ProjectSnapshots (cheap) rather than recomputing per project."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_snapshots"
    )
    overall_health_score = models.FloatField(default=0.0)
    overall_health_status = models.CharField(max_length=12, choices=HealthStatus.choices,
                                              default=HealthStatus.GOOD)
    workspace_score = models.FloatField(default=0.0)
    health = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    score = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    analytics = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    organization_insights = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    knowledge_freshness = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="uniq_organization_snapshot"),
        ]

    def __str__(self) -> str:
        return f"org snapshot v{self.snapshot_version} [{self.owner_id}] {self.overall_health_status}"


class ProjectSnapshot(_SnapshotBase):
    """Per-project materialized health/score — a single project's meeting change
    only re-materializes this row (+ the org rollup)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_snapshots"
    )
    project = models.ForeignKey(
        "workspace.Project", on_delete=models.CASCADE, related_name="snapshots"
    )
    overall_health_score = models.FloatField(default=0.0)
    overall_health_status = models.CharField(max_length=12, choices=HealthStatus.choices,
                                              default=HealthStatus.GOOD)
    memory_score = models.JSONField(default=dict, blank=True)    # Organizational Memory Score
    signals = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "project"], name="uniq_project_snapshot"),
        ]
        indexes = [models.Index(fields=["owner", "-overall_health_score"])]

    def __str__(self) -> str:
        return f"project snapshot [{self.project_id}] {self.overall_health_status}"


class ExecutiveRecommendation(_SnapshotBase):
    """A normalized, explainable recommendation (not embedded in a JSON blob)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_recommendations"
    )
    key = models.CharField(max_length=200, db_index=True)   # stable dedup key
    priority = models.CharField(max_length=12, blank=True)
    recommendation = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(default=0.0)
    impact = models.JSONField(default=dict, blank=True)
    related_projects = models.JSONField(default=list, blank=True)
    consensus = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=RecommendationStatus.choices,
                              default=RecommendationStatus.OPEN, db_index=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "key"], name="uniq_executive_recommendation"),
        ]

    def __str__(self) -> str:
        return f"rec[{self.priority}] {self.recommendation[:40]}"


class ExecutiveExplanation(_SnapshotBase):
    """One explanation per metric card — every score links here for its 'Why?'."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_explanations"
    )
    scope = models.CharField(max_length=48, default="organization")   # organization | project:<id>
    metric_key = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=128, blank=True)
    value = models.FloatField(null=True, blank=True)
    formula = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "scope", "metric_key"],
                                    name="uniq_executive_explanation"),
        ]

    def __str__(self) -> str:
        return f"why[{self.scope}] {self.metric_key}={self.value}"


class ExecutiveTrendPoint(BaseModel):
    """Materialized daily/weekly/monthly trend points so graphs are instant."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_trend_points"
    )
    granularity = models.CharField(max_length=8, choices=TrendGranularity.choices, db_index=True)
    metric = models.CharField(max_length=40, db_index=True)
    period_start = models.DateTimeField(db_index=True)
    value = models.FloatField(default=0.0)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "granularity", "metric", "period_start"],
                                    name="uniq_executive_trend_point"),
        ]
        indexes = [models.Index(fields=["owner", "metric", "granularity", "period_start"])]

    def __str__(self) -> str:
        return f"trend[{self.granularity}] {self.metric} @{self.period_start:%Y-%m-%d}={self.value}"


class ExecutivePrediction(_SnapshotBase):
    """A materialized heuristic prediction (health likely to fall to X in N days)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_predictions"
    )
    metric = models.CharField(max_length=40, db_index=True)
    current_value = models.FloatField(default=0.0)
    expected_value = models.FloatField(default=0.0)
    horizon_days = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(default=0.0)
    message = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["owner", "metric", "-generated_at"])]

    def __str__(self) -> str:
        return f"predict {self.metric}: {self.current_value}→{self.expected_value}"


class ExecutiveMetricSnapshot(BaseModel):
    """Append-only time series of headline metrics — powers Executive History,
    trend charts and predictive health without recomputing anything."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_metrics"
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    knowledge_version = models.PositiveIntegerField(default=0)

    overall_health = models.FloatField(default=0.0)
    workspace_score = models.FloatField(default=0.0)
    knowledge_items = models.PositiveIntegerField(default=0)
    meetings = models.PositiveIntegerField(default=0)
    tasks_total = models.PositiveIntegerField(default=0)
    tasks_done = models.PositiveIntegerField(default=0)
    tasks_blocked = models.PositiveIntegerField(default=0)
    open_risks = models.PositiveIntegerField(default=0)
    open_issues = models.PositiveIntegerField(default=0)
    decisions = models.PositiveIntegerField(default=0)
    open_conflicts = models.PositiveIntegerField(default=0)
    avg_confidence = models.FloatField(default=0.0)
    decision_stability = models.FloatField(default=0.0)
    ai_retrievals = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        ordering = ("recorded_at",)
        indexes = [models.Index(fields=["owner", "recorded_at"])]

    def __str__(self) -> str:
        return f"metrics [{self.owner_id}] @{self.recorded_at:%Y-%m-%d %H:%M}"


class ExecutiveAlert(BaseModel):
    """A materialized executive alert (deduped by ``key``, resolvable)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="executive_alerts"
    )
    key = models.CharField(max_length=200, db_index=True)   # stable dedup key
    alert_type = models.CharField(max_length=24, choices=AlertType.choices, db_index=True)
    severity = models.CharField(max_length=12, choices=AlertSeverity.choices, default=AlertSeverity.WARNING)
    status = models.CharField(max_length=12, choices=AlertStatus.choices, default=AlertStatus.OPEN, db_index=True)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    knowledge_version = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["owner", "key"], name="uniq_executive_alert"),
        ]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "alert_type"]),
        ]

    def __str__(self) -> str:
        return f"alert[{self.alert_type}/{self.severity}] {self.title[:40]}"
