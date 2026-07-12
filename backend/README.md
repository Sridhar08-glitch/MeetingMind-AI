<div align="center">

# ⚙️ MeetingMind AI — Backend

**Django 5.1 · Django REST Framework · PostgreSQL · Celery · 100% Local AI**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15-A30000?style=flat-square&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Pytest](https://img.shields.io/badge/Tested-Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)

</div>

The MeetingMind backend is a **clean, layered, event-sourced** Django application. It exposes a fully-documented REST API and runs all AI locally (Faster-Whisper, Ollama, SpeechBrain ECAPA). Every capability is **owner-scoped** — a user only ever accesses their own data.

> 📚 See the root [README](../README.md) for the product overview, and [`docs/`](docs/) for deep dives (architecture, database, security, deployment).

---

## 🧱 Architecture

Each app follows the same layered structure — a strict boundary from HTTP down to persistence:

```
api/          → HTTP boundary: DRF views, serializers, urls, JWT, owner-scoping
services/     → business logic: STT, LLM, RAG, materialization, diarization
selectors/    → read queries: owner-scoped, eager-loaded
models.py     → persistence: ORM, UUID PKs, soft-delete, audit, versioning
tasks/        → async entrypoints (Celery @shared_task)
pipeline.py   → self-registering pipeline stages
subscribers.py→ event-bus listeners (materialize domain state)
```

**Cross-cutting foundations**

- **Provider abstraction** — `LLMProvider` / `SpeechToTextProvider` / `EmbeddingProvider` / `DiarizationProvider` are chosen by settings, so the local-first mandate is pure configuration.
- **Generic job + pipeline engine** (`apps/jobs`) — self-registering stages, dependency-DAG ordering, retries, idempotent resume, cancellation, live event timeline.
- **In-process event bus** — job/stage lifecycle events; `meetings` / `workspace` / `knowledge` subscribe to materialize their own state (no cross-app coupling).
- **Bitemporal knowledge index** — append-only, event-sourced facts (valid-time + transaction-time).

---

## 📦 Apps

| App | Responsibility |
|-----|----------------|
| `common` | Base models (UUID / soft-delete / audit), storage abstraction, response envelopes, demo seeding |
| `accounts` | JWT authentication, users, password reset |
| `jobs` | Generic background-job + pipeline engine, Celery integration, health checks |
| `meetings` | Upload, STT, AI analysis, meeting chat (RAG), diarization, speakers, media import |
| `workspace` | Tasks, issues, decisions, risks, notes, reports, AI suggestions, **VoicePerson** identities |
| `knowledge` | Bitemporal Knowledge Hub, org search/chat, consensus, conflicts, Executive Intelligence |
| `agents` | Multi-agent framework, 12 declarative agents, Planner, Collaboration engine |
| `benchmarks` | Speaker-diarization evaluation & tuning framework |

---

## 🗂️ Structure

```
backend/
├── config/               # settings, urls, asgi, wsgi, celery app
├── apps/
│   ├── common/           # base models, storage, responses, demo
│   ├── accounts/         # auth
│   ├── jobs/             # job + pipeline engine
│   ├── meetings/         # STT, AI, chat, diarization, ingest/
│   ├── workspace/        # tasks, decisions, voice identities
│   ├── knowledge/        # knowledge hub + executive
│   ├── agents/           # agents, planner, collaboration
│   └── benchmarks/       # diarization benchmarking
├── docs/                 # architecture, database, security, deployment…
├── requirements.txt      # core dependencies
├── requirements-stt.txt  # Faster-Whisper (optional)
├── requirements-diarization.txt  # SpeechBrain ECAPA (optional)
├── conftest.py           # pytest fixtures (mock providers)
└── manage.py
```

---

## 🧠 AI Services (all local)

| Service | Module | Engine |
|---------|--------|--------|
| Speech-to-Text | `apps/meetings/services/stt/` | Faster-Whisper (Dummy fallback for tests) |
| LLM analysis + chat | `apps/meetings/services/llm/` | Ollama `llama3.2:3b` |
| Embeddings (RAG) | `apps/meetings/services/embeddings.py` | Ollama `nomic-embed-text` |
| Diarization | `apps/meetings/services/diarization/` | SpeechBrain ECAPA (optional pyannote) |
| Media inspection | `apps/meetings/services/media.py` | FFmpeg / ffprobe |

All providers degrade gracefully: if a local engine is unavailable, tests use deterministic dummy providers and the pipeline never hard-fails on transient AI errors.

---

## 🔄 Background Processing

- **Celery** (`config/celery.py`) with queues: `default, media, ai, exports, notifications, maintenance`.
- **Redis** as broker (via Memurai on Windows). Set `CELERY_TASK_ALWAYS_EAGER=True` to run inline without Redis.
- The meeting pipeline (`apps/meetings/pipeline.py`) chains: validate → extract → normalize → STT → diarization → store → AI analysis → knowledge index.

```bash
# Run a worker (Windows requires --pool=solo)
python -m celery -A config worker --pool=solo --queues=default,media,ai
```

---

## 🔌 API

```
http://localhost:8000/api/docs/     # Swagger UI (drf-spectacular)
http://localhost:8000/api/schema/   # OpenAPI 3 schema
http://localhost:8000/admin/        # Django admin
```

Responses use a standard envelope (`{ "success": true, "data": … }`) via `apps/common/responses.py`, with a centralized exception handler.

---

## ✅ Testing

```bash
# Run the full suite (mock AI providers, eager Celery — no external services needed)
CELERY_TASK_ALWAYS_EAGER=True python -m pytest apps -q
```

Tests force deterministic dummy providers via `conftest.py`, so they never load models, hit Ollama, or need Redis.

---

## 🔧 Environment

Copy the template and set **your own** values (never commit real secrets — `.env` is git-ignored):

```bash
cp .env.example .env
```

Key variables: `DJANGO_SECRET_KEY`, `DB_*` (PostgreSQL), `AI_PROVIDER`, `STT_PROVIDER`, `EMBEDDING_PROVIDER`, `OLLAMA_BASE_URL`, `FFMPEG_BINARY`, `CELERY_TASK_ALWAYS_EAGER`, `REDIS_URL`. Full reference in [`docs/LOCAL_DEVELOPMENT.md`](docs/LOCAL_DEVELOPMENT.md).

---

## 🚀 Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) and [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) for Gunicorn/Uvicorn, static collection, worker setup, and hardening checklists.
