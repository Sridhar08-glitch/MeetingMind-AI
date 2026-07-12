"""Executive Intelligence (Phase 11C).

Composes the layers already built (Phase 10 insights + graph, 11A temporal/
events, 11B consensus/conflict/reliability/memory-score) into an executive view:
Workspace Health, Workspace Score, Analytics, explainable Recommendations,
Organization Insights, Alerts, History and Predictive Health.

Everything is MATERIALIZED into ExecutiveSnapshot / ExecutiveMetricSnapshot /
ExecutiveAlert (computed on job completion or explicit refresh) so requests never
recompute expensive metrics. Every card is explainable (formula + evidence +
knowledge_version + last_updated). Owner-scoped, 100% local, no paid APIs.
"""
from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.jobs.events import event_bus
from apps.knowledge.models import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    ConflictStatus,
    ExecutiveAlert,
    ExecutiveExplanation,
    ExecutiveMetricSnapshot,
    ExecutivePrediction,
    ExecutiveRecommendation,
    ExecutiveTrendPoint,
    HealthStatus,
    KnowledgeConflict,
    KnowledgeConsensus,
    KnowledgeItem,
    KnowledgeRetrieval,
    KnowledgeVersion,
    OrganizationSnapshot,
    ProjectSnapshot,
    RecommendationStatus,
    TrendGranularity,
)
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.insights import ai_insights, recommendations
from apps.knowledge.services.scoring import organizational_memory_scores, project_memory_score
from apps.meetings.models import AIAnalysis, Meeting, TranscriptSegment
from apps.workspace.models import AISuggestion, Decision, Issue, Project, Risk, Task

# Event-bus topic emitted after a scope is (re)materialized (generic string bus).
EXECUTIVE_MATERIALIZED = "executive_materialized"


def _next_snapshot_version(owner) -> int:
    from django.db.models import Max
    org = OrganizationSnapshot.objects.filter(owner=owner).aggregate(m=Max("snapshot_version"))["m"] or 0
    proj = ProjectSnapshot.objects.filter(owner=owner).aggregate(m=Max("snapshot_version"))["m"] or 0
    return max(org, proj) + 1


def _status(score: float) -> str:
    if score >= 85:
        return HealthStatus.EXCELLENT
    if score >= 70:
        return HealthStatus.GOOD
    if score >= 50:
        return HealthStatus.WARNING
    return HealthStatus.CRITICAL


def _clamp(x: float) -> float:
    return round(max(0.0, min(100.0, x)), 1)


def _dim(score: float, formula: str, evidence: dict) -> dict:
    s = _clamp(score)
    return {"score": s, "status": _status(s), "formula": formula, "evidence": evidence}


# --- Health (Module 1) ------------------------------------------------------


