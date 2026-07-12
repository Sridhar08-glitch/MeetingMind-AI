"""AI meeting chat — grounded, cited Q&A over a single meeting (Phase 8).

Pipeline per question: retrieve relevant transcript segments (RAG) → build a
context from those segments + the meeting's AI summary/action-items/decisions →
prompt the local LLM for a strict JSON answer with citations → validate (retry
once) → store the turn with transcript-grounded citations.

The assistant answers ONLY from the meeting; if the answer isn't there it says
so rather than inventing one.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.accounts.models import User
from apps.meetings.enums import ChatRole
from apps.meetings.models import ChatConversation, ChatMessage, MessageCitation, TranscriptSegment
from apps.meetings.prompts import CHAT_VERSION, chat_schema, prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.meetings.services.media import ProcessingError
from apps.meetings.services.retrieval import RetrievalService, is_overview_query

logger = logging.getLogger("meetingmind.ai")

NOT_FOUND = "I couldn't find that information in this meeting."

SUGGESTED_QUESTIONS = [
    "Summarize this meeting",
    "List the action items",
    "Who owns each task?",
    "What decisions were made?",
    "What risks were mentioned?",
    "What deadlines exist?",
    "Generate a follow-up email",
]

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ChatResult:
    answer: str
    found: bool
    citation_indices: list[int]
    model: str
    provider: str
    prompt_version: str
    inference_ms: int
    raw: str


class ContextBuilder:
    """Assemble a compact, grounded context from meeting data."""

    def summary_block(self, meeting) -> str:
        analysis = meeting.analyses.filter(is_current=True).order_by("-version").first()
        if not analysis:
            return ""
        parts = []
        if analysis.executive_summary:
            parts.append(f"Summary: {analysis.executive_summary}")
        if analysis.action_items:
            items = "; ".join(f"{a.get('task','')} ({a.get('owner') or 'unassigned'})" for a in analysis.action_items[:8])
            parts.append(f"Action items: {items}")
        if analysis.decisions:
            parts.append("Decisions: " + "; ".join(d.get("decision", "") for d in analysis.decisions[:6]))
        return "\n".join(parts)

    def build(self, segments: list[TranscriptSegment]) -> str:
        lines = []
        for i, seg in enumerate(segments, start=1):
            ts = f"{int(seg.start_time) // 60:02d}:{int(seg.start_time) % 60:02d}"
            speaker = f"{seg.speaker}: " if seg.speaker else ""
            lines.append(f"[{i}] ({ts}) {speaker}{seg.text}")
        return "\n".join(lines)


class ChatService:
    def __init__(self, llm=None, retriever: RetrievalService | None = None):
        self.llm = llm or get_llm_provider()
        self.retriever = retriever or RetrievalService()
        self.context_builder = ContextBuilder()

    # --- public ----------------------------------------------------------
    @transaction.atomic
    def ask(self, conversation: ChatConversation, question: str, *, actor: User | None = None) -> ChatMessage:
        meeting = conversation.meeting
        question = question.strip()

        # Store the user turn first.
        user_msg = ChatMessage(conversation=conversation, meeting=meeting, role=ChatRole.USER, content=question)
        if actor:
            user_msg.set_acting_user(actor)
        user_msg.save()

        segments = self.retriever.retrieve(meeting, question)
        result = self._answer(conversation, meeting, question, segments)

        assistant = ChatMessage(
            conversation=conversation, meeting=meeting, role=ChatRole.ASSISTANT,
            content=result.answer, found=result.found, provider=result.provider,
            model_used=result.model, prompt_version=result.prompt_version,
            inference_ms=result.inference_ms,
        )
        if actor:
            assistant.set_acting_user(actor)
        assistant.save()

        # Map validated citations (only segments we actually provided) to rows.
        cited = []
        for idx in result.citation_indices:
            if 1 <= idx <= len(segments):
                seg = segments[idx - 1]
                MessageCitation.objects.create(
                    message=assistant, segment=seg, index=seg.index,
                    start_time=seg.start_time, end_time=seg.end_time, snippet=seg.text[:200],
                )
                cited.append({"index": seg.index, "start_time": seg.start_time, "text": seg.text[:200]})
        assistant.citations = cited
        assistant.save(update_fields=["citations", "updated_at"])

        # Auto-title a new conversation from its first question.
        if conversation.title == "New conversation":
            conversation.title = question[:80]
            conversation.save(update_fields=["title", "updated_at"])
        return assistant

    # --- internals -------------------------------------------------------
    def _history_block(self, conversation: ChatConversation) -> str:
        turns = list(
            conversation.messages.order_by("-created_at")[: settings.CHAT_HISTORY_TURNS * 2]
        )[::-1]
        if not turns:
            return ""
        lines = [f"{'User' if m.role == ChatRole.USER else 'Assistant'}: {m.content}" for m in turns]
        return "Conversation so far:\n" + "\n".join(lines) + "\n\n"

    def _answer(self, conversation, meeting, question, segments) -> ChatResult:
        if not segments:
            return ChatResult(NOT_FOUND, False, [], self._model(), self._provider(), CHAT_VERSION, 0, "")

        # Summary/overview questions ("summarize this meeting", "key points",
        # "recap"…) are answered DETERMINISTICALLY from the meeting's already-
        # computed AI analysis. A small local model otherwise sometimes returns a
        # spurious "not found" for broad summary requests (notably as the first
        # turn, before any conversation history anchors it).
        overview = self._overview_answer(meeting, question, segments)
        if overview is not None:
            return overview

        prompt = prompt_registry.get("meeting_chat")
        system, user = prompt.render(
            schema=chat_schema(),
            title=meeting.title,
            summary=self.context_builder.summary_block(meeting),
            context=self.context_builder.build(segments),
            history=self._history_block(conversation),
            question=question,
        )
        total_ms = 0
        last_error = None
        for attempt in (1, 2):
            sys_prompt = system if attempt == 1 else system + " Reply with ONE valid JSON object only."
            try:
                resp = self.llm.generate(user, system=sys_prompt, json=True, schema_hint="meeting_chat")
            except LLMError as exc:
                raise ProcessingError(f"Chat LLM failed: {exc.message}", code="llm_error",
                                      retryable=exc.retryable) from exc
            total_ms += resp.inference_ms
            try:
                obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
                answer = str(obj.get("answer", "")).strip()
                found = bool(obj.get("found", True)) and bool(answer)
                cites = [int(c) for c in obj.get("citations", []) if isinstance(c, (int, float, str)) and str(c).isdigit()]
                if not answer:
                    answer, found, cites = NOT_FOUND, False, []
                return ChatResult(answer, found, cites, resp.model, resp.provider, CHAT_VERSION, total_ms, resp.text)
            except (json.JSONDecodeError, AttributeError, ValueError) as exc:
                last_error = exc
                logger.warning("Chat JSON validation failed (attempt %s): %s", attempt, exc)
        # Fall back to a safe grounded message rather than surfacing raw text.
        logger.error("Chat response invalid after retry: %s", last_error)
        return ChatResult(NOT_FOUND, False, [], self._model(), self._provider(), CHAT_VERSION, total_ms, "")

    def _overview_answer(self, meeting, question, segments) -> ChatResult | None:
        """A grounded summary answer built from the stored AI analysis, or None."""
        if not is_overview_query(question):
            return None
        analysis = meeting.analyses.filter(is_current=True).order_by("-version").first()
        if not analysis or not analysis.executive_summary:
            return None  # AI not ready yet — fall through to the LLM path
        parts = [analysis.executive_summary]
        if analysis.bullet_summary:
            parts.append("Key points:\n" + "\n".join(f"- {b}" for b in analysis.bullet_summary[:6]))
        if analysis.action_items:
            parts.append(
                "Action items:\n"
                + "\n".join(
                    f"- {a.get('task', '')}" + (f" — {a.get('owner')}" if a.get("owner") else "")
                    for a in analysis.action_items[:6]
                )
            )
        answer = "\n\n".join(parts)
        cites = list(range(1, min(3, len(segments)) + 1))  # ground to the opening segments
        return ChatResult(answer, True, cites, self._model(), self._provider(), CHAT_VERSION, 0, "")

    def _model(self) -> str:
        return self.llm.model_name

    def _provider(self) -> str:
        return self.llm.name


# --- conversation management ------------------------------------------------
def start_conversation(meeting, *, title: str = "New conversation", actor: User | None = None) -> ChatConversation:
    conv = ChatConversation(meeting=meeting, title=title or "New conversation")
    if actor:
        conv.set_acting_user(actor)
    conv.save()
    return conv
