"""Tests for the jobs API, metrics, health checks, and permissions."""
import pytest

from apps.accounts.tests.factories import UserFactory
from apps.jobs.enums import JobStatus, JobType
from apps.jobs.manager import job_manager
from apps.jobs.services import execute_job

from . import stages as S  # noqa: F401 — registers test stages/pipelines

pytestmark = pytest.mark.django_db


def _make_job(owner, pipeline="t_linear", **kw):
    return job_manager.enqueue(
        JobType.MEETING_PROCESSING, pipeline=pipeline, actor=owner, dispatch=False, **kw
    )


@pytest.fixture
def staff_client(api_client):
    staff = UserFactory(is_staff=True)
    staff.set_password("SuperSecret123")
    staff.save()
    resp = api_client.post(
        "/api/auth/login/", {"email": staff.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    return api_client, staff


# --- listing & permissions --------------------------------------------------
def test_list_returns_only_own_jobs(auth_client, user):
    _make_job(user)
    other = UserFactory()
    _make_job(other)
    resp = auth_client.get("/api/jobs/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_cannot_retrieve_another_users_job(auth_client):
    other = UserFactory()
    job = _make_job(other)
    resp = auth_client.get(f"/api/jobs/{job.id}/")
    assert resp.status_code == 404


def test_staff_sees_all_jobs(staff_client, user):
    client, _ = staff_client
    _make_job(user)
    resp = client.get("/api/jobs/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1


def test_requires_authentication(api_client):
    assert api_client.get("/api/jobs/").status_code == 401


# --- detail, logs, timeline -------------------------------------------------
def test_detail_and_logs_after_run(auth_client, user):
    job = _make_job(user)
    execute_job(str(job.id))
    detail = auth_client.get(f"/api/jobs/{job.id}/")
    assert detail.status_code == 200
    assert detail.data["status"] == JobStatus.SUCCEEDED
    assert detail.data["progress"] == 100
    assert len(detail.data["logs"]) >= 3

    logs = auth_client.get(f"/api/jobs/{job.id}/logs/")
    assert logs.status_code == 200
    assert len(logs.data["data"]) >= 3

    timeline = auth_client.get(f"/api/jobs/{job.id}/timeline/")
    assert timeline.status_code == 200
    assert "logs" in timeline.data["data"]


# --- controls ---------------------------------------------------------------
def test_retry_only_allowed_on_failed(auth_client, user):
    job = _make_job(user, pipeline="t_fatal")
    execute_job(str(job.id))
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    resp = auth_client.post(f"/api/jobs/{job.id}/retry/")
    assert resp.status_code == 200
    assert resp.data["data"]["status"] == JobStatus.QUEUED


def test_retry_rejected_on_completed(auth_client, user):
    job = _make_job(user)
    execute_job(str(job.id))
    resp = auth_client.post(f"/api/jobs/{job.id}/retry/")
    assert resp.status_code == 409
    assert resp.data["error"]["code"] == "invalid_state"


def test_cancel_active_job(auth_client, user):
    job = _make_job(user)  # queued
    resp = auth_client.post(f"/api/jobs/{job.id}/cancel/")
    assert resp.status_code == 200
    job.refresh_from_db()
    assert job.status == JobStatus.CANCELED


def test_cannot_control_another_users_job(auth_client):
    other = UserFactory()
    job = _make_job(other)
    assert auth_client.post(f"/api/jobs/{job.id}/cancel/").status_code == 404


# --- metrics ----------------------------------------------------------------
def test_metrics_endpoint(auth_client, user):
    done = _make_job(user)
    execute_job(str(done.id))
    _make_job(user, pipeline="t_fatal")  # queued, not run
    resp = auth_client.get("/api/jobs/metrics/")
    assert resp.status_code == 200
    data = resp.data["data"]
    assert data["total_jobs"] == 2
    assert data["completed_jobs"] == 1
    assert "success_rate" in data
    assert isinstance(data["pipelines"], list)


# --- filters ----------------------------------------------------------------
def test_filter_by_status(auth_client, user):
    done = _make_job(user)
    execute_job(str(done.id))
    _make_job(user)  # queued
    resp = auth_client.get("/api/jobs/?status=succeeded")
    assert resp.status_code == 200
    assert all(j["status"] == "succeeded" for j in resp.data["results"])


# --- health checks ----------------------------------------------------------
def test_health_endpoints(api_client):
    root = api_client.get("/api/health/")
    assert root.status_code == 200
    body = root.json()
    assert set(body["components"]) == {"database", "redis", "storage", "workers"}
    assert body["components"]["database"]["status"] == "ok"
    # Eager mode → workers component is ok in eager mode.
    assert body["components"]["workers"]["status"] == "ok"

    assert api_client.get("/api/health/database/").status_code == 200
    assert api_client.get("/api/health/storage/").status_code == 200
    assert api_client.get("/api/health/redis/").json()["status"] in {"ok", "degraded"}
