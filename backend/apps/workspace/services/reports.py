"""AI-generated reports & emails (local Ollama), versioned and never overwritten."""
from __future__ import annotations

from django.db.models import Max

from apps.meetings.prompts.registry import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.meetings.services.media import ProcessingError
from apps.workspace.models import Decision, Issue, Report, Risk, Task
from apps.workspace.prompts import REPORT_VERSION, report_instruction


def _context_for(owner, meeting=None, project=None) -> str:
    parts: list[str] = []
    if meeting is not None:
        parts.append(f"Meeting: {meeting.title}")
        analysis = meeting.analyses.filter(is_current=True).order_by("-version").first()
        if analysis:
            parts.append(f"Summary: {analysis.executive_summary}")
        task_qs = Task.objects.filter(meeting=meeting)
        decision_qs = Decision.objects.filter(meeting=meeting)
        risk_qs = Risk.objects.filter(meeting=meeting)
        issue_qs = Issue.objects.filter(meeting=meeting)
    else:
        parts.append(f"Project: {project.name}" if project else "Workspace overview")
        base = {"owner": owner}
        if project is not None:
            base["project"] = project
        task_qs = Task.objects.filter(**base)
        decision_qs = Decision.objects.filter(**base)
        risk_qs = Risk.objects.filter(**base)
        issue_qs = Issue.objects.filter(**base)

    if task_qs.exists():
        parts.append("Tasks:\n" + "\n".join(
            f"- [{t.status}] {t.title} ({t.assignee or 'unassigned'}, {t.priority})" for t in task_qs[:40]))
    if decision_qs.exists():
        parts.append("Decisions:\n" + "\n".join(f"- {d.decision}" for d in decision_qs[:20]))
    if risk_qs.exists():
        parts.append("Risks:\n" + "\n".join(f"- [{r.severity}] {r.risk}" for r in risk_qs[:20]))
    if issue_qs.exists():
        parts.append("Issues:\n" + "\n".join(f"- [{i.issue_type}/{i.severity}] {i.title}" for i in issue_qs[:20]))
    return "\n\n".join(parts)


def generate_report(*, owner, report_type: str, meeting=None, project=None, llm=None) -> Report:
    """Generate a versioned AI report/email. Previous versions are preserved."""
    context = _context_for(owner, meeting, project)
    prompt = prompt_registry.get("workspace_report")
    system, user = prompt.render(instructions=report_instruction(report_type), context=context)

    provider = llm or get_llm_provider()
    try:
        resp = provider.generate(user, system=system)
    except LLMError as exc:
        raise ProcessingError(f"Report generation failed: {exc.message}", code="llm_error",
                              retryable=exc.retryable) from exc

    scope = {"owner": owner, "report_type": report_type, "meeting": meeting, "project": project}
    next_version = (Report.all_objects.filter(**scope).aggregate(m=Max("version"))["m"] or 0) + 1
    Report.objects.filter(**scope).update(is_current=False)

    title = report_type.replace("_", " ").title()
    if meeting is not None:
        title = f"{title} — {meeting.title}"
    return Report.objects.create(
        owner=owner, report_type=report_type, meeting=meeting, project=project,
        title=title[:255], content=resp.text.strip(), version=next_version, is_current=True,
        model_used=resp.model, provider=resp.provider, prompt_version=REPORT_VERSION,
        inference_ms=resp.inference_ms,
    )
