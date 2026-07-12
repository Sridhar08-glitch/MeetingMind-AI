"""End-to-end tests for the authentication flows (Phase 2)."""
import pytest
from django.core import mail

from apps.accounts.models import PasswordResetToken, User
from apps.accounts.services import auth as auth_service

pytestmark = pytest.mark.django_db


class TestRegistration:
    def test_register_creates_active_user(self, api_client):
        resp = api_client.post(
            "/api/auth/register/",
            {"email": "bob@example.com", "password": "SuperSecret123", "first_name": "Bob"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["success"] is True
        user = User.objects.get(email="bob@example.com")
        assert user.is_active
        assert user.check_password("SuperSecret123")

    def test_register_rejects_duplicate_email(self, api_client, user):
        resp = api_client.post(
            "/api/auth/register/",
            {"email": user.email, "password": "SuperSecret123"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"]["code"] == "email_taken"

    def test_register_rejects_weak_password(self, api_client):
        resp = api_client.post(
            "/api/auth/register/",
            {"email": "weak@example.com", "password": "123"},
            format="json",
        )
        assert resp.status_code == 400


class TestLogin:
    def test_login_returns_tokens_and_profile(self, api_client, user):
        resp = api_client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "SuperSecret123"},
            format="json",
        )
        assert resp.status_code == 200
        assert "access" in resp.data and "refresh" in resp.data
        assert resp.data["user"]["email"] == user.email

    def test_login_rejects_bad_password(self, api_client, user):
        resp = api_client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "wrong"},
            format="json",
        )
        assert resp.status_code == 401


class TestProfile:
    def test_profile_requires_auth(self, api_client):
        assert api_client.get("/api/auth/profile/").status_code == 401

    def test_get_and_update_profile(self, auth_client):
        assert auth_client.get("/api/auth/profile/").status_code == 200
        resp = auth_client.patch("/api/auth/profile/", {"first_name": "Alicia"}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["first_name"] == "Alicia"


class TestTokenLifecycle:
    def test_refresh_and_logout_blacklist(self, api_client, user):
        login = api_client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "SuperSecret123"},
            format="json",
        )
        refresh = login.data["refresh"]
        assert api_client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code == 200

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        assert api_client.post("/api/auth/logout/", {"refresh": refresh}, format="json").status_code == 200

        # A blacklisted refresh token can no longer be used.
        api_client.credentials()
        assert api_client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code == 401


class TestPasswordReset:
    def test_forgot_password_issues_token_and_email(self, api_client, user):
        resp = api_client.post("/api/auth/forgot-password/", {"email": user.email}, format="json")
        assert resp.status_code == 200
        assert PasswordResetToken.objects.filter(user=user, used_at__isnull=True).count() == 1
        assert len(mail.outbox) == 1
        assert "reset-password?token=" in mail.outbox[0].body

    def test_forgot_password_unknown_email_is_silent(self, api_client):
        resp = api_client.post("/api/auth/forgot-password/", {"email": "nobody@example.com"}, format="json")
        assert resp.status_code == 200
        assert len(mail.outbox) == 0

    def test_reset_password_with_valid_token(self, api_client, user):
        # Drive the service directly to capture the raw token.
        import hashlib
        import secrets

        raw = secrets.token_urlsafe(48)
        from django.utils import timezone

        PasswordResetToken.objects.create(
            user=user,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=timezone.now() + PasswordResetToken.DEFAULT_TTL,
        )
        resp = api_client.post(
            "/api/auth/reset-password/",
            {"token": raw, "new_password": "BrandNewPass456"},
            format="json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password("BrandNewPass456")

    def test_reset_password_rejects_invalid_token(self, api_client):
        resp = api_client.post(
            "/api/auth/reset-password/",
            {"token": "not-a-real-token", "new_password": "BrandNewPass456"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"]["code"] == "invalid_token"


class TestChangePassword:
    def test_change_password_success(self, auth_client, user):
        resp = auth_client.post(
            "/api/auth/change-password/",
            {"current_password": "SuperSecret123", "new_password": "AnotherPass789"},
            format="json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password("AnotherPass789")

    def test_change_password_wrong_current(self, auth_client):
        resp = auth_client.post(
            "/api/auth/change-password/",
            {"current_password": "wrong", "new_password": "AnotherPass789"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"]["code"] == "invalid_password"


class TestServiceLayer:
    def test_register_user_service(self):
        user = auth_service.register_user(email="svc@example.com", password="SuperSecret123")
        assert user.pk is not None
        assert User.objects.filter(email="svc@example.com").exists()
