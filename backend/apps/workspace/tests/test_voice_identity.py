"""Phase 15B tests: cross-meeting VoicePerson identity.

Processes meetings through the dummy diarization engine (deterministic fake
embeddings — the SAME label yields the SAME vector across meetings), so a speaker
in meeting B matches a VoicePerson seeded from meeting A. Verifies suggestion-only
matching, tiered confidence, the confirm/merge/split lifecycle, audit trail, and
owner-scoping. Nothing is auto-linked.
"""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.jobs.services import execute_job
from apps.meetings.models import Speaker
from apps.meetings.services.uploads import create_upload
from apps.workspace.enums import VoiceMatchTier, VoicePersonEventType
from apps.workspace.models import VoicePerson, VoicePersonEvent
from apps.workspace.services import voice_identity

pytestmark = pytest.mark.django_db


_SEQ = [0]


def _wav(seconds: int = 40, rate: int = 16000) -> bytes:
    # Vary length per call so uploads have distinct checksums (dummy diarization
    # embeddings are label-based, independent of the audio, so matching is unaffected).
    _SEQ[0] += 1
    extra = _SEQ[0]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * (rate * seconds + extra))
    return buf.getvalue()


def _meeting_with_speakers(user, settings, *, speakers=2, title="M"):
    settings.DIARIZATION_ENABLED = True
    settings.DIARIZATION_PROVIDER = "dummy"
    settings.DIARIZATION_DUMMY_SPEAKERS = speakers
    f = SimpleUploadedFile("talk.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title=title).meeting
    execute_job(str(meeting.meeting_jobs.order_by("-created_at").first().background_job_id))
    meeting.refresh_from_db()
    return meeting


def _first_speaker(meeting):
    return Speaker.objects.filter(meeting=meeting).order_by("label").first()


# --- tiered confidence ------------------------------------------------------
def test_tier_thresholds(settings):
    settings.VOICE_MATCH_AUTO_HIGHLIGHT = 98.0
    settings.VOICE_MATCH_HIGHLY_LIKELY = 95.0
    settings.VOICE_MATCH_POSSIBLE = 90.0
    assert voice_identity.tier_for(99) == VoiceMatchTier.AUTO_HIGHLIGHT
    assert voice_identity.tier_for(96) == VoiceMatchTier.HIGHLY_LIKELY
    assert voice_identity.tier_for(92) == VoiceMatchTier.POSSIBLE
    assert voice_identity.tier_for(80) == VoiceMatchTier.NONE


# --- create + aggregate -----------------------------------------------------
def test_create_from_speaker_links_and_aggregates(user, settings):
    m = _meeting_with_speakers(user, settings, speakers=1)
    sp = _first_speaker(m)
    person = voice_identity.create_from_speaker(sp, display_name="Alice", actor=user)
    sp.refresh_from_db()
    assert sp.voice_person_id == person.id
    assert person.display_name == "Alice"
    assert person.speaker_count == 1 and person.meeting_count == 1
    assert person.voice_centroid_embedding  # signature aggregated
    assert person.total_talk_time > 0
    # Audit: CREATED + LINKED events.
    kinds = set(VoicePersonEvent.objects.filter(voice_person=person).values_list("event_type", flat=True))
    assert {VoicePersonEventType.CREATED, VoicePersonEventType.LINKED} <= kinds


# --- cross-meeting matching (the core feature) ------------------------------
def test_cross_meeting_match_is_suggestion_only(user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=1, title="Meeting A")
    person = voice_identity.create_from_speaker(_first_speaker(m1), display_name="Alice", actor=user)

    m2 = _meeting_with_speakers(user, settings, speakers=1, title="Meeting B")
    sp2 = _first_speaker(m2)
    cands = voice_identity.find_candidates(sp2)
    assert cands, "expected a candidate for the recurring voice"
    assert cands[0]["voice_person"].id == person.id
    assert cands[0]["score"] >= 90  # identical dummy voice → high similarity
    # SUGGESTION ONLY — nothing linked automatically.
    sp2.refresh_from_db()
    assert sp2.voice_person_id is None

    # Confirming the link updates the identity across both meetings.
    voice_identity.link_speaker(person, sp2, actor=user, confidence=cands[0]["score"],
                                tier=cands[0]["tier"])
    person.refresh_from_db()
    assert person.speaker_count == 2 and person.meeting_count == 2


def test_suggest_for_meeting_lists_unlinked_speakers(user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=2, title="A")
    for sp in Speaker.objects.filter(meeting=m1):
        voice_identity.create_from_speaker(sp, display_name=f"P-{sp.label}", actor=user)
    m2 = _meeting_with_speakers(user, settings, speakers=2, title="B")
    rows = voice_identity.suggest_for_meeting(m2)
    assert len(rows) == 2  # both m2 speakers unlinked
    assert all(r["candidates"] for r in rows)  # each has a recurring-voice candidate


# --- lifecycle: confirm / merge / split -------------------------------------
def test_confirm_records_event(user, settings):
    m = _meeting_with_speakers(user, settings, speakers=1)
    person = voice_identity.create_from_speaker(_first_speaker(m), actor=user)
    voice_identity.confirm(person, actor=user)
    person.refresh_from_db()
    assert person.confirmed
    assert VoicePersonEvent.objects.filter(
        voice_person=person, event_type=VoicePersonEventType.CONFIRMED).exists()


def test_merge_relinks_speakers_and_archives_source(user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=1, title="A")
    m2 = _meeting_with_speakers(user, settings, speakers=1, title="B")
    p1 = voice_identity.create_from_speaker(_first_speaker(m1), display_name="Alice", actor=user)
    p2 = voice_identity.create_from_speaker(_first_speaker(m2), display_name="Alicia", actor=user)

    merged = voice_identity.merge(p1, p2, actor=user)
    assert merged.id == p1.id
    assert merged.speaker_count == 2
    assert "Alicia" in merged.aliases
    assert not VoicePerson.objects.filter(id=p2.id).exists()  # source soft-deleted


def test_split_creates_new_identity(user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=1, title="A")
    m2 = _meeting_with_speakers(user, settings, speakers=1, title="B")
    person = voice_identity.create_from_speaker(_first_speaker(m1), display_name="Alice", actor=user)
    sp2 = _first_speaker(m2)
    voice_identity.link_speaker(person, sp2, actor=user)
    assert person.speaker_count == 2

    new_person = voice_identity.split(person, [str(sp2.id)], new_name="Bob", actor=user)
    person.refresh_from_db()
    assert new_person.display_name == "Bob"
    assert new_person.speaker_count == 1
    assert person.speaker_count == 1
    sp2.refresh_from_db()
    assert sp2.voice_person_id == new_person.id


def test_unlink_recomputes(user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=1, title="A")
    m2 = _meeting_with_speakers(user, settings, speakers=1, title="B")
    person = voice_identity.create_from_speaker(_first_speaker(m1), actor=user)
    sp2 = _first_speaker(m2)
    voice_identity.link_speaker(person, sp2, actor=user)
    assert person.speaker_count == 2
    voice_identity.unlink_speaker(sp2, actor=user)
    person.refresh_from_db()
    assert person.speaker_count == 1


# --- owner-scoping ----------------------------------------------------------
def test_matching_is_owner_scoped(user, settings):
    other = User.objects.create_user(email="bob@example.com", password="x")
    m_other = _meeting_with_speakers(other, settings, speakers=1, title="Other")
    voice_identity.create_from_speaker(_first_speaker(m_other), display_name="Bob", actor=other)

    m_mine = _meeting_with_speakers(user, settings, speakers=1, title="Mine")
    cands = voice_identity.find_candidates(_first_speaker(m_mine))
    assert cands == []  # never see another owner's identities


# --- API --------------------------------------------------------------------
def test_voice_identity_api_flow(auth_client, user, settings):
    m1 = _meeting_with_speakers(user, settings, speakers=1, title="A")
    sp1 = _first_speaker(m1)
    # Create identity from a speaker.
    resp = auth_client.post(
        "/api/workspace/voice-people/from-speaker/",
        {"speaker": str(sp1.id), "display_name": "Alice"}, format="json",
    )
    assert resp.status_code == 201
    person_id = resp.data["data"]["id"]

    # Candidates for a recurring voice in a new meeting.
    m2 = _meeting_with_speakers(user, settings, speakers=1, title="B")
    sp2 = _first_speaker(m2)
    cand = auth_client.get(f"/api/workspace/voice-people/candidates/?speaker={sp2.id}")
    assert cand.status_code == 200
    assert cand.data["data"]["candidates"][0]["voice_person"]["id"] == person_id
    assert cand.data["data"]["candidates"][0]["tier"] in {
        VoiceMatchTier.AUTO_HIGHLIGHT, VoiceMatchTier.HIGHLY_LIKELY, VoiceMatchTier.POSSIBLE
    }

    # Link + confirm.
    link = auth_client.post(f"/api/workspace/voice-people/{person_id}/link/",
                            {"speaker": str(sp2.id)}, format="json")
    assert link.status_code == 200
    assert link.data["data"]["speaker_count"] == 2
    conf = auth_client.post(f"/api/workspace/voice-people/{person_id}/confirm/")
    assert conf.status_code == 200 and conf.data["data"]["confirmed"] is True

    # Audit trail is populated.
    ev = auth_client.get(f"/api/workspace/voice-people/{person_id}/events/")
    assert ev.status_code == 200
    assert len(ev.data["data"]) >= 3
