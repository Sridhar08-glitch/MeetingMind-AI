"""Phase 8 tests: chat conversations, retrieval, grounding, citations, API.

All tests run on the deterministic Dummy LLM + Dummy embeddings (forced via
conftest) — no Ollama server required.
"""
from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.meetings.enums import ChatRole, ProcessingStatus
from apps.meetings.models import ChatConversation, Meeting, MessageCitation, TranscriptSegment
from apps.meetings.services.chat import NOT_FOUND, ChatService, start_conversation
from apps.meetings.services.retrieval import RetrievalService

pytestmark = pytest.mark.django_db

TRANSCRIPT_LINES = [
    "We decided to migrate the database to Postgres 16.",
    "Bob will fix the authentication bug by Friday.",
    "The main risk is the vendor API rate limit during peak hours.",
    "Carol owns the deployment pipeline and will update it next week.",
    "The launch deadline is March 15th.",
]


@pytest.fixture
def meeting_with_transcript(user):
    m = Meeting.objects.create(owner=user, title="Team Sync", processing_status=ProcessingStatus.COMPLETED)
    for i, line in enumerate(TRANSCRIPT_LINES):
        TranscriptSegment.objects.create(
            meeting=m, index=i, start_time=i * 12.0, end_time=i * 12.0 + 12,
            text=line, confidence=0.9, word_count=len(line.split()),
        )
    return m


# --- retrieval --------------------------------------------------------------
def test_retrieval_returns_relevant_segments(meeting_with_transcript):
    segs = RetrievalService().retrieve(meeting_with_transcript, "who owns deployment?", k=3)
    assert len(segs) <= 3
    # The deployment segment should be retrieved.
    assert any("deployment" in s.text.lower() for s in segs)


def test_retrieval_empty_for_no_transcript(user):
    m = Meeting.objects.create(owner=user, title="Empty")
    assert RetrievalService().retrieve(m, "anything") == []


def test_keyword_and_timestamp_search(meeting_with_transcript):
    assert RetrievalService.keyword_search(meeting_with_transcript, "deadline")
    assert RetrievalService.timestamp_search(meeting_with_transcript, 0, 15)


# --- chat service -----------------------------------------------------------
def test_ask_produces_grounded_cited_answer(meeting_with_transcript, user):
    conv = start_conversation(meeting_with_transcript, actor=user)
    assistant = ChatService().ask(conv, "What did we decide about the database?", actor=user)

    assert assistant.role == ChatRole.ASSISTANT
    assert assistant.found is True
    assert assistant.content
    assert assistant.provider == "dummy"
    # A citation row was created, referencing a real retrieved segment.
    cites = MessageCitation.objects.filter(message=assistant)
    assert cites.exists()
    assert cites.first().segment is not None
    # Both user + assistant turns are stored.
    assert conv.messages.count() == 2


def test_not_found_when_no_transcript(user):
    m = Meeting.objects.create(owner=user, title="No transcript")
    conv = start_conversation(m, actor=user)
    assistant = ChatService().ask(conv, "What decisions were made?", actor=user)
    assert assistant.found is False
    assert assistant.content == NOT_FOUND
    assert not MessageCitation.objects.filter(message=assistant).exists()


def test_conversation_auto_titles_from_first_question(meeting_with_transcript, user):
    conv = start_conversation(meeting_with_transcript, actor=user)
    ChatService().ask(conv, "Who owns the deployment pipeline?", actor=user)
    conv.refresh_from_db()
    assert conv.title.startswith("Who owns")


def test_follow_up_uses_history(meeting_with_transcript, user):
    conv = start_conversation(meeting_with_transcript, actor=user)
    ChatService().ask(conv, "What is the deadline?", actor=user)
    ChatService().ask(conv, "And who owns deployment?", actor=user)
    assert conv.messages.count() == 4  # two Q&A pairs


# --- API --------------------------------------------------------------------
def test_conversation_api_flow(auth_client, meeting_with_transcript):
    mid = str(meeting_with_transcript.id)
    # create
    created = auth_client.post("/api/meetings/conversations/", {"meeting": mid}, format="json")
    assert created.status_code == 201
    cid = created.data["data"]["id"]

    # ask
    ask = auth_client.post(f"/api/meetings/conversations/{cid}/ask/",
                           {"question": "What are the risks?"}, format="json")
    assert ask.status_code == 200
    assert ask.data["data"]["role"] == "assistant"

    # retrieve (with messages + citations)
    detail = auth_client.get(f"/api/meetings/conversations/{cid}/")
    assert detail.status_code == 200
    assert len(detail.data["messages"]) == 2

    # rename
    renamed = auth_client.patch(f"/api/meetings/conversations/{cid}/", {"title": "Risks chat"}, format="json")
    assert renamed.status_code == 200

    # list scoped to meeting
    lst = auth_client.get(f"/api/meetings/conversations/?meeting={mid}")
    assert lst.status_code == 200
    assert lst.data["count"] == 1

    # delete
    assert auth_client.delete(f"/api/meetings/conversations/{cid}/").status_code == 200
    assert not ChatConversation.objects.filter(id=cid).exists()


def test_multiple_conversations_per_meeting(auth_client, meeting_with_transcript):
    mid = str(meeting_with_transcript.id)
    auth_client.post("/api/meetings/conversations/", {"meeting": mid}, format="json")
    auth_client.post("/api/meetings/conversations/", {"meeting": mid}, format="json")
    lst = auth_client.get(f"/api/meetings/conversations/?meeting={mid}")
    assert lst.data["count"] == 2


def test_suggested_questions(auth_client):
    resp = auth_client.get("/api/meetings/chat/suggested/")
    assert resp.status_code == 200
    assert "Summarize this meeting" in resp.data["data"]


def test_cannot_access_other_users_conversation(auth_client, api_client, meeting_with_transcript):
    conv = start_conversation(meeting_with_transcript)
    other = UserFactory()
    login = api_client.post(
        "/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api_client.get(f"/api/meetings/conversations/{conv.id}/").status_code in (403, 404)
    assert api_client.post(f"/api/meetings/conversations/{conv.id}/ask/",
                           {"question": "hi"}, format="json").status_code in (403, 404)


def test_no_cross_meeting_leakage(meeting_with_transcript, user):
    # A second meeting with different content.
    other = Meeting.objects.create(owner=user, title="Other", processing_status=ProcessingStatus.COMPLETED)
    TranscriptSegment.objects.create(meeting=other, index=0, start_time=0, end_time=5,
                                     text="Completely unrelated budget discussion.", confidence=0.9)
    conv = start_conversation(other, actor=user)
    ChatService().ask(conv, "Who owns deployment?", actor=user)
    # Citations must only reference the *other* meeting's segments.
    for cite in MessageCitation.objects.filter(message__meeting=other):
        assert cite.segment.meeting_id == other.id