def compute_health(owner) -> dict:
    ins = ai_insights(owner)
    mem = organizational_memory_scores(owner)

    tasks = Task.objects.filter(owner=owner)
    total_t = tasks.count()
    done_t = tasks.filter(status="completed").count()
    blocked_t = ins["blocked_tasks"]["count"]
    overdue_t = ins["overdue_tasks"]["count"]
    completion = done_t / total_t if total_t else 1.0
    task_health = _dim(
        100 * (0.5 + 0.5 * completion) - 5 * blocked_t - 3 * overdue_t if total_t else 100,
        "0.5+0.5·completion, minus 5·blocked and 3·overdue (capped 0–100)",
        {"total": total_t, "completed": done_t, "blocked": blocked_t, "overdue": overdue_t,
         "completion_rate": round(completion, 2)},
    )

    risks = Risk.objects.filter(owner=owner)
    open_r = risks.exclude(status__in=["closed", "mitigated"]).count()
    crit_open = risks.exclude(status__in=["closed", "mitigated"]).filter(
        severity__in=["high", "critical"]).count()
    risk_health = _dim(
        100 - min(60, 5 * open_r) - min(30, 10 * crit_open),
        "100 − min(60, 5·open_risks) − min(30, 10·high_severity_open)",
        {"open_risks": open_r, "high_severity_open": crit_open, "total_risks": risks.count()},
    )

    decisions = Decision.objects.filter(owner=owner)
    n_dec = decisions.count()
    reversed_n = decisions.filter(status="reversed").count()
    consensus = list(KnowledgeConsensus.objects.filter(owner=owner))
    avg_stab = sum(c.stability_score for c in consensus) / len(consensus) if consensus else None
    dec_base = 100 * (1 - (reversed_n / n_dec)) if n_dec else 100
    decision_health = _dim(
        0.5 * avg_stab + 0.5 * dec_base if avg_stab is not None else dec_base,
        "blend of consensus stability and (1 − reversed_ratio)",
        {"decisions": n_dec, "reversed": reversed_n,
         "avg_consensus_stability": round(avg_stab, 1) if avg_stab is not None else None},
    )

    items = KnowledgeItem.objects.current().filter(owner=owner)
    avg_conf = items.aggregate(a=Avg("confidence"))["a"] or 0.0
    stats = KnowledgeIndexService().stats(owner)
    last = stats.get("indexed_at") or stats.get("last_updated")
    age_days = (timezone.now() - last).days if last else 999
    freshness = 100 * (0.5 ** (age_days / 30))
    open_conf = KnowledgeConflict.objects.filter(owner=owner, status=ConflictStatus.OPEN).count()
    knowledge_health = _dim(
        0.6 * avg_conf + 0.4 * freshness - 5 * open_conf,
        "0.6·avg_item_confidence + 0.4·freshness(30-day half-life) − 5·open_conflicts",
        {"items": items.count(), "avg_confidence": round(avg_conf, 1),
         "days_since_index": age_days, "open_conflicts": open_conf,
         "knowledge_version": stats.get("knowledge_version", 0)},
    )

    meetings = Meeting.objects.filter(owner=owner, is_deleted=False)
    n_meet = meetings.count()
    summarized = (AIAnalysis.objects.filter(meeting__owner=owner, is_current=True)
                  .values("meeting").distinct().count())
    meeting_health = _dim(
        100 * (summarized / n_meet) if n_meet else 100,
        "share of meetings with an AI summary (processed quality)",
        {"meetings": n_meet, "summarized": summarized},
    )

    sugg = AISuggestion.objects.filter(owner=owner)
    approved = sugg.filter(status__in=["approved", "converted"]).count()
    rejected = sugg.filter(status="rejected").count()
    approval = approved / (approved + rejected) if (approved + rejected) else None
    ai_conf = sugg.aggregate(a=Avg("confidence_score"))["a"]
    ai_health = _dim(
        (0.6 * approval * 100 + 0.4 * (ai_conf or 80)) if approval is not None else (ai_conf or 80),
        "0.6·approval_rate + 0.4·avg_ai_confidence (neutral 80 when no reviews)",
        {"approved": approved, "rejected": rejected,
         "approval_rate": round(approval, 2) if approval is not None else None,
         "avg_ai_confidence": round(ai_conf, 1) if ai_conf else None},
    )

    project_health = _dim(
        mem["workspace_overall"],
        "average Organizational Memory Score across projects",
        {"projects": mem["project_count"], "workspace_overall": mem["workspace_overall"]},
    )

    dims = {
        "project": project_health, "meeting": meeting_health, "knowledge": knowledge_health,
        "task": task_health, "decision": decision_health, "risk": risk_health, "ai": ai_health,
    }
    weights = {"project": 0.2, "knowledge": 0.2, "task": 0.15, "risk": 0.15,
               "decision": 0.15, "meeting": 0.1, "ai": 0.05}
    overall_score = _clamp(sum(dims[k]["score"] * w for k, w in weights.items()))
    overall = {"score": overall_score, "status": _status(overall_score),
               "formula": "weighted average of the 7 health dimensions",
               "evidence": {k: dims[k]["score"] for k in dims}}
    return {"overall": overall, "dimensions": dims,
            "knowledge_version": stats.get("knowledge_version", 0)}


# --- Workspace Score (Module 2) --------------------------------------------


def compute_score(owner, *, health: dict | None = None) -> dict:
    health = health or compute_health(owner)
    d = health["dimensions"]
    mem = organizational_memory_scores(owner)
    doc_vals = [p["components"]["documentation"] for p in mem["projects"]]
    documentation = round(sum(doc_vals) / len(doc_vals), 1) if doc_vals else d["meeting"]["score"]
    trend_vals = [p["components"]["trend_stability"] for p in mem["projects"]]
    trend_stability = round(sum(trend_vals) / len(trend_vals), 1) if trend_vals else 100.0

    breakdown = {
        "knowledge": {"score": d["knowledge"]["score"], "explanation": d["knowledge"]["formula"]},
        "execution": {"score": d["task"]["score"], "explanation": d["task"]["formula"]},
        "risks": {"score": d["risk"]["score"], "explanation": d["risk"]["formula"]},
        "documentation": {"score": documentation, "explanation": "avg project documentation coverage"},
        "ai_confidence": {"score": d["ai"]["score"], "explanation": d["ai"]["formula"]},
        "decision_stability": {"score": d["decision"]["score"], "explanation": d["decision"]["formula"]},
        "trend_stability": {"score": trend_stability, "explanation": "avg consensus stability across projects"},
    }
    weights = {"knowledge": 0.2, "execution": 0.2, "risks": 0.15, "documentation": 0.15,
               "ai_confidence": 0.1, "decision_stability": 0.1, "trend_stability": 0.1}
    overall = _clamp(sum(breakdown[k]["score"] * w for k, w in weights.items()))
    return {"score": overall, "out_of": 100, "status": _status(overall), "breakdown": breakdown}


# --- Analytics (Module 3) ---------------------------------------------------


def _monthly(qs, field="created_at"):
    rows = (qs.annotate(m=TruncMonth(field)).values("m").annotate(n=Count("id")).order_by("m"))
    return [{"period": r["m"], "count": r["n"]} for r in rows if r["m"]]


