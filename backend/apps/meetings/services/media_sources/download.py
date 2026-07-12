"""Shared stdlib streaming downloader with resume + size cap + progress.

Used by providers that fetch a direct media URL (podcast enclosures, etc.). Keeps
the download logic in one place so every provider enforces the same limits.
"""
from __future__ import annotations

import os
from urllib.request import Request, urlopen

from .base import MediaProviderError, ProgressCallback

_UA = "MeetingMind-MediaImport/1.0"
_CHUNK = 256 * 1024


def stream_download(
    url: str,
    dest: str,
    *,
    cap_bytes: int,
    timeout: int,
    progress_cb: ProgressCallback | None = None,
    resume: bool = True,
) -> int:
    """Download ``url`` to ``dest`` (resuming a partial file). Returns bytes written."""
    existing = os.path.getsize(dest) if (resume and os.path.exists(dest)) else 0
    headers = {"User-Agent": _UA}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    try:
        resp = urlopen(Request(url, headers=headers), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise MediaProviderError(f"Could not download the file: {exc}", code="download_error") from exc

    resuming = bool(existing) and resp.status == 206
    total_hdr = resp.headers.get("Content-Length")
    remaining = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
    total = (existing + remaining) if (resuming and remaining is not None) else remaining
    done = existing if resuming else 0

    with resp, open(dest, "ab" if resuming else "wb") as fh:
        while True:
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if done > cap_bytes:
                fh.close()
                if os.path.exists(dest):
                    os.remove(dest)
                raise MediaProviderError(
                    f"Download exceeded the {cap_bytes // 1024 // 1024} MB limit.",
                    code="too_large", blocked=True,
                )
            if progress_cb:
                pct = (done / total * 100.0) if total else 0.0
                progress_cb(min(pct, 100.0), done, total)
    return done
