"""API tests for the benchmarking suite — CRUD, owner-scoping, ground-truth honesty."""
from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.benchmarks.enums import BenchmarkDatasetKind, GroundTruthType
from apps.benchmarks.models import BenchmarkDataset

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_client(api_client):
    other = User.objects.create_user(email="bob@example.com", password="SuperSecret123")
    resp = api_client.post(
        "/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    return api_client


def _make_dataset(client, kind="user", name="My set"):
    return client.post(
        "/api/benchmarks/datasets/", {"kind": kind, "name": name}, format="json"
    )


def test_create_and_list_dataset(auth_client, user):
    resp = _make_dataset(auth_client, kind="public", name="Public panels")
    assert resp.status_code == 201
    assert resp.data["data"]["kind"] == "public"

    listing = auth_client.get("/api/benchmarks/datasets/")
    assert listing.status_code == 200
    assert len(listing.data["data"]) == 1
    assert listing.data["data"][0]["recording_count"] == 0


def test_public_recording_defaults_to_approximate_ground_truth(auth_client):
    ds = _make_dataset(auth_client, kind="public", name="CC videos").data["data"]
    resp = auth_client.post(
        "/api/benchmarks/recordings/",
        {"dataset": ds["id"], "name": "A panel", "format": "panel", "expected_speaker_count": 4},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["data"]["ground_truth_type"] == GroundTruthType.PUBLIC_APPROXIMATE
    # Approximate counts must not be flagged exact (req 8).
    assert resp.data["data"]["ground_truth_is_exact"] is False


def test_user_recording_defaults_to_verified_and_is_exact(auth_client):
    ds = _make_dataset(auth_client, kind="user", name="My meetings").data["data"]
    resp = auth_client.post(
        "/api/benchmarks/recordings/",
        {"dataset": ds["id"], "name": "Standup", "expected_speaker_count": 3,
         "known_participants": ["Alice", "Bob", "Carol"]},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["data"]["ground_truth_type"] == GroundTruthType.USER_VERIFIED
    assert resp.data["data"]["ground_truth_is_exact"] is True


def test_owner_scoping_hides_other_users_datasets(auth_client, other_client):
    # `other_client` has swapped the shared api_client credentials to Bob.
    BenchmarkDataset.objects.create(
        owner=User.objects.get(email="alice@example.com"), kind=BenchmarkDatasetKind.USER, name="Alice set"
    )
    listing = other_client.get("/api/benchmarks/datasets/")
    assert listing.status_code == 200
    assert listing.data["data"] == []


def test_cannot_attach_recording_to_foreign_dataset(auth_client, api_client):
    # Alice owns the dataset.
    ds = _make_dataset(auth_client, kind="user", name="Alice set").data["data"]
    # Bob tries to add a recording to it.
    bob = User.objects.create_user(email="bob@example.com", password="SuperSecret123")
    resp = api_client.post(
        "/api/auth/login/", {"email": bob.email, "password": "SuperSecret123"}, format="json"
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    attach = api_client.post(
        "/api/benchmarks/recordings/", {"dataset": ds["id"], "name": "sneaky"}, format="json"
    )
    assert attach.status_code == 403


def test_config_crud(auth_client):
    resp = auth_client.post(
        "/api/benchmarks/configs/",
        {"name": "loose", "cluster_threshold": 0.7, "max_speakers": 6},
        format="json",
    )
    assert resp.status_code == 201
    cid = resp.data["data"]["id"]
    patch = auth_client.patch(
        f"/api/benchmarks/configs/{cid}/", {"cluster_threshold": 0.4}, format="json"
    )
    assert patch.status_code == 200
    assert patch.data["data"]["cluster_threshold"] == 0.4


def test_runs_list_empty(auth_client):
    resp = auth_client.get("/api/benchmarks/runs/")
    assert resp.status_code == 200
    assert resp.data["data"] == []