def compute_analytics(owner) -> dict:
    ins = ai_insights(owner)
    meetings = Meeting.objects.filter(owner=owner, is_deleted=False)
    history = ExecutiveMetricSnapshot.objects.filter(owner=owner).order_by("recorded_at")

    def series(field):
        return [{"at": m.recorded_at, "value": getattr(m, field)} for m in history]

    speakers = Counter()
    for row in (TranscriptSegment.objects.filter(meeting__owner=owner)
                .exclude(speaker="").values("speaker").annotate(n=Count("id"))):
        speakers[row["speaker"]] = row["n"]

    # Contributors = speakers + task/risk assignees.
    contributors = Counter(speakers)
    for model, field in ((Task, "assignee"), (Risk, "assignee")):
        for row in (model.objects.filter(owner=owner).exclude(**{f"{field}": ""})
                    .values(field).annotate(n=Count("id"))):
            contributors[row[field]] += row["n"]

    projects_activity = []
    for p in Project.objects.filter(owner=owner):
        in_p = Q(project=p) | Q(meeting__project=p)
        projects_activity.append({
            "project_id": str(p.id), "name": p.name,
            "meetings": meetings.filter(project=p).count(),
            "tasks": Task.objects.filter(owner=owner).filter(in_p).count(),
        })
    projects_activity.sort(key=lambda r: -(r["meetings"] + r["tasks"]))

    return {
        "growth": {
            "meetings_monthly": _monthly(meetings),
            "tasks_monthly": _monthly(Task.objects.filter(owner=owner)),
            "decisions_monthly": _monthly(Decision.objects.filter(owner=owner)),
            "risks_monthly": _monthly(Risk.objects.filter(owner=owner)),
            "issues_monthly": _monthly(Issue.objects.filter(owner=owner)),
            "knowledge_items": series("knowledge_items"),
        },
        "trends": {
            "workspace_score": series("workspace_score"),
            "overall_health": series("overall_health"),
            "knowledge_confidence": series("avg_confidence"),
            "decision_stability": series("decision_stability"),
        },
        "ai_usage": {
            "retrievals": KnowledgeRetrieval.objects.filter(owner=owner).count(),
            "by_kind": list(KnowledgeRetrieval.objects.filter(owner=owner)
                            .values("kind").annotate(n=Count("id"))),
        },
        "ai_accuracy": _ai_accuracy(owner),
        "leaderboards": {
            "top_contributors": [{"name": n, "count": c} for n, c in contributors.most_common(10)],
            "most_active_projects": projects_activity[:10],
            "most_discussed_topics": ins["top_topics"][:10],
            "most_active_speakers": [{"name": n, "count": c} for n, c in speakers.most_common(10)],
            "most_frequent_customers": ins["frequent_customers"][:10],
            "most_frequent_technologies": ins["top_technologies"][:10],
        },
    }


def _ai_accuracy(owner) -> dict:
    sugg = AISuggestion.objects.filter(owner=owner)
    approved = sugg.filter(status__in=["approved", "converted"]).count()
    rejected = sugg.filter(status="rejected").count()
    edited = sugg.filter(status="edited").count()
    reviewed = approved + rejected
    return {
        "total_suggestions": sugg.count(), "approved": approved, "rejected": rejected,
        "edited": edited,
        "approval_rate": round(approved / reviewed, 2) if reviewed else None,
        "avg_confidence": round(sugg.aggregate(a=Avg("confidence_score"))["a"] or 0, 1),
    }


# --- Recommendation Explainability (Module 4) ------------------------------


def explain_recommendations(owner) -> list[dict]:
    """Every recommendation carries reason + full evidence + confidence +
    consensus + related projects + impact (never unexplained)."""
    stats = KnowledgeIndexService().stats(owner)
    kv = stats.get("knowledge_version", 0)
    consensus = {c.topic: c for c in KnowledgeConsensus.objects.filter(owner=owner)}
    out = []
    for rec in recommendations(owner):
        ev = rec.get("evidence", {})
        related_projects = []
        if ev.get("project_id"):
            p = Project.objects.filter(owner=owner, id=ev["project_id"]).first()
            if p:
                related_projects = [{"id": str(p.id), "name": p.name}]
        # Confidence from breadth of evidence.
        n_ev = sum(len(v) if isinstance(v, list) else 1 for v in ev.values())
        confidence = _clamp(50 + 12 * n_ev)
        topic_match = next((consensus[t] for t in consensus
                            if t in rec["title"].lower() or t in rec["detail"].lower()), None)
        out.append({
            **rec,
            "explanation": {
                "reason": rec["detail"],
                "evidence": ev,
                "supporting_meetings": ev.get("meeting_ids", []),
                "supporting_decisions": ev.get("decision_ids", []),
                "supporting_tasks": ev.get("task_ids", []),
                "supporting_risks": ev.get("risk_ids", []),
                "confidence": confidence,
                "consensus": ({"topic": topic_match.topic, "position": topic_match.current_position,
                               "confidence": topic_match.confidence} if topic_match else None),
                "related_projects": related_projects,
                "knowledge_version": kv,
                "last_updated": stats.get("indexed_at"),
            },
        })
    return out


# --- Organization Insights (Module 9) --------------------------------------


