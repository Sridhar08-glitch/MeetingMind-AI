"""Reproducibility provenance for benchmark runs (req 7).

Captures the moving parts that affect a diarization score so a run can be
reproduced and regressions attributed: the benchmark engine version, the active
providers/models, the git commit (best-effort — "" when not a git repo), and the
owner's current knowledge version at run time.
"""
from __future__ import annotations

import subprocess

from django.conf import settings

# Bump when the scoring/metric semantics change, so historical runs stay comparable.
ENGINE_VERSION = "1.0"

_GIT_COMMIT_CACHE: str | None = None


def git_commit() -> str:
    """Short git commit of the working tree, or "" if unavailable (req 7 "if any")."""
    global _GIT_COMMIT_CACHE
    if _GIT_COMMIT_CACHE is not None:
        return _GIT_COMMIT_CACHE
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(settings.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        _GIT_COMMIT_CACHE = out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — git may be absent; provenance is best-effort
        _GIT_COMMIT_CACHE = ""
    return _GIT_COMMIT_CACHE


def diarization_engine() -> str:
    provider = getattr(settings, "DIARIZATION_PROVIDER", "embedding")
    if provider == "pyannote":
        return f"pyannote:{getattr(settings, 'DIARIZATION_PYANNOTE_MODEL', '')}"
    if provider in {"dummy", "mock"}:
        return "dummy"
    return f"embedding:{getattr(settings, 'DIARIZATION_EMBEDDING_MODEL', '')}"


def stt_provider() -> str:
    provider = getattr(settings, "STT_PROVIDER", "faster_whisper")
    if provider == "faster_whisper":
        return f"faster_whisper:{getattr(settings, 'WHISPER_MODEL_SIZE', 'base')}"
    return provider


def embedding_model() -> str:
    return getattr(settings, "DIARIZATION_EMBEDDING_MODEL", "speechbrain/spkrec-ecapa-voxceleb")


def knowledge_version(owner) -> int | None:
    """The owner's current knowledge version (append-only, Phase 11A), or None."""
    try:
        from apps.knowledge.models import KnowledgeVersion

        row = KnowledgeVersion.objects.filter(owner=owner).order_by("-version").first()
        return row.version if row else None
    except Exception:  # noqa: BLE001 — knowledge layer optional for a benchmark
        return None


def provenance(owner) -> dict:
    """Full provenance snapshot for a BenchmarkRun."""
    return {
        "engine_version": ENGINE_VERSION,
        "diarization_engine": diarization_engine(),
        "stt_provider": stt_provider(),
        "embedding_model": embedding_model(),
        "git_commit": git_commit(),
        "knowledge_version": knowledge_version(owner),
    }
