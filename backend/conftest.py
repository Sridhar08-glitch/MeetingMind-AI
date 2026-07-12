"""Shared pytest fixtures."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture(autouse=True)
def _no_throttle_cache(settings):
    """Use a no-op cache so rate throttling never accumulates across tests."""
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}
    }


@pytest.fixture(autouse=True)
def _dummy_ai_providers(settings):
    """Force deterministic dummy providers in tests.

    Production defaults to faster_whisper (STT) and ollama (LLM); tests must never
    load models, download weights, or hit a local Ollama server, so we pin the
    dummy providers for the whole suite.
    """
    settings.STT_PROVIDER = "mock"
    settings.AI_PROVIDER = "mock"
    settings.EMBEDDING_PROVIDER = "mock"
    settings.TRANSLATION_PROVIDER = "mock"
    # Never touch Redis for the channel layer in tests.
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@pytest.fixture(autouse=True)
def _isolate_media_root(settings, tmp_path):
    """Write uploaded files under a throwaway temp dir, not the repo's media/.

    Reset the storage handler so FileField saves pick up the new MEDIA_ROOT
    rather than the value cached when default_storage was first created.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.storage import storages

    storages._storages = {}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email="alice@example.com",
        password="SuperSecret123",
        first_name="Alice",
        last_name="Smith",
    )


@pytest.fixture
def auth_client(api_client: APIClient, user: User) -> APIClient:
    resp = api_client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "SuperSecret123"},
        format="json",
    )
    token = resp.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client
