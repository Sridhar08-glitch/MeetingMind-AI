"""Deterministic LLM provider for automated tests ONLY.

Never used in normal operation (the default is OllamaProvider). Returns a stable,
schema-valid combined analysis so backend tests, APIs, storage and the frontend
work without a running Ollama server.
"""
from __future__ import annotations

import json as jsonlib

from .base import LLMProvider, LLMResponse

_ANALYSIS = {
    "executive_summary": "The team reviewed progress and agreed on next steps for the release.",
    "detailed_summary": (
        "The meeting covered project status, the platform migration timeline, and budget review. "
        "The team confirmed the release is on track and assigned follow-up work."
    ),
    "bullet_summary": [
        "Reviewed action items from last week.",
        "Platform migration is on track for month-end.",
        "Budget numbers to be double-checked before the board meeting.",
    ],
    "meeting_minutes": (
        "1. Progress review\n2. Migration timeline confirmed\n3. Budget check assigned\n4. Next sync scheduled"
    ),
    "action_items": [
        {"task": "Double-check budget numbers", "owner": "Alice", "priority": "high", "due_date": "", "status": "open"},
        {"task": "Follow up with the design team", "owner": "", "priority": "medium", "due_date": "", "status": "open"},
    ],
    "decisions": [
        {"decision": "Proceed with the platform migration", "reason": "On track for month-end", "participants": ["Alice", "Bob"]},
    ],
    "risks": [
        {"risk": "Budget overrun before board meeting", "severity": "medium", "mitigation": "Verify numbers early"},
    ],
    "issues": [
        {"title": "Login page slow under load", "type": "performance", "severity": "high", "description": "Latency spikes reported"},
    ],
    "follow_ups": [
        {"item": "Confirm release-candidate deadline", "owner": ""},
    ],
    "deadlines": [
        {"item": "Platform migration", "date": "end of month"},
    ],
    "keywords": {
        "topics": ["migration", "budget", "release"],
        "technologies": ["platform"],
        "people": ["Alice", "Bob"],
        "companies": [],
        "phrases": ["on track", "board meeting"],
    },
}


class DummyLLMProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def model_name(self) -> str:
        return "dummy"

    def generate(
        self, prompt, *, system="", temperature=None, max_tokens=None, json=False, schema_hint="",
    ) -> LLMResponse:
        if json and schema_hint == "meeting_chat":
            text = jsonlib.dumps({
                "answer": "Based on the transcript, this is a deterministic test answer.",
                "citations": [1],
                "found": True,
            })
        elif json and schema_hint == "agent_synthesis":
            text = jsonlib.dumps({
                "answer": "Based on the gathered evidence, here is a deterministic test answer.",
                "reasoning": "Synthesised from the provided tool evidence.",
                "key_points": ["Point one from evidence", "Point two from evidence"],
                "recommendations": ["Review the highlighted item"],
                "next_actions": ["Assign an owner and a due date"],
                "confidence": 82,
                "found": True,
            })
        elif json and schema_hint == "planner_intent":
            text = jsonlib.dumps({
                "intent": "deterministic test intent",
                "agents": ["knowledge_agent", "executive_agent"],
                "mode": "parallel",
                "reasoning": "These agents cover the request.",
            })
        elif json and schema_hint == "planner_merge":
            text = jsonlib.dumps({
                "answer": "Unified deterministic answer combining the agent findings.",
                "reasoning": "Merged the agent contributions without duplication.",
                "confidence": 84,
            })
        elif json and schema_hint == "nl_filter":
            text = jsonlib.dumps({"entity_type": "", "keywords": prompt.split("Request:")[-1].strip()[:80],
                                  "date_from": "", "date_to": "", "category": ""})
        elif json and schema_hint == "knowledge_consensus":
            text = jsonlib.dumps({
                "current_position": "Proceed with the platform migration",
                "category": "technical",
                "support_count": 2,
                "opposition_count": 1,
                "confidence": 84,
                "resolved": True,
                "reason": "The most recent decision, backed by testing, confirms the direction.",
            })
        elif json and schema_hint == "speaker_naming":
            # Deterministically "recognize" the first speaker only (tests confirm
            # suggestions are stored but never auto-applied).
            text = jsonlib.dumps({
                "speakers": [
                    {"label": "Speaker 1", "name": "Alex Test", "confidence": 90,
                     "evidence": "introduced themselves"},
                ]
            })
        elif json:
            text = jsonlib.dumps(_ANALYSIS)
        elif schema_hint == "translation":
            # Deterministic, recognisably "translated" output for tests.
            src = prompt.split("Text:", 1)[-1].strip()
            text = f"[translated] {src}" if src else "[translated]"
        else:
            text = "This is a deterministic dummy summary for testing."
        return LLMResponse(text=text, model=self.model_name, provider=self.name, inference_ms=1, raw={})

    def supported_languages(self) -> dict[str, str]:
        return {"en": "English", "es": "Spanish", "fr": "French", "ar": "Arabic", "hi": "Hindi"}
