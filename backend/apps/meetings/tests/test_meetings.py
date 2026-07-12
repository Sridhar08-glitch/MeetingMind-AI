"""Tests for owner-scoped meeting access and dashboard stats."""
import pytest

from apps.accounts.tests.factories import UserFactory
from apps.meetings.enums import ProcessingStatus
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_meeting():
    other = UserFactory()
    return Meeting.objects.create(owner=other, title="Someone else's meeting")


def test_list_returns_only_own_meetings(auth_client, user, other_meeting):
    Meeting.objects.create(owner=user, title="My meeting", processing_status=ProcessingStatus.COMPLETED)
    resp = auth_client.get("/api/meetings/")
    assert resp.status_code == 200
    titles = [m["title"] for m in resp.data["results"]]
    assert "My meeting" in titles
    assert "Someone else's meeting" not in titles


def test_cannot_retrieve_other_users_meeting(auth_client, other_meeting):
    resp = auth_client.get(f"/api/meetings/{other_meeting.id}/")
    assert resp.status_code in (403, 404)


def test_soft_delete_meeting(auth_client, user):
    meeting = Meeting.objects.create(owner=user, title="To delete")
    resp = auth_client.delete(f"/api/meetings/{meeting.id}/")
    assert resp.status_code == 200
    meeting.refresh_from_db()
    assert meeting.is_deleted is True
    assert not Meeting.objects.filter(id=meeting.id).exists()
    assert Meeting.all_objects.filter(id=meeting.id).exists()


def test_dashboard_stats(auth_client, user):
    Meeting.objects.create(owner=user, title="A", processing_status=ProcessingStatus.COMPLETED, duration_seconds=3600)
    Meeting.objects.create(owner=user, title="B", processing_status=ProcessingStatus.FAILED, duration_seconds=1800)
    resp = auth_client.get("/api/meetings/dashboard/stats/")
    assert resp.status_code == 200
    data = resp.data["data"]
    assert data["total_meetings"] == 2
    assert data["completed_meetings"] == 1
    assert data["failed_meetings"] == 1
    assert data["total_hours_processed"] == pytest.approx(1.5)
