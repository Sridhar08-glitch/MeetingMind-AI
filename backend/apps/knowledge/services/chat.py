"""Cross-meeting AI chat — grounded, cited answers over the whole workspace.

Retrieves only the relevant evidence (never the full workspace) via the org
search index, prompts the local LLM for a strict-JSON answer with citations, and
returns an AI Sources panel + Knowledge Freshness so users know exactly what the
answer is based on and how current it is. Authorization is enforced by the search
layer (owner-scoped) before any retrieval.
"""
from __future__ import annotations

import json
import logging
import re
import time

from apps.knowledge.models import KnowledgeRetrieval
from apps.knowledge.prompts import ORG_CHAT_SCHEMA, ORG_CHAT_VERSION
from apps.knowledge.services import versioning
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.search import OrgSearchService
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.embeddings import get_embedding_provider
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.meetings.services.media import ProcessingError

logger = logging.getLogger("meetingmind.ai")
NOT_FOUND = "I couldn't find that in your meetings."
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class OrgChatService:
    def __init__(self, llm=None, search=None):
        self.llm = llm or get_llm_provider()
        self.search = search or OrgSearchService()

    def ask(self, owner, question: str, *, project_id=None, filters: dict | None = None, k: int = 8) -> dict:
        question = question.strip()
        filters = dict(filters or {})
        if project_id:
            filters["project"] = project_id

        started = time.perf_counter()
        evidence = self.search.search(owner, question, filters=filters, k=k)
        freshness = KnowledgeIndexService().stats(owner)
        if not evidence:
            self._record(owner, question, evidence, freshness, found=False, answer="",
                         elapsed_ms=int((time.perf_counter() - started) * 1000))
            return {"answer": NOT_FOUND, "found": False, "sources": [], "knowledge_freshness": freshness}

        context = "\n".join(
            f"[{i}] ({e['meeting_title'] or 'meeting'}"
            + (f", {e['speaker']}" if e['speaker'] else "")
            + (f" @{int(e['timestamp'])}s" if e['timestamp'] is not None else "")
            + f") {e['snippet']}"
            for i, e in enumerate(evidence, start=1)
        )
        prompt = prompt_registry.get("org_chat")
        system, user = prompt.render(schema=ORG_CHAT_SCHEMA, context=context, history="", question=question)

        answer, found, cite_idx = self._call(system, user)
        sources = []
        for idx in cite_idx:
            if 1 <= idx <= len(evidence):
                e = evidence[idx - 1]
                sources.append({
                    "meeting_id": e["meeting_id"], "meeting_title": e["meeting_title"],
                    "project_id": e["project_id"], "entity_type": e["entity_type"],
                    "speaker": e["speaker"], "timestamp": e["timestamp"],
                    "quote": e["snippet"], "confidence": e["confidence"],
                })
        # Fall back to the top evidence as sources if the model cited none.
        if found and not sources:
            e = evidence[0]
            sources = [{"meeting_id": e["meeting_id"], "meeting_title": e["meeting_title"],
                        "project_id": e["project_id"], "entity_type": e["entity_type"],
                        "speaker": e["speaker"], "timestamp": e["timestamp"],
                        "quote": e["snippet"], "confidence": e["confidence"]}]
        self._record(owner, question, evidence, freshness, found=found, answer=answer,
                     elapsed_ms=int((time.perf_counter() - started) * 1000))
        return {"answer": answer, "found": found, "sources": sources,
                "knowledge_freshness": freshness, "prompt_version": ORG_CHAT_VERSION,
                "provider": self.llm.name, "model": self.llm.model_name}

    def _record(self, owner, question, evidence, freshness, *, found, answer, elapsed_ms):
        """Persist retrieval provenance so any answer is reproducible/auditable."""
        try:
            emb = get_embedding_provider()
            emb_ver = versioning.register_embedding_version(emb)
            KnowledgeRetrieval.objects.create(
                owner=owner, kind="org_chat", question=question[:2000],
                knowledge_version=freshness.get("knowledge_version", 0),
                embedding_version=emb_ver,
                retrieved_items=[
                    {"item_id": e.get("item_id"), "entity_type": e["entity_type"],
                     "entity_id": e["entity_id"], "score": e.get("confidence"),
                     "knowledge_version": e.get("knowledge_version")}
                    for e in evidence
                ],
                ranking_scores={"top": evidence[0]["confidence"] if evidence else None,
                                "count": len(evidence)},
                response_time_ms=elapsed_ms, llm_provider=self.llm.name,
                llm_model=self.llm.model_name, prompt_version=ORG_CHAT_VERSION,
                found=found, answer_preview=(answer or "")[:500],
            )
        except Exception:  # noqa: BLE001 — provenance must never break the answer
            logger.debug("Failed to record retrieval provenance.", exc_info=True)

    def _call(self, system, user):
        last = None
        for attempt in (1, 2):
            sys_p = system if attempt == 1 else system + " Reply with ONE valid JSON object only."
            try:
                resp = self.llm.generate(user, system=sys_p, json=True, schema_hint="meeting_chat")
            except LLMError as exc:
                raise ProcessingError(f"Org chat LLM failed: {exc.message}", code="llm_error",
                                      retryable=exc.retryable) from exc
            try:
                obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
                answer = str(obj.get("answer", "")).strip()
                found = bool(obj.get("found", True)) and bool(answer)
                cites = [int(c) for c in obj.get("citations", []) if str(c).isdigit()]
                if not answer:
                    return NOT_FOUND, False, []
                return answer, found, cites
            except (json.JSONDecodeError, AttributeError, ValueError) as exc:
                last = exc
        logger.warning("Org chat response invalid: %s", last)
        return NOT_FOUND, False, []