def organization_insights(owner) -> dict:
    ins = ai_insights(owner)
    mem = organizational_memory_scores(owner)
    recent = timezone.now() - timezone.timedelta(days=30)

    growth = []
    for p in Project.objects.filter(owner=owner):
        recent_m = Meeting.objects.filter(owner=owner, project=p, created_at__gte=recent).count()
        recent_t = Task.objects.filter(owner=owner, project=p, created_at__gte=recent).count()
        growth.append((p, recent_m + recent_t))
    fastest = max(growth, key=lambda x: x[1], default=(None, 0))

    highest_risk = max(ins["project_health"], key=lambda p: p["open_risks"], default=None)
    most_stable = max(mem["projects"], key=lambda p: p["components"]["decision_stability"], default=None)
    most_delayed = max(ins["project_health"],
                       key=lambda p: p["tasks"] - p["completed"], default=None)

    blocked_words = Counter()
    for t in Task.objects.filter(owner=owner, status="blocked"):
        blocked_words.update(w for w in t.title.lower().split() if len(w) > 3)

    assignees = Counter()
    for t in Task.objects.filter(owner=owner, status="completed").exclude(assignee=""):
        assignees[t.assignee] += 1

    return {
        "fastest_growing_project": ({"id": str(fastest[0].id), "name": fastest[0].name,
                                     "recent_activity": fastest[1]} if fastest[0] else None),
        "highest_risk_project": highest_risk,
        "most_stable_project": ({"id": most_stable["project_id"], "name": most_stable["name"],
                                 "decision_stability": most_stable["components"]["decision_stability"]}
                                if most_stable else None),
        "most_discussed_technology": (ins["top_technologies"][0] if ins["top_technologies"] else None),
        "most_common_blocker": (blocked_words.most_common(1)[0][0] if blocked_words else None),
        "most_delayed_area": ({"name": most_delayed["name"],
                               "open_tasks": most_delayed["tasks"] - most_delayed["completed"]}
                              if most_delayed else None),
        "most_productive_contributor": (assignees.most_common(1)[0][0] if assignees else None),
        "most_frequent_customer_request": (ins["frequent_customers"][0] if ins["frequent_customers"] else None),
    }


# --- Alerts (Module 8) ------------------------------------------------------


def _candidate_alerts(owner, kv: int) -> list[dict]:
    alerts = []

    for c in KnowledgeConflict.objects.filter(owner=owner, status=ConflictStatus.OPEN)[:20]:
        alerts.append({"key": f"conflict:{c.id}", "type": AlertType.KNOWLEDGE_CONFLICT,
                       "severity": AlertSeverity.WARNING,
                       "title": f"Unresolved {c.category} conflict on '{c.topic}'",
                       "detail": f"{c.decision_count} decisions across {c.meeting_count} meetings disagree.",
                       "evidence": {"topic": c.topic, "positions": c.positions[:4]}})

    for c in KnowledgeConsensus.objects.filter(owner=owner, stability_score__lt=60)[:20]:
        alerts.append({"key": f"instability:{c.id}", "type": AlertType.DECISION_INSTABILITY,
                       "severity": AlertSeverity.WARNING,
                       "title": f"Decision instability on '{c.topic}'",
                       "detail": f"Position has shifted repeatedly (stability {c.stability_score:.0f}).",
                       "evidence": {"topic": c.topic, "trend": c.trend}})

    blocked = Task.objects.filter(owner=owner, status="blocked")
    if blocked.count() >= 3:
        alerts.append({"key": "blockers", "type": AlertType.REPEATED_BLOCKER,
                       "severity": AlertSeverity.WARNING,
                       "title": f"{blocked.count()} tasks are blocked",
                       "detail": "Multiple tasks are blocked; review dependencies.",
                       "evidence": {"task_ids": [str(t.id) for t in blocked[:8]]}})

    high_risk_open = Risk.objects.filter(owner=owner, severity__in=["high", "critical"]).exclude(
        status__in=["closed", "mitigated"])
    if high_risk_open.count() >= 1:
        alerts.append({"key": "high_risks", "type": AlertType.OVERDUE_RISK,
                       "severity": AlertSeverity.CRITICAL,
                       "title": f"{high_risk_open.count()} high-severity risks are open",
                       "detail": "High/critical risks remain unmitigated.",
                       "evidence": {"risk_ids": [str(r.id) for r in high_risk_open[:8]]}})

    # Trend-based alerts (need ≥2 metric snapshots).
    pts = list(ExecutiveMetricSnapshot.objects.filter(owner=owner).order_by("-recorded_at")[:2])
    if len(pts) == 2:
        newer, older = pts[0], pts[1]
        if older.overall_health - newer.overall_health >= 8:
            alerts.append({"key": "health_decline", "type": AlertType.DECLINING_HEALTH,
                           "severity": AlertSeverity.WARNING,
                           "title": "Workspace health is declining",
                           "detail": f"Overall health fell {older.overall_health:.0f}→{newer.overall_health:.0f}.",
                           "evidence": {"from": older.overall_health, "to": newer.overall_health}})
        if older.avg_confidence - newer.avg_confidence >= 8:
            alerts.append({"key": "ai_conf_drop", "type": AlertType.AI_CONFIDENCE_DROP,
                           "severity": AlertSeverity.INFO,
                           "title": "AI confidence dropped",
                           "detail": f"Avg confidence fell {older.avg_confidence:.0f}→{newer.avg_confidence:.0f}.",
                           "evidence": {"from": older.avg_confidence, "to": newer.avg_confidence}})

    stats = KnowledgeIndexService().stats(owner)
    last = stats.get("indexed_at") or stats.get("last_updated")
    if last and (timezone.now() - last).days >= 30:
        alerts.append({"key": "stale_knowledge", "type": AlertType.KNOWLEDGE_OUTDATED,
                       "severity": AlertSeverity.INFO,
                       "title": "Knowledge is becoming outdated",
                       "detail": f"No re-index in {(timezone.now() - last).days} days.",
                       "evidence": {"days": (timezone.now() - last).days}})
    return alerts


