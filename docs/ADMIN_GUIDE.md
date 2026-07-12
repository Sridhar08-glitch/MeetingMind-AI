# MeetingMind AI — Administrator Guide

Operating MeetingMind AI: configuration, the local AI services, and day-to-day maintenance.
For go-live see [DEPLOYMENT.md](../backend/docs/DEPLOYMENT.md) and
[PRODUCTION_READINESS.md](../backend/docs/PRODUCTION_READINESS.md).

---

## 1. Runtime topology

A full local deployment is up to five processes:

| Process | Command | Needed for |
|---|---|---|
| **PostgreSQL** | (service) | Primary datastore |
| **Redis / Memurai** | `redis-server` / `memurai` | Celery broker + result backend (real async) |
| **Ollama** | `ollama serve` | LLM + embeddings |
| **Django API** | `venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload` | REST API |
| **Celery worker** | `venv/Scripts/celery -A config worker -l info --pool=solo` | Background processing |
| **Frontend** | `npm run dev` (or `build && next start`) | UI |

> On Windows the worker must use `--pool=solo`. If `CELERY_TASK_ALWAYS_EAGER=True`, tasks run
> inline in the API process and you do **not** need Redis or a worker (fine for dev/demo, not
> for production throughput).

## 2. Configuration

All configuration is environment-driven via `backend/.env` (read by `django-environ`). Start from
`backend/.env.example`.

### Core / security
| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | — | **Set a real secret in production.** |
| `DJANGO_DEBUG` | `False` | Keep `False` outside local dev. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. |
| `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | `http://localhost:3000` | Pin to your frontend origin. |

### Database
| Variable | Default |
|---|---|
| `DB_ENGINE` | `postgres` (or `sqlite`) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `meetingmind` / `postgres` / `postgres` |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `5432` |

### Auth (JWT)
| Variable | Default |
|---|---|
| `JWT_ACCESS_TOKEN_LIFETIME_MIN` | `30` |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` |

### AI providers
| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `ollama` | `ollama\|openai\|claude\|mock` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `llama3.2:3b` | |
| `AI_TEMPERATURE` / `AI_MAX_TOKENS` | `0.2` / `2000` | |
| `AI_CHUNK_SIZE` / `AI_CHUNK_OVERLAP` | `12000` / `800` | Map-reduce chunking |
| `AI_REQUEST_TIMEOUT` | `600` | Seconds |
| `AI_SUMMARY_STYLE` | `professional` | |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `ollama` / `nomic-embed-text` | |
| `CHAT_RETRIEVAL_K` / `CHAT_HISTORY_TURNS` | `6` / `4` | RAG retrieval size |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | `""` | Optional cloud; never required |

### Speech-to-Text
| Variable | Default | Notes |
|---|---|---|
| `STT_PROVIDER` | `faster_whisper` | Falls back to mock if library missing |
| `WHISPER_MODEL_SIZE` | `base` | `tiny\|base\|small\|medium\|large-v3` |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | |
| `WHISPER_BEAM_SIZE` | `5` | |
| `WHISPER_DOWNLOAD_ROOT` | `media/whisper-models` | Model cache |

### Media & storage
| Variable | Default |
|---|---|
| `FFMPEG_BINARY` / `FFPROBE_BINARY` | `ffmpeg` / `ffprobe` |
| `NORMALIZED_SAMPLE_RATE` | `16000` |
| `MAX_UPLOAD_SIZE_MB` / `MIN_UPLOAD_SIZE_BYTES` | `500` / `1024` |
| `MAX_AUDIO_DURATION_SECONDS` | `21600` (6 h) |
| `ALLOW_MKV_UPLOADS` | `True` |
| `STORAGE_BACKEND` | `local` |

### Async & workspace behaviour
| Variable | Default | Notes |
|---|---|---|
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` / `…/1` | |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | `True` = inline (no worker) |
| `CELERY_TASK_TIME_LIMIT` / `..._SOFT_TIME_LIMIT` | `3600` / `3300` | Per-task seconds |
| `AI_SUGGESTION_MODE` | `suggestions_only` | `suggestions_only\|auto_high\|always` |
| `AI_AUTO_APPROVE_THRESHOLD` | `95` | Confidence to auto-approve (if `auto_high`) |
| `EMAIL_BACKEND` | console | Swap for SMTP in prod |

