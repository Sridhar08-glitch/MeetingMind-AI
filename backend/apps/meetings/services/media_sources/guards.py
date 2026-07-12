"""URL safety guards for server-side media fetching.

User-supplied URLs are fetched by the backend, so they must be constrained:
- scheme allow-list (http/https only — no file://, ftp://, etc.);
- reject hosts that resolve to private / loopback / link-local / reserved IPs
  (blocks SSRF against internal services and cloud metadata endpoints);
- optional host allow-list (``MEDIA_IMPORT_ALLOWED_HOSTS``; empty = any public host).

These guards protect the SERVER. They are separate from the content-permission
check (private/DRM/age-gated), which each provider enforces via its extractor.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings

from .base import MediaProviderError

_ALLOWED_SCHEMES = ("http", "https")


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _host_allowed(host: str) -> bool:
    allow = [h.strip().lower() for h in getattr(settings, "MEDIA_IMPORT_ALLOWED_HOSTS", []) if h.strip()]
    if not allow:
        return True  # no allow-list configured → any public host is permitted
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in allow)


def assert_public_url(url: str) -> None:
    """Raise MediaProviderError(blocked=True) unless ``url`` is a safe public URL.

    Resolves the hostname and requires that EVERY resolved address is public, so a
    name that maps to a private/loopback/metadata IP is refused (SSRF defense).
    """
    if not getattr(settings, "MEDIA_IMPORT_ENABLED", True):
        raise MediaProviderError("Media import is disabled.", code="import_disabled", blocked=True)

    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise MediaProviderError(
            "Only http(s) URLs can be imported.", code="bad_scheme", blocked=True
        )
    host = parsed.hostname
    if not host:
        raise MediaProviderError("The URL has no host.", code="bad_url", blocked=True)
    if not _host_allowed(host):
        raise MediaProviderError(
            f"Host '{host}' is not in the import allow-list.", code="host_not_allowed", blocked=True
        )

    # A bare IP literal: check it directly. A name: resolve and check every A/AAAA.
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise MediaProviderError(f"Could not resolve host '{host}'.", code="dns_error", blocked=True) from exc

    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise MediaProviderError(f"Could not resolve host '{host}'.", code="dns_error", blocked=True)
    for ip in resolved:
        if not _is_public_ip(ip):
            raise MediaProviderError(
                f"Host '{host}' resolves to a non-public address and cannot be imported.",
                code="private_address", blocked=True,
            )
