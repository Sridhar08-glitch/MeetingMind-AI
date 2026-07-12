"""AI Insights, Smart Recommendations, Cross-Project Comparison, and the two
bonus analyses (Knowledge Conflict Detection + Decision Impact).

Everything here is EVIDENCE-BASED and computed from stored data — no invented
facts. Each surfaced item carries the meetings/records it was derived from so the
UI can show sources. Owner-scoped throughout (authorization before aggregation).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.db.models import Q
from django.utils import timezone

from apps.meetings.models import AIAnalysis, Meeting
from apps.workspace.models import Decision, Issue, Project, Report, Risk, Task

_STOP = set(
    "the a an and or of to in on for with at by from is are was were be this that "
    "we our you your it its their they will can should would our us new".split()
)
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#-]{2,}")


def _current_analyses(owner):
    return AIAnalysis.objects.filter(
        meeting__owner=owner, is_current=True, meeting__is_deleted=False
    ).select_related("meeting")


def _keywords(analyses, bucket):
    counter: Counter = Counter()
    evidence: dict[str, set] = defaultdict(set)
    for a in analyses:
        for kw in (a.keywords or {}).get(bucket, []) or []:
            key = str(kw).strip().lower()
            if not key or key in _STOP:
                continue
            counter[key] += 1
            evidence[key].add(a.meeting_id)
    return counter, evidence


def ai_insights(owner) -> dict:
    analyses = list(_current_analyses(owner))
    today = timezone.now().date()

    def top(bucket, n=10):
        counter, ev = _keywords(analyses, bucket)
        return [
            {"label": k, "count": c, "meetings": len(ev[k]), "meeting_ids": [str(x) for x in list(ev[k])[:5]]}
            for k, c in counter.most_common(n)
        ]

    # Recurring risks — group risk statements by their most salient keyword.
    risk_groups: dict[str, list] = defaultdict(list)
    for r in Risk.objects.filter(owner=owner).exclude(status="closed"):
        words = [w.lower() for w in _WORD.findall(r.risk) if w.lower() not in _STOP]
        if words:
            key = Counter(words).most_common(1)[0][0]
            risk_groups[key].append(r)
    recurring_risks = [
        {"topic": k, "count": len(v), "severity": Counter(x.severity for x in v).most_common(1)[0][0],
         "risk_ids": [str(x.id) for x in v[:5]]}
        for k, v in sorted(risk_groups.items(), key=lambda kv: -len(kv[1])) if len(v) >= 2
    ][:10]

    tasks = Task.objects.filter(owner=owner)
    overdue = tasks.filter(due_date__lt=today).exclude(status__in=["completed", "cancelled"])
    blocked = tasks.filter(status="blocked")

    # Per-project health.
    projects = []
    for p in Project.objects.filter(owner=owner):
        p_tasks = tasks.filter(Q(project=p) | Q(meeting__project=p))
        total = p_tasks.count()
        done = p_tasks.filter(status="completed").count()
        projects.append({
            "project_id": str(p.id), "name": p.name, "status": p.status,
            "tasks": total, "completed": done,
            "completion_rate": round(done / total, 2) if total else 0.0,
            "open_risks": Risk.objects.filter(Q(project=p) | Q(meeting__project=p), owner=owner)
                          .exclude(status__in=["closed", "mitigated"]).count(),
            "meetings": Meeting.objects.filter(owner=owner, project=p, is_deleted=False).count(),
        })

    return {
        "meetings_analyzed": len(analyses),
        "top_topics": top("topics"),
        "top_technologies": top("technologies"),
        "frequent_people": top("people"),
        "frequent_customers": top("companies"),
        "recurring_risks": recurring_risks,
        "overdue_tasks": {"count": overdue.count(),
                          "task_ids": [str(t.id) for t in overdue[:8]]},
        "blocked_tasks": {"count": blocked.count(),
                          "task_ids": [str(t.id) for t in blocked[:8]]},
        "project_health": projects,
    }


def recommendations(owner) -> list[dict]:
    """Rule-based, each with a cited reason and evidence ids."""
    out: list[dict] = []
    ins = ai_insights(owner)

    if ins["blocked_tasks"]["count"] >= 3:
        out.append({"priority": "high", "title": "Unblock stalled work",
                    "detail": f"{ins['blocked_tasks']['count']} tasks are blocked. Review dependencies.",
                    "evidence": {"task_ids": ins["blocked_tasks"]["task_ids"]}})
    if ins["overdue_tasks"]["count"] > 0:
        out.append({"priority": "high", "title": "Address overdue tasks",
                    "detail": f"{ins['overdue_tasks']['count']} tasks are past their due date.",
                    "evidence": {"task_ids": ins["overdue_tasks"]["task_ids"]}})
    for r in ins["recurring_risks"][:3]:
        out.append({"priority": "medium", "title": f"Escalate recurring risk: {r['topic']}",
                    "detail": f"'{r['topic']}' surfaced in {r['count']} open risks "
                              f"(max severity {r['severity']}).",
                    "evidence": {"risk_ids": r["risk_ids"]}})
    for t in ins["top_topics"][:3]:
        if t["meetings"] >= 3:
            out.append({"priority": "low", "title": f"Consider a dedicated project for '{t['label']}'",
                        "detail": f"'{t['label']}' was discussed across {t['meetings']} meetings.",
                        "evidence": {"meeting_ids": t["meeting_ids"]}})
    for p in ins["project_health"]:
        if p["tasks"] >= 3 and p["completion_rate"] < 0.25:
            out.append({"priority": "medium", "title": f"Project '{p['name']}' is behind",
                        "detail": f"Only {int(p['completion_rate'] * 100)}% of {p['tasks']} tasks complete.",
                        "evidence": {"project_id": p["project_id"]}})
    return out


def cross_project_comparison(owner) -> dict:
    rows = []
    for p in Project.objects.filter(owner=owner):
        m = Meeting.objects.filter(owner=owner, project=p, is_deleted=False)
        in_p = Q(project=p) | Q(meeting__project=p)
        tasks = Task.objects.filter(owner=owner).filter(in_p)
        total = tasks.count()
        done = tasks.filter(status="completed").count()
        rows.append({
            "project_id": str(p.id), "name": p.name, "status": p.status,
            "meetings": m.count(),
            "tasks": total, "completed_tasks": done,
            "completion_rate": round(done / total, 2) if total else 0.0,
            "open_risks": Risk.objects.filter(owner=owner).filter(in_p).exclude(status__in=["closed", "mitigated"]).count(),
            "decisions": Decision.objects.filter(owner=owner).filter(in_p).count(),
            "open_issues": Issue.objects.filter(owner=owner).filter(in_p).exclude(status__in=["closed", "resolved", "wont_fix"]).count(),
        })
    rows.sort(key=lambda r: (-r["open_risks"], -r["tasks"]))
    return {"projects": rows, "project_count": len(rows)}


def detect_conflicts(owner) -> list[dict]:
    """BONUS — potential contradictory decisions.

    Heuristic: decisions from DIFFERENT meetings that share a salient topic word
    are surfaced for human review (evidence-based, never auto-asserts a conflict).
    """
    by_topic: dict[str, list] = defaultdict(list)
    for d in Decision.objects.filter(owner=owner).select_related("meeting").exclude(status="reversed"):
        words = [w.lower() for w in _WORD.findall(d.decision) if w.lower() not in _STOP]
        for key in {w for w, _ in Counter(words).most_common(3)}:
            by_topic[key].append(d)
    conflicts = []
    for topic, decs in by_topic.items():
        meetings = {d.meeting_id for d in decs}
        if len(decs) >= 2 and len(meetings) >= 2:
            conflicts.append({
                "topic": topic, "count": len(decs),
                "decisions": [
                    {"id": str(d.id), "decision": d.decision[:200],
                     "meeting_id": str(d.meeting_id) if d.meeting_id else None,
                     "meeting_title": d.meeting.title if d.meeting else None,
                     "status": d.status, "decided_at": d.decided_at}
                    for d in decs[:6]
                ],
            })
    conflicts.sort(key=lambda c: -c["count"])
    return conflicts[:15]


def decision_impact(owner, decision: Decision) -> dict:
    """BONUS — what a decision touches: tasks, risks, issues in the same
    project/meeting plus items sharing its keywords."""
    words = {w.lower() for w in _WORD.findall(decision.decision) if w.lower() not in _STOP}
    scope = Q(meeting=decision.meeting) if decision.meeting_id else Q(pk__in=[])
    if decision.project_id:
        scope |= Q(project_id=decision.project_id)

    def related(model, text_field):
        qs = model.objects.filter(owner=owner).filter(scope)
        kw = Q()
        for w in list(words)[:8]:
            kw |= Q(**{f"{text_field}__icontains": w})
        if words:
            qs = model.objects.filter(owner=owner).filter(scope | kw)
        return qs.distinct()

    tasks = related(Task, "title")
    risks = related(Risk, "risk")
    issues = related(Issue, "title")
    return {
        "decision": {"id": str(decision.id), "decision": decision.decision,
                     "meeting_id": str(decision.meeting_id) if decision.meeting_id else None,
                     "project_id": str(decision.project_id) if decision.project_id else None},
        "impact": {
            "tasks": {"count": tasks.count(), "items": list(tasks.values("id", "title", "status")[:10])},
            "risks": {"count": risks.count(), "items": list(risks.values("id", "risk", "severity", "status")[:10])},
            "issues": {"count": issues.count(), "items": list(issues.values("id", "title", "status")[:10])},
        },
    }


def decision_impact_graph(owner, decision: Decision) -> dict:
    """Decision Impact Graph (11B, feature #4) — everything a decision touches
    (tasks, risks, issues, reports, meetings, projects) as counts + a graph."""
    words = {w.lower() for w in _WORD.findall(decision.decision) if w.lower() not in _STOP}
    scope = Q(meeting=decision.meeting) if decision.meeting_id else Q(pk__in=[])
    if decision.project_id:
        scope |= Q(project_id=decision.project_id)

    def related(model, text_field):
        kw = Q()
        for w in list(words)[:8]:
            kw |= Q(**{f"{text_field}__icontains": w})
        base = scope | kw if words else scope
        return model.objects.filter(owner=owner).filter(base).distinct()

    tasks = related(Task, "title")
    risks = related(Risk, "risk")
    issues = related(Issue, "title")
    reports = Report.objects.filter(owner=owner).filter(scope).distinct()
    meetings = Meeting.objects.filter(owner=owner, is_deleted=False).filter(
        Q(id=decision.meeting_id) | (Q(project_id=decision.project_id) if decision.project_id else Q(pk__in=[]))
    ).distinct()
    projects = Project.objects.filter(owner=owner).filter(
        Q(id=decision.project_id) if decision.project_id else Q(pk__in=[])
    ).distinct()

    nodes = [{"id": str(decision.id), "type": "decision", "label": decision.decision[:60]}]
    edges = []

    def add(qs, ntype, label_field, limit=25):
        for row in qs[:limit]:
            nid = str(row.id)
            nodes.append({"id": nid, "type": ntype, "label": (getattr(row, label_field) or "")[:60]})
            edges.append({"source": str(decision.id), "target": nid, "type": ntype})

    add(tasks, "task", "title")
    add(risks, "risk", "risk")
    add(issues, "issue", "title")
    add(reports, "report", "title")
    add(meetings, "meeting", "title")
    add(projects, "project", "name")

    return {
        "decision": {"id": str(decision.id), "decision": decision.decision,
                     "project_id": str(decision.project_id) if decision.project_id else None},
        "counts": {
            "tasks": tasks.count(), "risks": risks.count(), "issues": issues.count(),
            "reports": reports.count(), "meetings": meetings.count(), "projects": projects.count(),
        },
        "graph": {"nodes": nodes, "edges": edges},
    }
