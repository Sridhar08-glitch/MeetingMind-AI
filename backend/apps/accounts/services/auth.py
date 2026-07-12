"""Authentication business logic.

All account state changes live here (never in views). Views validate input and
delegate; services own the rules and side effects.
"""
from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PasswordResetToken, User
from apps.accounts.selectors.users import get_active_user_by_email
from apps.common.exceptions import ApplicationError

logger = logging.getLogger("meetingmind")
security_logger = logging.getLogger("meetingmind.security")


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@transaction.atomic
def register_user(*, email: str, password: str, first_name: str = "", last_name: str = "") -> User:
    """Create a new active user, enforcing password policy and unique email."""
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise ApplicationError("An account with this email already exists.", code="email_taken")

    user = User(email=email, first_name=first_name.strip(), last_name=last_name.strip())
    # Run Django's configured password validators against the candidate.
    validate_password(password, user)
    user.set_password(password)
    user.save()
    security_logger.info("User registered: %s", user.id)
    return user


@transaction.atomic
def request_password_reset(*, email: str) -> None:
    """Issue a reset token and email a link. Never reveals whether the email exists."""
    user = get_active_user_by_email(email)
    if user is None:
        # Deliberately silent: avoid user enumeration.
        security_logger.info("Password reset requested for unknown email.")
        return

    # Invalidate any outstanding tokens for this user.
    user.reset_tokens.filter(used_at__isnull=True).update(used_at=timezone.now())

    raw_token = secrets.token_urlsafe(48)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=_hash_token(raw_token),
        expires_at=timezone.now() + PasswordResetToken.DEFAULT_TTL,
    )

    reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={raw_token}"
    send_mail(
        subject="Reset your MeetingMind AI password",
        message=(
            "We received a request to reset your password.\n\n"
            f"Use the link below (valid for 1 hour):\n{reset_link}\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    security_logger.info("Password reset issued for user: %s", user.id)


@transaction.atomic
def reset_password(*, raw_token: str, new_password: str) -> None:
    """Consume a valid reset token and set a new password."""
    token = (
        PasswordResetToken.objects.select_for_update()
        .filter(token_hash=_hash_token(raw_token))
        .select_related("user")
        .first()
    )
    if token is None or not token.is_valid():
        raise ApplicationError("This reset link is invalid or has expired.", code="invalid_token")

    user = token.user
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    token.mark_used()
    security_logger.info("Password reset completed for user: %s", user.id)


@transaction.atomic
def change_password(*, user: User, current_password: str, new_password: str) -> None:
    """Change the password of an authenticated user after verifying the current one."""
    if not user.check_password(current_password):
        raise ApplicationError("Your current password is incorrect.", code="invalid_password")
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    security_logger.info("Password changed for user: %s", user.id)


@transaction.atomic
def update_profile(*, user: User, first_name: str | None = None, last_name: str | None = None) -> User:
    """Update mutable profile fields for the authenticated user."""
    fields: list[str] = []
    if first_name is not None:
        user.first_name = first_name.strip()
        fields.append("first_name")
    if last_name is not None:
        user.last_name = last_name.strip()
        fields.append("last_name")
    if fields:
        fields.append("updated_at")
        user.save(update_fields=fields)
    return user