@transaction.atomic
def _materialize_alerts(owner, kv: int) -> int:
    seen = set()
    for a in _candidate_alerts(owner, kv):
        seen.add(a["key"])
        ExecutiveAlert.objects.update_or_create(
            owner=owner, key=a["key"],
            defaults={"alert_type": a["type"], "severity": a["severity"], "title": a["title"],
                      "detail": a["detail"], "evidence": a["evidence"], "knowledge_version": kv,
                      "last_seen_at": timezone.now(),
                      "status": AlertStatus.OPEN},
        )
    # Auto-resolve alerts whose condition disappeared (that weren't manually acked).
    (ExecutiveAlert.objects.filter(owner=owner, status=AlertStatus.OPEN)
     .exclude(key__in=seen).update(status=AlertStatus.RESOLVED))
    return len(seen)


def list_alerts(owner, *, status: str | None = None) -> list[dict]:
    qs = ExecutiveAlert.objects.filter(owner=owner)
    if status:
        qs = qs.filter(status=status)
    return [
        {"id": str(a.id), "type": a.alert_type, "severity": a.severity, "status": a.status,
         "title": a.title, "detail": a.detail, "evidence": a.evidence,
         "knowledge_version": a.knowledge_version, "last_seen_at": a.last_seen_at}
        for a in qs.order_by("severity", "-last_seen_at")
    ]


def set_alert_status(owner, alert, status: str):
    """Alert lifecycle: open → acknowledged → resolved → dismissed."""
    alert.status = status
    alert.save(update_fields=["status", "updated_at"])
    return alert


def set_recommendation_status(owner, rec, status: str):
    rec.status = status
    rec.save(update_fields=["status", "updated_at"])
    return rec


# --- Materialization (scoped + normalized) ---------------------------------


def materialize_project(owner, project, *, snapshot_version=None, actor=None) -> ProjectSnapshot:
    """Materialize ONE project's snapshot (cheap — reuses the 11B memory score)."""
    import time
    started = time.perf_counter()
    mem = project_memory_score(owner, project)
    kv = KnowledgeIndexService().stats(owner).get("knowledge_version", 0)
    sv = snapshot_version or _next_snapshot_version(owner)
    with transaction.atomic():
        snap, _ = ProjectSnapshot.objects.update_or_create(
            owner=owner, project=project,
            defaults={
                "snapshot_version": sv, "knowledge_version": kv,
                "consensus_version": KnowledgeConsensus.objects.filter(owner=owner).count(),
                "generated_at": timezone.now(), "generated_by": actor,
                "processing_ms": int((time.perf_counter() - started) * 1000),
                "overall_health_score": mem["overall"],
                "overall_health_status": _status(mem["overall"]),
                "memory_score": mem, "signals": mem["signals"],
            },
        )
        for key, val in mem["components"].items():
            _save_explanation(owner, f"project:{project.id}", key, val,
                              f"Organizational Memory Score component ({key})",
                              mem["signals"], sv, kv)
    event_bus.publish(EXECUTIVE_MATERIALIZED, owner_id=str(owner.id),
                      scope=f"project:{project.id}", snapshot_version=sv)
    return snap


