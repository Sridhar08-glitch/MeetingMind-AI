"""Natural Language Filters (Phase 11C improvement #4).

Translates plain-English requests ("show only customer risks", "meetings from
March mentioning Redis") into a STRUCTURED filter via the local LLM, then runs it
through the existing owner-scoped retrieval layer. A deterministic keyword
fallback keeps it working offline if the LLM is unavailable. Never bypasses
authorization — OrgSearchService enforces owner scope.
"""
from __future__ import annotations

import json
import logging
import re

from django.utils import timezone

from apps.knowledge.models import KnowledgeEntityType
from apps.knowledge.prompts import NL_FILTER_SCHEMA, NL_FILTER_VERSION
from apps.knowledge.services.search import OrgSearchService
from apps.meetings.prompts import prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider

logger = logging.getLogger("meetingmind.ai")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_ENTITY_WORDS = {
    "risk": "risk", "risks": "risk", "task": "task", "tasks": "task",
    "decision": "decision", "decisions": "decision", "meeting": "meeting",
    "meetings": "meeting", "report": "report", "reports": "report",
    "issue": "issue", "issues": "issue",
}
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_CATEGORY_WORDS = ["customer", "security", "performance", "compliance", "budget", "timeline"]


def _fallback(query: str) -> dict:
    low = query.lower()
    entity_type = next((v for w, v in _ENTITY_WORDS.items() if re.search(rf"\b{w}\b", low)), "")
    category = next((c for c in _CATEGORY_WORDS if c in low), "")
    date_from = date_to = ""
    for name, num in _MONTHS.items():
        if name in low:
            year = timezone.now().year
            date_from = f"{year}-{num:02d}-01"
            date_to = f"{year}-{num:02d}-28"
            break
    # Keywords = query minus obvious structural words.
    keywords = re.sub(r"\b(show|only|me|from|the|with|in|mentioning|about|of)\b", " ", low)
    return {"entity_type": entity_type, "keywords": keywords.strip(),
            "date_from": date_from, "date_to": date_to, "category": category}


def _interpret(query: str) -> dict:
    prompt = prompt_registry.get("nl_filter")
    system, user = prompt.render(schema=NL_FILTER_SCHEMA, today=timezone.now().date().isoformat(),
                                 query=query)
    try:
        resp = get_llm_provider().generate(user, system=system, json=True, schema_hint="nl_filter")
        obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
        return {"entity_type": str(obj.get("entity_type", "")).strip(),
                "keywords": str(obj.get("keywords", "")).strip() or query,
                "date_from": str(obj.get("date_from", "")).strip(),
                "date_to": str(obj.get("date_to", "")).strip(),
                "category": str(obj.get("category", "")).strip()}
    except (LLMError, json.JSONDecodeError, AttributeError, ValueError, TypeError) as exc:
        logger.warning("NL filter LLM failed (%s); using keyword fallback.", exc)
        return _fallback(query)


def natural_language_query(owner, query: str, *, k: int = 12) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": query, "filters": {}, "results": []}
    interp = _interpret(query)
    filters = {}
    # Only trust entity_type if it's a REAL type — the LLM sometimes returns a
    # topic word (e.g. "redis") here, which would filter out every result.
    etype = (interp["entity_type"] or "").strip().lower()
    if etype in KnowledgeEntityType.values:
        filters["entity_type"] = etype
    elif etype and etype not in interp["keywords"].lower():
        # Fold the bogus type back into the free-text search instead of dropping it.
        interp["keywords"] = f"{interp['keywords']} {etype}".strip()
    if interp["date_from"]:
        filters["date_from"] = interp["date_from"]
    if interp["date_to"]:
        filters["date_to"] = interp["date_to"]
    search_text = " ".join(x for x in (interp["keywords"], interp["category"]) if x).strip() or query
    results = OrgSearchService().search(owner, search_text, filters=filters, k=k)
    return {"query": query, "interpreted": interp, "filters": filters,
            "search_text": search_text, "count": len(results), "results": results,
            "prompt_version": NL_FILTER_VERSION}
