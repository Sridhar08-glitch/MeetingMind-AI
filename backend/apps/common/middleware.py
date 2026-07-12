"""Thread-local access to the current request user.

This lets base model `save()` populate `created_by` / `updated_by` audit fields
without threading the user through every service call. It is a deliberate,
narrow use of thread-locals scoped to the request lifecycle.
"""
from __future__ import annotations

import threading
from typing import Optional

from django.contrib.auth.models import AbstractBaseUser

_state = threading.local()


def get_current_user() -> Optional[AbstractBaseUser]:
    """Return the user bound to the active request, or ``None``."""
    user = getattr(_state, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def set_current_user(user: Optional[AbstractBaseUser]) -> None:
    _state.user = user


class RequestUserMiddleware:
    """Bind the authenticated user to a thread-local for the request duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)
