"""Phase 11A — temporal knowledge tests: append-only versioning, immutable
event stream, knowledge versioning, time-travel, timeline, decision evolution,
embedding-version tracking, and retrieval provenance. Owner-scoped throughout."""
from __future__ import annotations

import pytest
from django.utils import timezone

from apps.knowledge.models import (
    EmbeddingVersion,
    KnowledgeEntityType,
    KnowledgeEventType,
    KnowledgeItem,
    KnowledgeRetrieval,
    KnowledgeVersion,
)
from apps.knowledge.services.chat import OrgChatService
from apps.knowledge.services.index import KnowledgeIndexService
from apps.knowledge.services.temporal import (
    decision_evolution,
    entity_history,
    knowledge_events,
    time_travel_stats,
    topic_timeline,
)
from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision

pytestmark = pytest.mark.django_db


def _meeting(owner, *, title="Sync", seg_text="We will use Postgres for the database."):
    m = Meeting.objects.create(owner=owner, title=title, description="d")
    TranscriptSegment.objects.create(meeting=m, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Alice", text=seg_text)
    KnowledgeIndexService().index_meeting(m)
    return m


def _seg(meeting):
    return meeting.segments.get(index=0)


def test_first_index_creates_v1_and_events(user):
    m = _meeting(user)
    seg = _seg(m)
    item = KnowledgeItem.objects.get(entity_type=KnowledgeEntityType.SEGMENT, entity_id=seg.id)
    assert item.version == 1
    assert item.is_current is True
    assert item.valid_to is None
    assert item.knowledge_version >= 1
    assert item.embedding_version_id is not None
    # One CREATED event for the segment.
    assert item.events.filter(event_type=KnowledgeEventType.CREATED).exists()
    assert KnowledgeVersion.objects.filter(owner=user).count() >= 1


def test_reindex_unchanged_is_idempotent(user):
    m = _meeting(user)
    versions_before = KnowledgeVersion.objects.filter(owner=user).count()
    changed = KnowledgeIndexService().index_meeting(m)
    assert changed == 0
    # No new version, no duplicate items.
    assert KnowledgeVersion.objects.filter(owner=user).count() == versions_before
    seg = _seg(m)
    assert KnowledgeItem.objects.filter(entity_type="segment", entity_id=seg.id).count() == 1


def test_change_supersedes_and_appends_new_version(user):
    m = _meeting(user, seg_text="We will use Postgres.")
    seg = _seg(m)
    seg.text = "We will use MySQL instead."
    seg.save(update_fields=["text"])

    KnowledgeIndexService().index_meeting(m)

    rows = list(KnowledgeItem.objects.filter(entity_type="segment", entity_id=seg.id).order_by("version"))
    assert len(rows) == 2
    old, new = rows
    assert old.version == 1 and old.is_current is False and old.valid_to is not None
    assert new.version == 2 and new.is_current is True and new.valid_to is None
    assert new.supersedes_version == 1
    assert "MySQL" in new.text
    # Exactly one current row (partial-unique holds).
    assert KnowledgeItem.objects.current().filter(entity_type="segment", entity_id=seg.id).count() == 1
    # Event stream records SUPERSEDED + UPDATED.
    kinds = set(new.events.values_list("event_type", flat=True)) | set(old.events.values_list("event_type", flat=True))
    assert KnowledgeEventType.SUPERSEDED in kinds
    assert KnowledgeEventType.UPDATED in kinds


def test_deleted_entity_is_archived(user):
    m = _meeting(user)
    seg = _seg(m)
    seg_id = seg.id
    seg.delete(hard=True)  # entity vanishes from source (Django nulls seg.id after delete)
    KnowledgeIndexService().index_meeting(m)
    item = KnowledgeItem.objects.get(entity_type="segment", entity_id=seg_id)
    assert item.is_current is False
    assert item.events.filter(event_type=KnowledgeEventType.ARCHIVED).exists()


def test_time_travel_returns_historical_knowledge(user):
    import time

    m = _meeting(user, seg_text="Decision: use Postgres.")
    seg = _seg(m)
    time.sleep(0.02)          # guarantee t_mid strictly separates the two indexes
    t_mid = timezone.now()
    time.sleep(0.02)

    seg.text = "Decision: switch to MySQL."
    seg.save(update_fields=["text"])
    KnowledgeIndexService().index_meeting(m)

    # As of t_mid we only knew about Postgres.
    historical = KnowledgeItem.objects.as_of(t_mid).filter(owner=user, entity_type="segment", entity_id=seg.id)
    assert historical.count() == 1
    assert "Postgres" in historical.first().text
    # Current knowledge is MySQL.
    assert "MySQL" in KnowledgeItem.objects.current().get(entity_type="segment", entity_id=seg.id).text

    stats_now = KnowledgeIndexService().stats(user)
    stats_then = time_travel_stats(user, t_mid)
    assert stats_then["knowledge_version"] < stats_now["knowledge_version"]


def test_topic_timeline_tracks_evolution(user):
    m = _meeting(user, seg_text="The authentication approach is JWT.")
    seg = _seg(m)
    seg.text = "The authentication approach moved to OAuth2."
    seg.save(update_fields=["text"])
    KnowledgeIndexService().index_meeting(m)

    tl = topic_timeline(user, "authentication")
    assert tl["total_mentions"] >= 2          # both versions counted
    assert tl["periods"]                       # at least one time bucket
    assert tl["milestones"]                    # discrete change events


def test_decision_evolution_and_entity_history(user):
    m = Meeting.objects.create(owner=user, title="Arch", description="d")
    d = Decision.objects.create(owner=user, meeting=m, decision="Use JWT for auth")
    KnowledgeIndexService().index_meeting(m)

    hist = entity_history(user, KnowledgeEntityType.DECISION, d.id)
    assert hist["current_version"] == 1
    assert len(hist["versions"]) == 1
    assert hist["events"]

    evo = decision_evolution(user, d)
    assert evo["decision"]["id"] == str(d.id)
    assert evo["versions"]


def test_embedding_version_recorded(user):
    _meeting(user)
    evs = EmbeddingVersion.objects.all()
    assert evs.exists()
    assert evs.first().dimensions > 0


def test_knowledge_events_feed(user):
    _meeting(user)
    events = knowledge_events(user, event_type=KnowledgeEventType.CREATED)
    assert events and all(e["event"] == "created" for e in events)


def test_chat_records_retrieval_provenance(user):
    _meeting(user, seg_text="We agreed to launch the new billing system in Q3.")
    out = OrgChatService().ask(user, "When are we launching billing?")
    assert out["found"] is True
    prov = KnowledgeRetrieval.objects.filter(owner=user, kind="org_chat").order_by("-created_at").first()
    assert prov is not None
    assert prov.knowledge_version >= 1
    assert prov.retrieved_items
    assert prov.embedding_version_id is not None
    assert prov.response_time_ms is not None


# ---- API smoke for the new temporal endpoints ----

def test_api_temporal_endpoints(auth_client, user):
    m = _meeting(user, seg_text="We will migrate to a microservices architecture.")
    d = Decision.objects.create(owner=user, meeting=m, decision="Adopt microservices")
    KnowledgeIndexService().index_meeting(m)
    seg = _seg(m)
    today = timezone.now().date().isoformat()   # date-only avoids '+' offset in URL

    assert auth_client.get("/api/knowledge/versions/").status_code == 200
    assert auth_client.get(f"/api/knowledge/timetravel/?as_of={today}").status_code == 200
    assert auth_client.get("/api/knowledge/timeline/?topic=microservices").status_code == 200
    assert auth_client.get("/api/knowledge/events/").status_code == 200
    assert auth_client.get(f"/api/knowledge/history/segment/{seg.id}/").status_code == 200
    assert auth_client.get(f"/api/knowledge/decision/{d.id}/evolution/").status_code == 200

    # Missing as_of -> 400; missing topic -> 400.
    assert auth_client.get("/api/knowledge/timetravel/").status_code == 400
    assert auth_client.get("/api/knowledge/timeline/").status_code == 400