## 3. The local AI services

### Ollama (LLM + embeddings)
```bash
ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```
Verify: `curl http://localhost:11434/api/tags`. See
[OLLAMA_ACTIVATION.md](../backend/docs/OLLAMA_ACTIVATION.md).

### Faster-Whisper (STT)
Install the optional extras and set the provider:
```bash
venv/Scripts/python.exe -m pip install -r requirements-stt.txt
# .env: STT_PROVIDER=faster_whisper
```
The first transcription downloads the model to `WHISPER_DOWNLOAD_ROOT`. See
[STT_ACTIVATION.md](../backend/docs/STT_ACTIVATION.md).

### FFmpeg
Required for real audio extraction/normalisation. Point `FFMPEG_BINARY`/`FFPROBE_BINARY` at the
binaries if they aren't on `PATH`. See [FFMPEG_SETUP.md](../backend/docs/FFMPEG_SETUP.md).

### Redis / Memurai + Celery
For real async, run Redis (or Memurai on Windows) and a worker. See
[REDIS_SETUP.md](../backend/docs/REDIS_SETUP.md) and
[CELERY_SETUP.md](../backend/docs/CELERY_SETUP.md).

## 4. Health & monitoring

Poll the health endpoints (no auth) for a liveness/readiness view:

| Endpoint | Reports |
|---|---|
| `GET /api/health/` | Aggregate + all components |
| `GET /api/health/database/` | DB connectivity (503 if down) |
| `GET /api/health/redis/` | Broker reachability |
| `GET /api/health/storage/` | Storage backend |
| `GET /api/health/workers/` | Worker mode (`worker`/`eager`) and count |

Operational insight also comes from:
- **Jobs dashboard** (`/api/jobs/metrics/`, `/api/jobs/{id}/timeline/`) — throughput, failures,
  per-stage timing.
- **Application logs** — Django uses split logging; the worker logs stage transitions. See
  [PRODUCTION_READINESS.md](../backend/docs/PRODUCTION_READINESS.md) for what to watch.

## 5. Maintenance

- **Database migrations:** `venv/Scripts/python.exe manage.py migrate` after any upgrade.
- **Temporary files:** audio extraction/normalisation writes temp WAVs; ensure the temp dir has
  space and is cleaned (see PRODUCTION_READINESS.md → temp/upload cleanup).
- **Uploads:** stored under `MEDIA_ROOT/private` with UUID names; files are versioned. Prune
  soft-deleted meetings per your retention policy (`all_objects` exposes soft-deleted rows).
- **Whisper models:** cached under `WHISPER_DOWNLOAD_ROOT`; safe to clear (re-downloaded on next
  run).
- **Backups:** back up PostgreSQL **and** `MEDIA_ROOT`. Restore both together. Details in
  [DEPLOYMENT.md](../backend/docs/DEPLOYMENT.md) and
  [PRODUCTION_READINESS.md](../backend/docs/PRODUCTION_READINESS.md).
- **Failed jobs:** retry/requeue via the Jobs API (`POST /api/jobs/{id}/retry|requeue/`);
  inspect `logs`/`timeline` first.

## 6. Creating an admin user

```bash
cd backend
venv/Scripts/python.exe manage.py createsuperuser
```
(The `User` model uses **email** as the username field.)

## 7. Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Worker crashes on start | Wrong Celery config | Ensure kombu `Queue` objects (already set); on Windows use `--pool=solo` |
| Transcription runs in "mock" | `STT_PROVIDER` fallback | Install `requirements-stt.txt`, set `STT_PROVIDER=faster_whisper`, install FFmpeg |
| AI returns generic/dummy text | `AI_PROVIDER=mock` or Ollama down | Set `AI_PROVIDER=ollama`, run `ollama serve`, pull models |
| Uploads rejected | Size/type/duration limits | Check the returned `validation_report`; adjust `MAX_UPLOAD_SIZE_MB` etc. |
| 401 loops in UI | Expired/blacklisted refresh | Re-login; check JWT lifetimes |

---

See also: [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) · [SECURITY.md](../backend/docs/SECURITY.md) ·
[PERFORMANCE.md](../backend/docs/PERFORMANCE.md).
