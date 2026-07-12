"""Knowledge graph + project memory (read-side, owner-scoped)."""
from __future__ import annotations

import re

from django.db.models import Q

from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision, Issue, Project, Report, Risk, Task

_MAX_GRAPH_MEETINGS = 40
_MAX_GRAPH_PEOPLE = 200


def knowledge_graph(owner, *, project=None, meeting=None) -> dict:
    """Nodes + edges linking projects → meetings → decisions/tasks/issues/risks/reports."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(nid, ntype, label):
        nodes.setdefault(str(nid), {"id": str(nid), "type": ntype, "label": (label or "")[:60]})

    def link(src, dst):
        edges.append({"source": str(src), "target": str(dst)})

    meetings = Meeting.objects.filter(owner=owner).select_related("project")
    if project:
        meetings = meetings.filter(project_id=project)
    if meeting:
        meetings = meetings.filter(id=meeting)
    meetings = meetings.order_by("-created_at")[:_MAX_GRAPH_MEETINGS]

    for m in meetings:
        add(m.id, "meeting", m.title)
        if m.project_id:
            add(m.project_id, "project", m.project.name)
            link(m.project_id, m.id)
        for d in m.decisions.all():
            add(d.id, "decision", d.decision); link(m.id, d.id)
        for t in m.tasks.all():
            add(t.id, "task", t.title); link(m.id, t.id)
        for r in m.risks.all():
            add(r.id, "risk", r.risk); link(m.id, r.id)
        for i in m.issues.all():
            add(i.id, "issue", i.title); link(m.id, i.id)
        for rep in m.reports.all():
            add(rep.id, "report", rep.title); link(m.id, rep.id)

    return {"nodes": list(nodes.values()), "edges": edges}


def _pid(name: str) -> str:
    """Stable node id for a person derived from their (normalized) name."""
    return "person:" + re.sub(r"\s+", "_", name.strip().lower())


def people_graph(owner, *, project=None) -> dict:
    """People Knowledge Graph (11C, Module 5) — extends the knowledge graph with
    PEOPLE nodes and their relationships (speaker/participant/assignee/owner) to
    meetings, tasks, decisions, risks, projects and reports. Every node is
    clickable (carries a stable id + type + entity ref)."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(nid, ntype, label, ref=None):
        nodes.setdefault(str(nid), {"id": str(nid), "type": ntype,
                                    "label": (label or "")[:60], "ref": ref})

    def person(name, role, target_id, target_type, target_label):
        if not name or not name.strip():
            return
        pid = _pid(name)
        add(pid, "person", name.strip())
        add(target_id, target_type, target_label, ref=str(target_id))
        edges.append({"source": pid, "target": str(target_id), "type": role})

    meetings = Meeting.objects.filter(owner=owner, is_deleted=False).select_related("project")
    if project:
        meetings = meetings.filter(project_id=project)
    meetings = meetings.order_by("-created_at")[:_MAX_GRAPH_MEETINGS]
    meeting_ids = [m.id for m in meetings]

    for m in meetings:
        add(m.id, "meeting", m.title, ref=str(m.id))
        if m.project_id:
            add(m.project_id, "project", m.project.name, ref=str(m.project_id))
            edges.append({"source": str(m.project_id), "target": str(m.id), "type": "contains"})

    # Speakers → meetings (from transcripts).
    for row in (TranscriptSegment.objects.filter(meeting__owner=owner, meeting_id__in=meeting_ids)
                .exclude(speaker="").values("speaker", "meeting_id").distinct()[:_MAX_GRAPH_PEOPLE * 4]):
        m = next((mm for mm in meetings if mm.id == row["meeting_id"]), None)
        if m:
            person(row["speaker"], "speaker", m.id, "meeting", m.title)

    # Assignees → tasks / risks.
    for t in Task.objects.filter(owner=owner).exclude(assignee="")[:_MAX_GRAPH_PEOPLE * 2]:
        add(t.id, "task", t.title, ref=str(t.id))
        person(t.assignee, "assignee", t.id, "task", t.title)
    for r in Risk.objects.filter(owner=owner).exclude(assignee="")[:_MAX_GRAPH_PEOPLE]:
        add(r.id, "risk", r.risk, ref=str(r.id))
        person(r.assignee, "assignee", r.id, "risk", r.risk)

    # Participants → decisions.
    for d in Decision.objects.filter(owner=owner)[:_MAX_GRAPH_PEOPLE * 2]:
        if d.participants:
            add(d.id, "decision", d.decision, ref=str(d.id))
            for name in d.participants:
                person(str(name), "participant", d.id, "decision", d.decision)

    people = [n for n in nodes.values() if n["type"] == "person"]
    return {"nodes": list(nodes.values()), "edges": edges,
            "counts": {"people": len(people), "nodes": len(nodes), "edges": len(edges)}}


def project_memory(owner, project: Project) -> dict:
    """Long-term project context: meetings, decisions, risks, tasks, reports."""
    meetings = Meeting.objects.filter(owner=owner, project=project).order_by("-created_at")
    in_project = Q(project=project) | Q(meeting__project=project)
    decisions = Decision.objects.filter(owner=owner).filter(in_project)
    risks = Risk.objects.filter(owner=owner).filter(in_project)
    tasks = Task.objects.filter(owner=owner).filter(in_project)
    issues = Issue.objects.filter(owner=owner).filter(in_project)
    reports = Report.objects.filter(owner=owner).filter(in_project)
    return {
        "project": {"id": str(project.id), "name": project.name, "status": project.status},
        "counts": {
            "meetings": meetings.count(), "decisions": decisions.count(), "risks": risks.count(),
            "tasks": tasks.count(), "issues": issues.count(), "reports": reports.count(),
        },
        "timeline": list(meetings.values("id", "title", "created_at")[:20]),
        "recent_decisions": list(decisions.order_by("-created_at").values("id", "decision")[:10]),
        "open_risks": list(risks.filter(status="open").values("id", "risk", "severity")[:10]),
    }
