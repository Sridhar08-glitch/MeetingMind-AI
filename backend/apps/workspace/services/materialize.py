"""AI Suggestion engine + approval workflow (human-in-the-loop).

The AI never creates live records directly. For each item extracted by
``meetings.AIAnalysis`` it creates an :class:`AISuggestion` (pending) with a
confidence score and full evidence (the transcript segment it was grounded in:
speaker, timestamp, quote) and a plain-language reason. A user then
approves/edits/rejects; only on approval is the real Task/Issue/Decision/Risk/
FollowUp created, carrying the same evidence. Nothing is deleted → full audit
trail.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.workspace.enums import (
    ActivityVerb,
    ApprovalStatus,
    Confidence,
    FollowUpStatus,
    IssueType,
    NotificationType,
    Priority,
    Severity,
    SuggestionType,
)
from apps.workspace.models import (
    AISuggestion,
    Decision,
    FollowUp,
    Issue,
    Notification,
    Risk,
    Task,
)

logger = logging.getLogger("meetingmind.ai")

_PRIORITY = {p.value: p.value for p in Priority}
_SEVERITY = {s.value: s.value for s in Severity}
_ISSUE_TYPE = {t.value: t.value for t in IssueType}

_REASON = {
    SuggestionType.TASK: "Detected because a task or work assignment was mentioned.",
    SuggestionType.DECISION: "Detected because a decision was stated in the meeting.",
    SuggestionType.RISK: "Detected because a risk, concern or blocker was raised.",
    SuggestionType.ISSUE: "Detected because a problem or issue was reported.",
    SuggestionType.FOLLOW_UP: "Detected because a follow-up or pending question was raised.",
}


def _coerce(value, mapping, default):
    return mapping.get(str(value or "").lower().strip(), default)


def _confidence_label(score: int) -> str:
    if score >= 75:
        return Confidence.HIGH
    if score >= 55:
        return Confidence.MEDIUM
    return Confidence.LOW


# Below this score a suggestion is flagged as "needs review".
_NEEDS_REVIEW_BELOW = 55


def _ground(meeting, text: str, retriever):
    """Find the transcript segment supporting ``text``; return (segment, score)."""
    segments = retriever.retrieve(meeting, text, k=1) if text else []
    if not segments:
        return None, 40
    seg = segments[0]
    words = set(re.findall(r"\w+", text.lower()))
    seg_words = set(re.findall(r"\w+", seg.text.lower()))
    overlap = len(words & seg_words) / max(1, len(words))
    return seg, int(min(96, 45 + overlap * 55))


def _notify(owner, meeting, ntype, title):
    Notification.objects.create(owner=owner, meeting=meeting, notification_type=ntype, title=title)


@transaction.atomic
def materialize(meeting, analysis) -> dict:
    """Create pending AI suggestions from an ``AIAnalysis`` (or auto-approve per mode)."""
    from apps.meetings.services.retrieval import RetrievalService

    owner = meeting.owner
    v = analysis.version
    retriever = RetrievalService()
    mode = getattr(settings, "AI_SUGGESTION_MODE", "suggestions_only")
    threshold = getattr(settings, "AI_AUTO_APPROVE_THRESHOLD", 95)
    counts = {"suggested": 0, "auto_approved": 0}

    # (type, title) already suggested/approved for this meeting → skip duplicates.
    existing = set(
        AISuggestion.objects.filter(meeting=meeting).values_list("suggestion_type", "title")
    )

    def emit(stype: str, title: str, item: dict):
        title = title.strip()
        if not title or (stype, title[:500]) in existing:
            return
        seg, score = _ground(meeting, title, retriever)
        status = ApprovalStatus.NEEDS_REVIEW if score < _NEEDS_REVIEW_BELOW else ApprovalStatus.PENDING
        suggestion = AISuggestion.objects.create(
            owner=owner, meeting=meeting, suggestion_type=stype, title=title[:500],
            status=status, generated_json=item, original_json=item,
            confidence_score=score, confidence=_confidence_label(score),
            reason=_REASON.get(stype, ""), source_analysis_version=v,
            source_segment_index=(seg.index if seg else None),
            source_start_time=(seg.start_time if seg else None),
            source_speaker=(seg.speaker if seg else ""),
            quote=(seg.text if seg else ""),
        )
        existing.add((stype, title[:500]))
        counts["suggested"] += 1
        _notify(owner, meeting, NotificationType.NEW_TASK if stype == SuggestionType.TASK
                else NotificationType.NEW_RISK if stype == SuggestionType.RISK
                else NotificationType.NEW_ISSUE if stype == SuggestionType.ISSUE
                else NotificationType.NEW_TASK,
                f"AI suggested {stype}: {title[:60]}")
        # Auto-approve modes.
        if mode == "always" or (mode == "auto_high" and score >= threshold):
            approve_suggestion(suggestion, actor=owner)
            counts["auto_approved"] += 1

    for it in analysis.action_items:
        emit(SuggestionType.TASK, it.get("task", ""), it)
    for d in analysis.decisions:
        emit(SuggestionType.DECISION, d.get("decision", ""), d)
    for r in analysis.risks:
        emit(SuggestionType.RISK, r.get("risk", ""), r)
    for i in getattr(analysis, "issues", []):
        emit(SuggestionType.ISSUE, i.get("title", ""), i)
    for f in analysis.follow_ups:
        emit(SuggestionType.FOLLOW_UP, f.get("item", ""), f)

    logger.info("AI suggestions for meeting %s: %s", meeting.id, counts)
    return counts


# --- approval workflow ------------------------------------------------------
def _explainability(suggestion: AISuggestion) -> dict:
    return dict(
        owner=suggestion.owner, meeting=suggestion.meeting, created_by_ai=True,
        source_analysis_version=suggestion.source_analysis_version,
        confidence=suggestion.confidence, confidence_score=suggestion.confidence_score,
        source_segment_index=suggestion.source_segment_index,
        source_start_time=suggestion.source_start_time, source_speaker=suggestion.source_speaker,
        source_quote=suggestion.quote, source_reason=suggestion.reason, suggestion=suggestion,
    )


@transaction.atomic
def approve_suggestion(suggestion, *, actor=None, edited: dict | None = None,
                       reviewer_notes: str = "", on_duplicate: str = "create"):
    """Approve a suggestion → create the real entity (from edited data if given).

    ``on_duplicate`` (tasks): ``create`` (default), ``merge`` (link to the
    existing duplicate, don't create a new one), or ``update`` (overwrite it).
    Records the full audit trail + an activity-feed entry.
    """
    from apps.workspace.services.activity import find_duplicate_tasks, log_activity

    if suggestion.status in {ApprovalStatus.APPROVED, ApprovalStatus.CONVERTED}:
        return None
    item = {**suggestion.generated_json, **(edited or {})}
    base = _explainability(suggestion)
    created = None
    t = suggestion.suggestion_type

    if t == SuggestionType.TASK:
        title = (item.get("task") or suggestion.title)[:500]
        if on_duplicate in {"merge", "update"}:
            dupes = find_duplicate_tasks(suggestion.owner, title)
            if dupes:
                existing = Task.objects.filter(id=dupes[0]["id"]).first()
                if existing:
                    if on_duplicate == "update":
                        existing.title = title
                        existing.assignee = (item.get("owner") or "").strip() or existing.assignee
                        existing.save()
                    log_activity(suggestion.owner, ActivityVerb.MERGED, existing,
                                 summary=f"Merged AI suggestion into task '{existing.title[:50]}'")
                    created = existing
        if created is None:
            created = Task.objects.create(
                title=title, assignee=(item.get("owner") or "").strip(),
                priority=_coerce(item.get("priority"), _PRIORITY, Priority.MEDIUM), **base)
    elif t == SuggestionType.ISSUE:
        created = Issue.objects.create(
            title=(item.get("title") or suggestion.title)[:500],
            description=(item.get("description") or "").strip(),
            issue_type=_coerce(item.get("type"), _ISSUE_TYPE, IssueType.PROBLEM),
            severity=_coerce(item.get("severity"), _SEVERITY, Severity.MEDIUM), **base)
    elif t == SuggestionType.DECISION:
        created = Decision.objects.create(
            decision=(item.get("decision") or suggestion.title),
            reason=(item.get("reason") or "").strip(),
            participants=item.get("participants") or [], **base)
    elif t == SuggestionType.RISK:
        created = Risk.objects.create(
            risk=(item.get("risk") or suggestion.title),
            severity=_coerce(item.get("severity"), _SEVERITY, Severity.MEDIUM),
            mitigation=(item.get("mitigation") or "").strip(), **base)
    elif t == SuggestionType.FOLLOW_UP:
        created = FollowUp.objects.create(
            item=(item.get("item") or suggestion.title),
            assignee=(item.get("owner") or "").strip(),
            status=FollowUpStatus.PENDING, **base)

    if actor is not None and created is not None:
        created.set_acting_user(actor)
        created.save()

    suggestion.status = ApprovalStatus.CONVERTED
    suggestion.approved_by = actor
    suggestion.approved_at = timezone.now()
    suggestion.reviewer_notes = reviewer_notes or suggestion.reviewer_notes
    suggestion.generated_json = item
    if edited:
        suggestion.edited_json = item
    if created is not None:
        suggestion.converted_to_type = type(created).__name__.lower()
        suggestion.converted_to_id = created.id
    suggestion.save()
    if created is not None:
        log_activity(suggestion.owner, ActivityVerb.APPROVED, created,
                     summary=f"Approved AI {t}: {suggestion.title[:60]}", confidence=suggestion.confidence)
    return created


def reject_suggestion(suggestion, *, actor=None, reviewer_notes: str = ""):
    from apps.workspace.services.activity import log_activity

    suggestion.status = ApprovalStatus.REJECTED
    suggestion.approved_by = actor
    suggestion.approved_at = timezone.now()
    suggestion.reviewer_notes = reviewer_notes or suggestion.reviewer_notes
    suggestion.save(update_fields=["status", "approved_by", "approved_at", "reviewer_notes", "updated_at"])
    log_activity(suggestion.owner, ActivityVerb.REJECTED, suggestion,
                 summary=f"Rejected AI {suggestion.suggestion_type}: {suggestion.title[:60]}")
    return suggestion
