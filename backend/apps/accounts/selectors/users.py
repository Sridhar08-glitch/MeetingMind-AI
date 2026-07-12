"""Read-side query helpers for accounts (no writes, no side effects)."""
from __future__ import annotations

from typing import Optional

from apps.accounts.models import User


def get_active_user_by_email(email: str) -> Optional[User]:
    return User.objects.filter(email__iexact=email.strip(), is_active=True).first()


def email_exists(email: str) -> bool:
    return User.objects.filter(email__iexact=email.strip()).exists()
