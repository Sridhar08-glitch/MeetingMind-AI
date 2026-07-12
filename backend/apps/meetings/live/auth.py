"""JWT authentication for the live WebSocket (token passed as ?token=<access>)."""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_token(token: str):
    from rest_framework_simplejwt.tokens import AccessToken

    from apps.accounts.models import User

    try:
        access = AccessToken(token)
        return User.objects.get(id=access["user_id"], is_active=True)
    except Exception:  # noqa: BLE001 — any failure → anonymous
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        qs = parse_qs((scope.get("query_string") or b"").decode())
        token = (qs.get("token") or [""])[0]
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
