"""Structured health-check endpoints.

`/health` returns an overall roll-up plus per-component detail; each component
also has its own endpoint. In eager mode (no Redis/worker) those components
report ``degraded`` rather than failing the whole app — the API is still fully
functional. Only a database outage yields a 503.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"


def _check_database() -> dict:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": _OK}
    except Exception as exc:  # noqa: BLE001
        return {"status": _DOWN, "error": str(exc)}


def _check_redis() -> dict:
    try:
        import redis  # redis-py is a dependency even when the server isn't running

        client = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=0.5)
        client.ping()
        return {"status": _OK, "broker": settings.CELERY_BROKER_URL}
    except Exception as exc:  # noqa: BLE001
        # Expected in local/eager mode — not fatal.
        return {"status": _DEGRADED, "note": "Redis not reachable (eager mode).", "error": str(exc)}


def _check_storage() -> dict:
    try:
        from apps.common.storage import get_storage_service
        from django.core.files.base import ContentFile

        storage = get_storage_service()
        key = storage.save("private/health", f"{uuid.uuid4().hex}.txt", ContentFile(b"ok"))
        exists = storage.exists(key)
        storage.delete(key)
        return {"status": _OK if exists else _DEGRADED, "backend": settings.STORAGE_BACKEND}
    except Exception as exc:  # noqa: BLE001
        return {"status": _DOWN, "error": str(exc)}


def _check_workers() -> dict:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return {"status": _OK, "mode": "eager", "note": "Tasks run in-process."}
    try:
        from config.celery import app

        replies = app.control.inspect(timeout=0.5).ping() or {}
        if replies:
            return {"status": _OK, "mode": "worker", "workers": list(replies.keys())}
        return {"status": _DEGRADED, "mode": "worker", "note": "No workers responded."}
    except Exception as exc:  # noqa: BLE001
        return {"status": _DEGRADED, "error": str(exc)}


def _roll_up(components: dict) -> tuple[str, int]:
    statuses = {c["status"] for c in components.values()}
    if _DOWN in statuses:
        return _DOWN, 503
    if _DEGRADED in statuses:
        return _DEGRADED, 200
    return _OK, 200


def health(_request) -> JsonResponse:
    components = {
        "database": _check_database(),
        "redis": _check_redis(),
        "storage": _check_storage(),
        "workers": _check_workers(),
    }
    status, code = _roll_up(components)
    return JsonResponse(
        {"status": status, "service": "meetingmind-api", "components": components}, status=code
    )


def health_database(_request) -> JsonResponse:
    c = _check_database()
    return JsonResponse(c, status=503 if c["status"] == _DOWN else 200)


def health_redis(_request) -> JsonResponse:
    return JsonResponse(_check_redis())


def health_storage(_request) -> JsonResponse:
    c = _check_storage()
    return JsonResponse(c, status=503 if c["status"] == _DOWN else 200)


def health_workers(_request) -> JsonResponse:
    return JsonResponse(_check_workers())
