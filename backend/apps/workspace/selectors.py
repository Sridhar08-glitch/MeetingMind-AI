"""Read-side: analytics, unified search, and meeting timeline."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.meetings.models import AIAnalysis, Meeting
from apps.workspace.enums import DONE_TASK_STATUSES, IssueStatus, RiskStatus, TaskStatus
from apps.workspace.models import Decision, Issue, Project, Report, Risk, Task


# --- analytics --------------------------------------------------------------
def workspace_analytics(owner) -> dict:
    today = timezone.now().date()
    soon = today + timedelta(days=7)
    tasks = Task.objects.filter(owner=owner)
    by_status = {row["status"]: row["n"] for row in tasks.values("status").annotate(n=Count("id"))}
    total = sum(by_status.values())
    completed = by_status.get(TaskStatus.COMPLETED, 0)
    open_tasks = total - completed - by_status.get(TaskStatus.CANCELLED, 0)
    overdue = tasks.filter(due_date__lt=today).exclude(status__in=DONE_TASK_STATUSES).count()

    # Most discussed topics across the owner's current analyses.
    topics: Counter = Counter()
    for a in AIAnalysis.objects.filter(meeting__owner=owner, is_current=True):
        topics.update(t for t in a.keywords.get("topics", []) if t)

    meetings = Meeting.objects.filter(owner=owner).count()
    return {
        "open_tasks": open_tasks,
        "completed_tasks": completed,
        "blocked_tasks": by_status.get(TaskStatus.BLOCKED, 0),
        "overdue_tasks": overdue,
        "task_completion_rate": round((completed / total) * 100, 1) if total else 0.0,
        "total_tasks": total,
        "task_status_breakdown": by_status,
        "open_issues": Issue.objects.filter(owner=owner).exclude(
            status__in=[IssueStatus.RESOLVED, IssueStatus.CLOSED, IssueStatus.WONT_FIX]).count(),
        "open_risks": Risk.objects.filter(owner=owner, status=RiskStatus.OPEN).count(),
        "decision_count": Decision.objects.filter(owner=owner).count(),
        "meeting_count": meetings,
        "tasks_per_meeting": round(total / meetings, 1) if meetings else 0.0,
        "upcoming_deadlines": tasks.filter(
            due_date__gte=today, due_date__lte=soon).exclude(status__in=DONE_TASK_STATUSES).count(),
        "most_discussed_topics": [{"topic": t, "count": c} for t, c in topics.most_common(10)],
    }


def dashboard(owner) -> dict:
    today = timezone.now().date()
    tasks = Task.objects.filter(owner=owner)
    upcoming = list(
        tasks.filter(due_date__gte=today).exclude(status__in=DONE_TASK_STATUSES)
        .order_by("due_date").values("id", "title", "due_date")[:5]
    )
    return {
        "analytics": workspace_analytics(owner),
        "recent_meetings": list(
            Meeting.objects.filter(owner=owner).order_by("-created_at")
            .values("id", "title", "processing_status", "created_at")[:5]
        ),
        "upcoming_deadlines": upcoming,
        "unread_notifications": owner.notifications.filter(is_read=False).count()
        if hasattr(owner, "notifications") else 0,
    }


# --- unified search ---------------------------------------------------------
def unified_search(owner, query: str) -> dict:
    q = (query or "").strip()
    if not q:
        return {k: [] for k in ("meetings", "tasks", "issues", "risks", "decisions", "projects", "reports")}
    return {
        "meetings": list(Meeting.objects.filter(owner=owner)
                         .filter(Q(title__icontains=q) | Q(description__icontains=q))
                         .values("id", "title")[:10]),
        "tasks": list(Task.objects.filter(owner=owner, title__icontains=q).values("id", "title", "status")[:10]),
        "issues": list(Issue.objects.filter(owner=owner, title__icontains=q).values("id", "title", "severity")[:10]),
        "risks": list(Risk.objects.filter(owner=owner, risk__icontains=q).values("id", "risk", "severity")[:10]),
        "decisions": list(Decision.objects.filter(owner=owner, decision__icontains=q).values("id", "decision")[:10]),
        "projects": list(Project.objects.filter(owner=owner, name__icontains=q).values("id", "name")[:10]),
        "reports": list(Report.objects.filter(owner=owner)
                        .filter(Q(title__icontains=q) | Q(content__icontains=q))
                        .values("id", "title", "report_type")[:10]),
    }


def semantic_search(owner, query: str, *, k: int = 10) -> list[dict]:
    """Hybrid semantic ranking over the owner's entities (local embeddings)."""
    from apps.meetings.services.embeddings import cosine, get_embedding_provider

    candidates: list[tuple[str, str, str]] = []  # (type, id, text)
    for m in Meeting.objects.filter(owner=owner).values("id", "title"):
        candidates.append(("meeting", str(m["id"]), m["title"]))
    for t in Task.objects.filter(owner=owner).values("id", "title"):
        candidates.append(("task", str(t["id"]), t["title"]))
    for i in Issue.objects.filter(owner=owner).values("id", "title"):
        candidates.append(("issue", str(i["id"]), i["title"]))
    for r in Risk.objects.filter(owner=owner).values("id", "risk"):
        candidates.append(("risk", str(r["id"]), r["risk"]))
    for d in Decision.objects.filter(owner=owner).values("id", "decision"):
        candidates.append(("decision", str(d["id"]), d["decision"]))
    if not candidates:
        return []
    embedder = get_embedding_provider()
    q_emb = embedder.embed_one(query)
    embs = embedder.embed([c[2] for c in candidates])
    scored = sorted(
        ({"type": c[0], "id": c[1], "text": c[2], "score": round(cosine(q_emb, e), 4)}
         for c, e in zip(candidates, embs)),
        key=lambda x: x["score"], reverse=True,
    )
    return scored[:k]


# --- timeline ---------------------------------------------------------------
def meeting_timeline(meeting) -> dict:
    """Categorized timeline; topic entries carry transcript timestamps to jump to."""
    topics = [
        {"index": s.index, "start_time": s.start_time, "text": s.text, "speaker": s.speaker}
        for s in meeting.segments.order_by("index")
    ]
    return {
        "topics": topics,
        "decisions": list(Decision.objects.filter(meeting=meeting)
                          .values("id", "decision", "created_at")),
        "tasks": list(Task.objects.filter(meeting=meeting).values("id", "title", "status", "created_at")),
        "issues": list(Issue.objects.filter(meeting=meeting)
                       .values("id", "title", "issue_type", "severity", "created_at")),
        "risks": list(Risk.objects.filter(meeting=meeting).values("id", "risk", "severity", "created_at")),
        "events": list(meeting.events.order_by("created_at")
                       .values("event_type", "message", "created_at")),
    }
