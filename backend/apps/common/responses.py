"""Helpers for producing the standard success envelope.

Success responses use::

    {"success": true, "message": "...", "data": { ... }}
"""
from __future__ import annotations

from typing import Any, Optional

from rest_framework import status as http_status
from rest_framework.response import Response


def success_response(
    data: Any = None,
    message: str = "",
    status: int = http_status.HTTP_200_OK,
) -> Response:
    payload: dict[str, Any] = {"success": True}
    if message:
        payload["message"] = message
    payload["data"] = data
    return Response(payload, status=status)


def error_response(
    message: str,
    code: str = "error",
    details: Optional[Any] = None,
    status: int = http_status.HTTP_400_BAD_REQUEST,
) -> Response:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return Response({"success": False, "error": error}, status=status)
