"""Organizational reasoning (Phase 11B): AI Consensus, Consensus Evolution,
Contradiction Detection/Categorization/Resolution, and the conflict registry.

Decisions made across DIFFERENT meetings about the SAME topic are grouped, and a
local LLM determines the CURRENT consensus (which position holds now, how many
decisions support vs oppose it, the contradiction category, and why). Results are
cached in :class:`KnowledgeConsensus` / :class:`KnowledgeConflict` so the
expensive reasoning isn't recomputed on every request; each position change is
recorded as an immutable :class:`KnowledgeConsensusRevision` (Consensus
Evolution). A deterministic fallback keeps everything working if the LLM is down.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict

from django.db import transaction
from django.utils import timezone

from apps.knowledge.models import (
    ConflictCategory,
    ConflictStatus,
    ConsensusTrend,
    KnowledgeConflict,
    KnowledgeConsensus,
    KnowledgeConsensusRevision,
)
from apps.knowledge.prompts import CONSENSUS_SCHEMA, CONSENSUS_VERSION
from apps.knowledge.services.versioning import current_version
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.workspace.models import Decision

logger = logging.getLogger("meetingmind.ai")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_STOP = set(
    "the a an and or of to in on for with at by from is are was were be this that "
    "we our you your it its their they will can should would our us new".split()
)
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#-]{2,}")

# Keyword hints for classifying a contradiction category without the LLM.
_CATEGORY_HINTS = {
    ConflictCategory.SECURITY: ["auth", "oauth", "jwt", "oidc", "security", "encrypt", "password", "token", "vulnerab"],
    ConflictCategory.PERFORMANCE: ["performance", "latency", "load", "throughput", "scal", "cache", "redis", "speed"],
    ConflictCategory.TIMELINE: ["deadline", "timeline", "schedule", "delay", "sprint", "milestone", "late"],
    ConflictCategory.ARCHITECTURE: ["architecture", "microservice", "monolith", "design pattern", "refactor", "structure"],
    ConflictCategory.COMPLIANCE: ["compliance", "gdpr", "hipaa", "regulation", "legal", "audit", "policy"],
    ConflictCategory.CUSTOMER: ["customer", "client", "churn", "support ticket", "user feedback"],
    ConflictCategory.BUSINESS: ["budget", "cost", "revenue", "pricing", "market", "roi", "sales"],
    ConflictCategory.TECHNICAL: ["database", "postgres", "mysql", "api", "framework", "library", "stack", "migration"],
    ConflictCategory.RISK: ["risk", "threat", "exposure"],
}


def _categorize(text: str) -> str:
    low = text.lower()
    for category, hints in _CATEGORY_HINTS.items():
        if any(h in low for h in hints):
            return category
    return ConflictCategory.GENERAL


def _topic_groups(owner) -> dict[str, list[Decision]]:
    """Decisions grouped by a shared salient topic word (across ≥2 meetings)."""
    by_topic: dict[str, list[Decision]] = defaultdict(list)
    for d in (Decision.objects.filter(owner=owner).select_related("meeting")
              .exclude(status="reversed")):
        words = [w.lower() for w in _WORD.findall(d.decision) if w.lower() not in _STOP]
        for key in {w for w, _ in Counter(words).most_common(3)}:
            by_topic[key].append(d)
    return {t: decs for t, decs in by_topic.items()
            if len(decs) >= 2 and len({d.meeting_id for d in decs}) >= 2}


class ConsensusService:
    def __init__(self, llm=None):
        self.llm = llm or get_llm_provider()

    # -- LLM resolution (with deterministic fallback) -----------------------

    def _resolve(self, topic: str, decisions: list[Decision]) -> dict:
        ordered = sorted(decisions, key=lambda d: d.decided_at or timezone.now())
        block = "\n".join(
            f"- \"{d.decision[:200]}\" (meeting: {d.meeting.title if d.meeting else 'n/a'}, "
            f"date: {d.decided_at:%Y-%m-%d}, status: {d.status})"
            for d in ordered
        )
        prompt = prompt_registry.get("knowledge_consensus")
        system, user = prompt.render(schema=CONSENSUS_SCHEMA, topic=topic, decisions=block)
        try:
            resp = self.llm.generate(user, system=system, json=True, schema_hint="knowledge_consensus")
            obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
            return self._normalize(obj, topic, ordered, provider=self.llm.name,
                                   model=self.llm.model_name)
        except (LLMError, json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
            logger.warning("Consensus LLM failed for topic '%s' (%s); using fallback.", topic, exc)
            return self._fallback(topic, ordered)

    def _normalize(self, obj, topic, ordered, *, provider, model) -> dict:
        n = len(ordered)
        opp = max(0, min(n, int(obj.get("opposition_count", 0) or 0)))
        sup = obj.get("support_count")
        sup = max(0, min(n, int(sup))) if str(sup).isdigit() or isinstance(sup, int) else (n - opp)
        category = str(obj.get("category", "")).strip().lower()
        if category not in ConflictCategory.values:
            category = _categorize(" ".join(d.decision for d in ordered))
        return {
            "current_position": str(obj.get("current_position", "")).strip() or ordered[-1].decision,
            "category": category,
            "support_count": sup,
            "opposition_count": opp,
            "confidence": float(max(0, min(100, obj.get("confidence", 60) or 60))),
            "resolved": bool(obj.get("resolved", opp == 0)),
            "reason": str(obj.get("reason", "")).strip(),
            "provider": provider, "model": model, "prompt_version": CONSENSUS_VERSION,
        }

    def _fallback(self, topic, ordered) -> dict:
        """No LLM: most recent decision wins; opposition = reversed/older variety."""
        return {
            "current_position": ordered[-1].decision,
            "category": _categorize(" ".join(d.decision for d in ordered)),
            "support_count": len(ordered),
            "opposition_count": 0,
            "confidence": 60.0,
            "resolved": True,
            "reason": "Most recent decision taken as the current position (LLM unavailable).",
            "provider": "", "model": "", "prompt_version": CONSENSUS_VERSION,
        }

    # -- Persistence + evolution -------------------------------------------

    def compute(self, owner, *, persist: bool = True) -> list[dict]:
        groups = _topic_groups(owner)
        kv = current_version(owner)
        out = []
        for topic, decisions in groups.items():
            result = self._resolve(topic, decisions)
            if persist:
                consensus = self._persist(owner, topic, decisions, result, kv)
                out.append(_serialize_consensus(consensus))
            else:
                out.append({"topic": topic, **result})
        out.sort(key=lambda c: -(c.get("opposition_count", 0)))
        return out

    @transaction.atomic
    def _persist(self, owner, topic, decisions, result, kv) -> KnowledgeConsensus:
        evidence = {
            "decision_ids": [str(d.id) for d in decisions],
            "meeting_ids": list({str(d.meeting_id) for d in decisions if d.meeting_id}),
        }
        existing = KnowledgeConsensus.objects.filter(owner=owner, topic=topic).first()
        new_pos = result["current_position"].strip()
        now = timezone.now()

        if existing is None:
            trend = ConsensusTrend.NEW
        elif new_pos.lower() != (existing.current_position or "").lower():
            trend = ConsensusTrend.SHIFTING
        elif result["confidence"] > existing.confidence + 2:
            trend = ConsensusTrend.STRENGTHENING
        elif result["confidence"] < existing.confidence - 2:
            trend = ConsensusTrend.WEAKENING
        else:
            trend = ConsensusTrend.STABLE

        position_changed = existing is None or trend == ConsensusTrend.SHIFTING

        consensus, _ = KnowledgeConsensus.objects.update_or_create(
            owner=owner, topic=topic,
            defaults={
                "category": result["category"], "current_position": new_pos,
                "confidence": result["confidence"], "support_count": result["support_count"],
                "opposition_count": result["opposition_count"], "reason": result["reason"],
                "evidence": evidence, "knowledge_version": kv, "trend": trend,
                "provider": result["provider"], "model": result["model"],
                "prompt_version": result["prompt_version"],
                "last_changed": now if position_changed else (existing.last_changed if existing else now),
            },
        )

        if position_changed:
            KnowledgeConsensusRevision.objects.create(
                consensus=consensus, owner=owner, position=new_pos,
                confidence=result["confidence"], support_count=result["support_count"],
                opposition_count=result["opposition_count"], knowledge_version=kv, recorded_at=now,
            )
        # Recompute stability from how many times the position has shifted.
        changes = max(0, consensus.revisions.count() - 1)
        consensus.stability_score = max(0.0, 100.0 - 18.0 * changes)
        consensus.save(update_fields=["stability_score", "updated_at"])

        self._sync_conflict(owner, topic, decisions, result, consensus)
        return consensus

    def _sync_conflict(self, owner, topic, decisions, result, consensus) -> None:
        """Maintain the conflict registry for topics with opposition."""
        is_conflict = result["opposition_count"] > 0 or not result["resolved"]
        if not is_conflict:
            KnowledgeConflict.objects.filter(owner=owner, topic=topic,
                                             status=ConflictStatus.OPEN).update(
                status=ConflictStatus.RESOLVED, resolved_at=timezone.now(),
                consensus=consensus, confidence=result["confidence"],
                reason=result["reason"])
            return
        positions = [
            {"decision_id": str(d.id), "decision": d.decision[:200],
             "meeting_id": str(d.meeting_id) if d.meeting_id else None,
             "meeting_title": d.meeting.title if d.meeting else None,
             "status": d.status,
             "decided_at": d.decided_at.isoformat() if d.decided_at else None}
            for d in sorted(decisions, key=lambda x: x.decided_at or timezone.now())
        ]
        existing = KnowledgeConflict.objects.filter(owner=owner, topic=topic).first()
        # Don't clobber a manually-resolved/dismissed conflict.
        status = existing.status if existing and existing.status in (
            ConflictStatus.RESOLVED, ConflictStatus.DISMISSED) else ConflictStatus.OPEN
        KnowledgeConflict.objects.update_or_create(
            owner=owner, topic=topic,
            defaults={
                "category": result["category"], "status": status, "positions": positions,
                "decision_count": len(decisions),
                "meeting_count": len({d.meeting_id for d in decisions}),
                "consensus": consensus, "confidence": result["confidence"],
                "reason": result["reason"], "provider": result["provider"],
                "model": result["model"], "prompt_version": result["prompt_version"],
            },
        )


def _serialize_consensus(c: KnowledgeConsensus) -> dict:
    return {
        "id": str(c.id), "topic": c.topic, "category": c.category,
        "current_position": c.current_position, "confidence": c.confidence,
        "support_count": c.support_count, "opposition_count": c.opposition_count,
        "trend": c.trend, "stability_score": c.stability_score,
        "last_changed": c.last_changed, "reason": c.reason,
        "knowledge_version": c.knowledge_version,
        "revision_count": c.revisions.count(),
    }


# -- Read side ---------------------------------------------------------------


def list_consensus(owner) -> list[dict]:
    return [_serialize_consensus(c)
            for c in KnowledgeConsensus.objects.filter(owner=owner).prefetch_related("revisions")
            .order_by("-opposition_count", "topic")]


def consensus_evolution(owner, topic: str) -> dict:
    c = KnowledgeConsensus.objects.filter(owner=owner, topic__iexact=topic).first()
    if not c:
        return {"topic": topic, "found": False, "timeline": []}
    timeline = [
        {"position": r.position, "confidence": r.confidence,
         "support_count": r.support_count, "opposition_count": r.opposition_count,
         "at": r.recorded_at, "knowledge_version": r.knowledge_version}
        for r in c.revisions.all()
    ]
    return {"topic": c.topic, "found": True, "current": _serialize_consensus(c),
            "timeline": timeline}


def list_conflicts(owner, *, status: str | None = None, category: str | None = None) -> list[dict]:
    qs = KnowledgeConflict.objects.filter(owner=owner).select_related("consensus")
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    return [
        {"id": str(c.id), "topic": c.topic, "category": c.category, "status": c.status,
         "decision_count": c.decision_count, "meeting_count": c.meeting_count,
         "positions": c.positions, "confidence": c.confidence, "reason": c.reason,
         "resolved_decision_id": str(c.resolved_decision_id) if c.resolved_decision_id else None,
         "resolved_at": c.resolved_at}
        for c in qs.order_by("status", "-decision_count")
    ]


def resolve_conflict(owner, conflict: KnowledgeConflict, *, resolved_by=None,
                     decision: Decision | None = None, status: str = ConflictStatus.RESOLVED,
                     reason: str = "") -> KnowledgeConflict:
    conflict.status = status
    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    if decision is not None:
        conflict.resolved_decision = decision
        conflict.resolved_meeting = decision.meeting
    if reason:
        conflict.reason = reason
    conflict.save(update_fields=["status", "resolved_by", "resolved_at",
                                 "resolved_decision", "resolved_meeting", "reason", "updated_at"])
    return conflict