def materialize_organization(owner, *, actor=None) -> OrganizationSnapshot:
    """Materialize the org-scope snapshot, rolling up stored ProjectSnapshots."""
    import time
    started = time.perf_counter()
    health = compute_health(owner)
    score = compute_score(owner, health=health)
    analytics = compute_analytics(owner)
    org = organization_insights(owner)
    stats = KnowledgeIndexService().stats(owner)
    kv = stats.get("knowledge_version", 0)
    cv = KnowledgeConsensus.objects.filter(owner=owner).count()
    sv = _next_snapshot_version(owner)

    with transaction.atomic():
        snap, _ = OrganizationSnapshot.objects.update_or_create(
            owner=owner,
            defaults={
                "snapshot_version": sv, "knowledge_version": kv, "consensus_version": cv,
                "generated_at": timezone.now(), "generated_by": actor,
                "overall_health_score": health["overall"]["score"],
                "overall_health_status": health["overall"]["status"],
                "workspace_score": score["score"], "health": health, "score": score,
                "analytics": analytics, "organization_insights": org, "knowledge_freshness": stats,
                "processing_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        # Normalized explanations for every health + score card.
        for key, dim in health["dimensions"].items():
            _save_explanation(owner, "organization", f"health.{key}", dim["score"],
                              dim["formula"], dim["evidence"], sv, kv)
        _save_explanation(owner, "organization", "health.overall", health["overall"]["score"],
                          health["overall"]["formula"], health["overall"]["evidence"], sv, kv)
        for key, part in score["breakdown"].items():
            _save_explanation(owner, "organization", f"score.{key}", part["score"],
                              part["explanation"], {}, sv, kv)

        _append_metric_point(owner, health, score, stats)
        _materialize_recommendations(owner, sv, kv, cv)
        _materialize_alerts(owner, kv)
        _materialize_trends(owner)
        _materialize_predictions(owner, sv, kv, cv)

    event_bus.publish(EXECUTIVE_MATERIALIZED, owner_id=str(owner.id),
                      scope="organization", snapshot_version=sv)
    return snap


def materialize(owner, *, actor=None) -> OrganizationSnapshot:
    """Full refresh — every project then the org rollup (explicit refresh / seed)."""
    sv = _next_snapshot_version(owner)
    for p in Project.objects.filter(owner=owner):
        materialize_project(owner, p, snapshot_version=sv, actor=actor)
    return materialize_organization(owner, actor=actor)


def _save_explanation(owner, scope, metric_key, value, formula, evidence, sv, kv, confidence=None):
    ExecutiveExplanation.objects.update_or_create(
        owner=owner, scope=scope, metric_key=metric_key,
        defaults={"value": value, "formula": formula, "evidence": evidence,
                  "confidence": confidence, "snapshot_version": sv, "knowledge_version": kv,
                  "generated_at": timezone.now()},
    )


def _materialize_recommendations(owner, sv, kv, cv) -> int:
    seen = set()
    for rec in explain_recommendations(owner):
        exp = rec["explanation"]
        key = f"{rec['title'][:80]}"
        seen.add(key)
        ExecutiveRecommendation.objects.update_or_create(
            owner=owner, key=key,
            defaults={
                "priority": rec.get("priority", ""), "recommendation": rec["title"][:255],
                "reason": exp["reason"], "evidence": exp["evidence"],
                "confidence": exp["confidence"], "related_projects": exp["related_projects"],
                "consensus": exp["consensus"] or {}, "snapshot_version": sv,
                "knowledge_version": kv, "consensus_version": cv,
                "impact": {"supporting_meetings": len(exp["supporting_meetings"]),
                           "supporting_decisions": len(exp["supporting_decisions"]),
                           "supporting_tasks": len(exp["supporting_tasks"]),
                           "supporting_risks": len(exp["supporting_risks"])},
            },
        )
    # Retire recommendations that no longer apply (keep manually-actioned ones).
    (ExecutiveRecommendation.objects.filter(owner=owner, status=RecommendationStatus.OPEN)
     .exclude(key__in=seen).update(status=RecommendationStatus.DONE))
    return len(seen)


def _materialize_trends(owner) -> None:
    from django.db.models.functions import TruncDay, TruncWeek
    pts = ExecutiveMetricSnapshot.objects.filter(owner=owner)
    if not pts.exists():
        return
    metrics = ["overall_health", "workspace_score", "knowledge_items", "avg_confidence",
               "decision_stability", "open_risks", "tasks_done"]
    trunc = {TrendGranularity.DAILY: TruncDay, TrendGranularity.WEEKLY: TruncWeek,
             TrendGranularity.MONTHLY: TruncMonth}
    for gran, fn in trunc.items():
        buckets = (pts.annotate(p=fn("recorded_at")).values("p")
                   .annotate(**{m: Avg(m) for m in metrics}).order_by("p"))
        for b in buckets:
            if not b["p"]:
                continue
            for m in metrics:
                ExecutiveTrendPoint.objects.update_or_create(
                    owner=owner, granularity=gran, metric=m, period_start=b["p"],
                    defaults={"value": round(b[m] or 0.0, 2)},
                )


def _materialize_predictions(owner, sv, kv, cv) -> None:
    pred = predictive_health(owner)
    ExecutivePrediction.objects.filter(owner=owner).delete()
    if not pred.get("available"):
        return
    last = ExecutiveMetricSnapshot.objects.filter(owner=owner).order_by("-recorded_at").first()
    for proj in pred.get("projections", []):
        current = getattr(last, proj["metric"], 0.0) if last else 0.0
        expected = proj.get("threshold", current)
        ExecutivePrediction.objects.create(
            owner=owner, metric=proj["metric"], current_value=current,
            expected_value=expected, horizon_days=proj.get("days", 0),
            confidence=60.0, message=proj["message"], snapshot_version=sv,
            knowledge_version=kv, consensus_version=cv,
        )


def _append_metric_point(owner, health, score, stats) -> None:
    tasks = Task.objects.filter(owner=owner)
    items = KnowledgeItem.objects.current().filter(owner=owner)
    ExecutiveMetricSnapshot.objects.create(
        owner=owner, knowledge_version=stats.get("knowledge_version", 0),
        overall_health=health["overall"]["score"], workspace_score=score["score"],
        knowledge_items=items.count(),
        meetings=Meeting.objects.filter(owner=owner, is_deleted=False).count(),
        tasks_total=tasks.count(), tasks_done=tasks.filter(status="completed").count(),
        tasks_blocked=tasks.filter(status="blocked").count(),
        open_risks=Risk.objects.filter(owner=owner).exclude(status__in=["closed", "mitigated"]).count(),
        open_issues=Issue.objects.filter(owner=owner).exclude(
            status__in=["closed", "resolved", "wont_fix"]).count(),
        decisions=Decision.objects.filter(owner=owner).count(),
        open_conflicts=KnowledgeConflict.objects.filter(owner=owner, status=ConflictStatus.OPEN).count(),
        avg_confidence=items.aggregate(a=Avg("confidence"))["a"] or 0.0,
        decision_stability=health["dimensions"]["decision"]["score"],
        ai_retrievals=KnowledgeRetrieval.objects.filter(owner=owner).count(),
    )


def _cache_key(owner, snap) -> str:
    return f"exec:{owner.id}:kv{snap.knowledge_version}:cv{snap.consensus_version}:sv{snap.snapshot_version}"


def get_dashboard(owner, *, refresh: bool = False) -> dict:
    """Read the materialized org dashboard. Assembles normalized child records —
    no expensive recomputation on the read path."""
    snap = OrganizationSnapshot.objects.filter(owner=owner).first()
    if snap is None or refresh:
        snap = materialize_organization(owner)
        if not ProjectSnapshot.objects.filter(owner=owner).exists():
            snap = materialize(owner)
    latest_kv = KnowledgeVersion.objects.filter(owner=owner).order_by("-version").first()
    return {
        "cache_key": _cache_key(owner, snap),
        "snapshot_version": snap.snapshot_version,
        "knowledge_version": snap.knowledge_version,
        "consensus_version": snap.consensus_version,
        "generated_at": snap.generated_at,
        "processing_ms": snap.processing_ms,
        "stale": bool(latest_kv and snap.knowledge_version < latest_kv.version),
        "health": snap.health,
        "score": snap.score,
        "analytics": snap.analytics,
        "organization_insights": snap.organization_insights,
        "knowledge_freshness": snap.knowledge_freshness,
        "project_health": [
            {"project_id": str(ps.project_id), "name": ps.memory_score.get("name"),
             "overall": ps.overall_health_score, "status": ps.overall_health_status}
            for ps in ProjectSnapshot.objects.filter(owner=owner).order_by("-overall_health_score")
        ],
        "recommendations": list_recommendations(owner),
        "alerts": list_alerts(owner, status=AlertStatus.OPEN),
        "predictions": list_predictions(owner),
    }


def read_snapshot(owner):
    """Fetch the materialized org snapshot, materializing once if absent."""
    snap = OrganizationSnapshot.objects.filter(owner=owner).first()
    if snap is None:
        snap = materialize(owner)
    return snap


def list_recommendations(owner) -> list[dict]:
    return [
        {"id": str(r.id), "key": r.key, "priority": r.priority, "recommendation": r.recommendation,
         "reason": r.reason, "evidence": r.evidence, "confidence": r.confidence,
         "impact": r.impact, "related_projects": r.related_projects, "consensus": r.consensus,
         "status": r.status, "knowledge_version": r.knowledge_version,
         "consensus_version": r.consensus_version}
        for r in ExecutiveRecommendation.objects.filter(owner=owner).exclude(
            status__in=[RecommendationStatus.DONE, RecommendationStatus.DISMISSED])
        .order_by("-confidence")
    ]


def list_predictions(owner) -> list[dict]:
    return [
        {"metric": p.metric, "current_value": p.current_value, "expected_value": p.expected_value,
         "horizon_days": p.horizon_days, "confidence": p.confidence, "message": p.message}
        for p in ExecutivePrediction.objects.filter(owner=owner).order_by("horizon_days")
    ]


def explanation_for(owner, scope, metric_key) -> dict | None:
    e = ExecutiveExplanation.objects.filter(owner=owner, scope=scope, metric_key=metric_key).first()
    if not e:
        return None
    return {"scope": e.scope, "metric": e.metric_key, "value": e.value, "formula": e.formula,
            "evidence": e.evidence, "confidence": e.confidence,
            "knowledge_version": e.knowledge_version, "snapshot_version": e.snapshot_version,
            "generated_at": e.generated_at}


def get_trends(owner, *, granularity=TrendGranularity.DAILY, metric=None) -> list[dict]:
    qs = ExecutiveTrendPoint.objects.filter(owner=owner, granularity=granularity)
    if metric:
        qs = qs.filter(metric=metric)
    return [{"metric": t.metric, "period_start": t.period_start, "value": t.value}
            for t in qs.order_by("metric", "period_start")]


# --- Executive Brief (Module 7) + What Changed report ----------------------

_PERIOD_DAYS = {"today": 1, "week": 7, "month": 30}


def executive_report(owner, period: str = "week") -> dict:
    """One-click executive brief for today / this week / this month."""
    from apps.knowledge.services.briefs import executive_brief

    days = _PERIOD_DAYS.get(period, 7)
    since = timezone.now() - timezone.timedelta(days=days)
    today = timezone.now().date()

    tasks = Task.objects.filter(owner=owner)
    achievements = list(tasks.filter(status="completed", updated_at__gte=since)
                        .values("id", "title")[:15])
    blocked_projects = [p for p in ai_insights(owner)["project_health"]
                        if p["tasks"] and p["completed"] / p["tasks"] < 0.3][:8]
    critical_risks = list(Risk.objects.filter(owner=owner, severity__in=["high", "critical"])
                          .exclude(status__in=["closed", "mitigated"]).values("id", "risk", "severity")[:10])
    decisions = list(Decision.objects.filter(owner=owner, created_at__gte=since)
                     .values("id", "decision")[:15])
    deadlines = list(tasks.filter(due_date__gte=today, due_date__lte=today + timezone.timedelta(days=days))
                     .exclude(status__in=["completed", "cancelled"]).values("id", "title", "due_date")[:15])
    changes = what_changed(owner, since)
    consensus_changes = list(KnowledgeConsensus.objects.filter(owner=owner, last_changed__gte=since)
                             .values("topic", "current_position", "trend")[:10])

    brief = executive_brief(owner, {"today": "daily", "week": "weekly", "month": "monthly"}.get(period, "weekly"))

    return {
        "period": period, "since": since, "generated_at": timezone.now(),
        "executive_summary": brief["brief"],
        "top_achievements": achievements,
        "blocked_projects": blocked_projects,
        "critical_risks": critical_risks,
        "important_decisions": decisions,
        "upcoming_deadlines": deadlines,
        "ai_recommendations": list_recommendations(owner)[:6],
        "knowledge_changes": {"version_changes": changes["knowledge_version_changes"],
                              "events": changes["knowledge_events"]},
        "decision_changes": consensus_changes,
        "trend_changes": {"health_delta": changes["health_delta"]},
        "provenance": {"prompt_version": brief.get("prompt_version"), "provider": brief.get("provider")},
    }


# --- History (Module 10) + What Changed + Predictive -----------------------


def _nearest_metric(owner, when):
    return (ExecutiveMetricSnapshot.objects.filter(owner=owner, recorded_at__lte=when)
            .order_by("-recorded_at").first())


def _metric_dict(m):
    if not m:
        return None
    return {"recorded_at": m.recorded_at, "overall_health": m.overall_health,
            "workspace_score": m.workspace_score, "knowledge_items": m.knowledge_items,
            "meetings": m.meetings, "decisions": m.decisions, "open_risks": m.open_risks,
            "tasks_done": m.tasks_done, "open_conflicts": m.open_conflicts,
            "avg_confidence": m.avg_confidence, "decision_stability": m.decision_stability,
            "knowledge_version": m.knowledge_version}


def executive_history(owner) -> dict:
    now = timezone.now()
    points = {
        "now": _nearest_metric(owner, now),
        "last_week": _nearest_metric(owner, now - timezone.timedelta(days=7)),
        "last_month": _nearest_metric(owner, now - timezone.timedelta(days=30)),
        "last_quarter": _nearest_metric(owner, now - timezone.timedelta(days=90)),
    }
    return {k: _metric_dict(v) for k, v in points.items()}


def what_changed(owner, since) -> dict:
    from apps.knowledge.models import KnowledgeEvent

    decisions = Decision.objects.filter(owner=owner, created_at__gte=since)
    resolved = KnowledgeConflict.objects.filter(owner=owner, resolved_at__gte=since,
                                                status=ConflictStatus.RESOLVED)
    kv_changes = KnowledgeVersion.objects.filter(owner=owner, indexed_at__gte=since)
    new_risks = Risk.objects.filter(owner=owner, created_at__gte=since)
    closed_risks = Risk.objects.filter(owner=owner, updated_at__gte=since,
                                       status__in=["closed", "mitigated"])
    events = KnowledgeEvent.objects.filter(owner=owner, created_at__gte=since)
    before = _nearest_metric(owner, since)
    now_m = _nearest_metric(owner, timezone.now())
    health_delta = (round(now_m.overall_health - before.overall_health, 1)
                    if before and now_m else None)
    return {
        "since": since,
        "new_decisions": list(decisions.values("id", "decision")[:20]),
        "resolved_conflicts": list(resolved.values("id", "topic", "category")[:20]),
        "knowledge_version_changes": kv_changes.count(),
        "new_risks": list(new_risks.values("id", "risk", "severity")[:20]),
        "closed_risks": list(closed_risks.values("id", "risk")[:20]),
        "knowledge_events": events.count(),
        "health_delta": health_delta,
        "new_recommendations": [r["title"] for r in recommendations(owner)[:5]],
    }


def predictive_health(owner) -> dict:
    """Heuristic projection from the metric time-series (no ML training)."""
    pts = list(ExecutiveMetricSnapshot.objects.filter(owner=owner).order_by("recorded_at"))
    if len(pts) < 3:
        return {"available": False, "reason": "Not enough history yet (need ≥3 snapshots)."}
    first, last = pts[0], pts[-1]
    span_days = max(1.0, (last.recorded_at - first.recorded_at).total_seconds() / 86400)
    health_slope = (last.overall_health - first.overall_health) / span_days   # pts/day
    blocked_slope = (last.tasks_blocked - first.tasks_blocked) / span_days

    projections = []
    if health_slope < -0.1:
        for threshold, label in ((70, "Good"), (50, "Warning")):
            if last.overall_health > threshold:
                days = (last.overall_health - threshold) / -health_slope
                if days <= 60:
                    projections.append({
                        "metric": "overall_health", "threshold": threshold,
                        "message": f"Workspace health may fall below '{label}' (~{threshold}) "
                                   f"in ~{int(days)} days at the current trend.",
                        "days": int(days)})
    if blocked_slope > 0.05:
        projections.append({
            "metric": "tasks_blocked",
            "message": f"Blocked tasks are rising (~{blocked_slope*7:.1f}/week); "
                       "review dependencies before they stall delivery.",
        })
    return {"available": True, "health_slope_per_day": round(health_slope, 3),
            "blocked_slope_per_day": round(blocked_slope, 3), "projections": projections}
