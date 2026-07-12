"""Enumerations for the MeetingMind workspace (native productivity suite)."""
from __future__ import annotations

from django.db import models


class ApprovalStatus(models.TextChoices):
    """AI suggestion lifecycle (human-in-the-loop, richer audit trail).

    pending → needs_review (low confidence) → edited (user changed it) →
    approved → converted (real record created); or rejected; or archived.
    """

    PENDING = "pending", "Pending review"
    NEEDS_REVIEW = "needs_review", "Needs review"
    EDITED = "edited", "Edited"
    APPROVED = "approved", "Approved"
    CONVERTED = "converted", "Converted"
    REJECTED = "rejected", "Rejected"
    ARCHIVED = "archived", "Archived"


OPEN_SUGGESTION_STATUSES = (
    ApprovalStatus.PENDING, ApprovalStatus.NEEDS_REVIEW, ApprovalStatus.EDITED,
)


class ActivityVerb(models.TextChoices):
    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    STATUS_CHANGED = "status_changed", "Status changed"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    COMMENTED = "commented", "Commented"
    ATTACHED = "attached", "Attached a file"
    MERGED = "merged", "Merged"


class Confidence(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class SuggestionType(models.TextChoices):
    TASK = "task", "Task"
    ISSUE = "issue", "Issue"
    DECISION = "decision", "Decision"
    RISK = "risk", "Risk"
    FOLLOW_UP = "follow_up", "Follow-up"


class VoiceMatchTier(models.TextChoices):
    """Confidence tiers for a cross-meeting voice match (Phase 15B). Tiered — not a
    single threshold — to minimise false positives. Nothing links automatically."""

    AUTO_HIGHLIGHT = "auto_highlight", "Almost certain"   # >= 98%
    HIGHLY_LIKELY = "highly_likely", "Highly likely"      # 95–98%
    POSSIBLE = "possible", "Possible"                     # 90–95%
    NONE = "none", "Below suggestion threshold"           # < 90% (not suggested)


class VoicePersonEventType(models.TextChoices):
    """Immutable audit trail for a VoicePerson identity (Phase 15B)."""

    CREATED = "created", "Created"
    LINKED = "linked", "Speaker linked"
    UNLINKED = "unlinked", "Speaker unlinked"
    CONFIRMED = "confirmed", "Confirmed"
    RENAMED = "renamed", "Renamed"
    EDITED = "edited", "Edited"
    MERGED = "merged", "Merged"
    SPLIT = "split", "Split"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class Severity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class TaskStatus(models.TextChoices):
    BACKLOG = "backlog", "Backlog"
    TODO = "todo", "To Do"
    IN_PROGRESS = "in_progress", "In Progress"
    BLOCKED = "blocked", "Blocked"
    REVIEW = "review", "Review"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


# Kanban column order.
TASK_BOARD_COLUMNS = [
    TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.IN_PROGRESS,
    TaskStatus.BLOCKED, TaskStatus.REVIEW, TaskStatus.COMPLETED, TaskStatus.CANCELLED,
]
DONE_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


class TaskCategory(models.TextChoices):
    GENERAL = "general", "General"
    DEVELOPMENT = "development", "Development"
    DESIGN = "design", "Design"
    RESEARCH = "research", "Research"
    OPERATIONS = "operations", "Operations"
    ADMIN = "admin", "Admin"


class IssueType(models.TextChoices):
    BUG = "bug", "Bug"
    PROBLEM = "problem", "Problem"
    TECH_DEBT = "tech_debt", "Technical Debt"
    CUSTOMER = "customer", "Customer Issue"
    SECURITY = "security", "Security Issue"
    PERFORMANCE = "performance", "Performance Issue"


class IssueStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"
    WONT_FIX = "wont_fix", "Won't Fix"


class DecisionStatus(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    ACCEPTED = "accepted", "Accepted"
    IMPLEMENTED = "implemented", "Implemented"
    REVERSED = "reversed", "Reversed"


class RiskStatus(models.TextChoices):
    OPEN = "open", "Open"
    MITIGATING = "mitigating", "Mitigating"
    MITIGATED = "mitigated", "Mitigated"
    ACCEPTED = "accepted", "Accepted"
    CLOSED = "closed", "Closed"


class FollowUpStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    MISSED = "missed", "Missed"
    OVERDUE = "overdue", "Overdue"


class ProjectStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On Hold"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class ReportType(models.TextChoices):
    DAILY = "daily", "Daily Report"
    WEEKLY = "weekly", "Weekly Report"
    SPRINT = "sprint", "Sprint Report"
    EXECUTIVE = "executive", "Executive Report"
    TECHNICAL = "technical", "Technical Report"
    CUSTOMER = "customer", "Customer Report"
    PROGRESS = "progress", "Progress Report"
    # AI emails (same generation path, different prompt intent).
    EMAIL_FOLLOW_UP = "email_follow_up", "Follow-up Email"
    EMAIL_RECAP = "email_recap", "Meeting Recap Email"
    EMAIL_STATUS = "email_status", "Status Update Email"
    EMAIL_CLIENT = "email_client", "Client Update Email"
    EMAIL_INTERNAL = "email_internal", "Internal Update Email"


class NotificationType(models.TextChoices):
    NEW_TASK = "new_task", "New AI Task"
    OVERDUE_TASK = "overdue_task", "Overdue Task"
    UPCOMING_DEADLINE = "upcoming_deadline", "Upcoming Deadline"
    NEW_RISK = "new_risk", "New Risk"
    COMPLETED_TASK = "completed_task", "Completed Task"
    BLOCKED_TASK = "blocked_task", "Blocked Task"
    NEW_ISSUE = "new_issue", "New Issue"
