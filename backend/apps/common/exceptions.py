"""Centralized error handling producing a standard API error envelope.

Every error response has the shape::

    {
        "success": false,
        "error": {
            "code": "validation_error",
            "message": "Human readable summary.",
            "details": { ... optional field errors ... }
        }
    }
"""
from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("meetingmind")


class ApplicationError(exceptions.APIException):
    """Base class for expected, domain-level errors raised by services."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "An application error occurred."
    default_code = "application_error"


def _code_for(exc: Exception) -> str:
    if isinstance(exc, exceptions.APIException):
        # Prefer the concrete code attached to the raised detail (e.g. the
        # `code=` passed to ApplicationError); fall back to the class default.
        codes = exc.get_codes()
        if isinstance(codes, str):
            return codes
        return str(getattr(exc, "default_code", "error"))
    if isinstance(exc, Http404):
        return "not_found"
    if isinstance(exc, (DjangoPermissionDenied,)):
        return "permission_denied"
    return "server_error"


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Translate any raised exception into the standard error envelope."""
    # Normalize Django-native exceptions DRF doesn't handle by default.
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=getattr(exc, "message_dict", exc.messages))
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, IntegrityError):
        exc = exceptions.ValidationError(detail="A database integrity error occurred.")

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception — log with traceback and return a safe 500.
        logger.exception("Unhandled server error: %s", exc)
        return Response(
            {
                "success": False,
                "error": {
                    "code": "server_error",
                    "message": "An unexpected server error occurred.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    message: str
    details: Any = None

    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
    elif isinstance(detail, dict):
        message = "Validation failed."
        details = detail
    elif isinstance(detail, list):
        message = "; ".join(str(item) for item in detail)
    else:
        message = str(detail)

    envelope: dict[str, Any] = {
        "success": False,
        "error": {"code": _code_for(exc), "message": message},
    }
    if details is not None:
        envelope["error"]["details"] = details

    response.data = envelope
    return response
