# MeetingMind AI — Deployment Guide

Deploying MeetingMind AI beyond the local dev machine. MeetingMind is local-first — it can run
entirely on a single self-hosted box — but the same steps apply to any private server. For the
operational go-live audit see [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

> MeetingMind v1.0 ships as a self-hosted application. It has been built and verified against the
> **local** stack; the items below are the standard steps to run it on a persistent server.

---

## 1. Production checklist (at a glance)

- [ ] `DJANGO_DEBUG=False`, real `DJANGO_SECRET_KEY`, tightened `DJANGO_ALLOWED_HOSTS`
- [ ] PostgreSQL provisioned, migrated, and backed up
- [ ] Redis running (with `requirepass`, localhost/private bind)
- [ ] Celery worker(s) running as a managed service
- [ ] Ollama running with models pulled; FFmpeg installed
- [ ] Faster-Whisper extras installed; `STT_PROVIDER=faster_whisper`
- [ ] Reverse proxy terminating **HTTPS** in front of the API and frontend
- [ ] Static files collected; media on persistent storage
- [ ] CORS/CSRF origins set to the real frontend domain
- [ ] Health checks wired to your monitor
- [ ] Backup + restore tested

## 2. Environment variables

Set these on the server (never commit secrets). Full reference in
[ADMIN_GUIDE](../../docs/ADMIN_GUIDE.md); production-critical ones:

```dotenv
DJANGO_SECRET_KEY=<a real, random secret>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=meetingmind.example.com
CORS_ALLOWED_ORIGINS=https://meetingmind.example.com
CSRF_TRUSTED_ORIGINS=https://meetingmind.example.com

DB_ENGINE=postgres
DB_NAME=meetingmind
DB_USER=meetingmind
DB_PASSWORD=<db password>
DB_HOST=<db host>
DB_PORT=5432

CELERY_BROKER_URL=redis://:<redis password>@127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://:<redis password>@127.0.0.1:6379/1
CELERY_TASK_ALWAYS_EAGER=False

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
STT_PROVIDER=faster_whisper
WHISPER_MODEL_SIZE=base

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend   # + SMTP settings
FRONTEND_BASE_URL=https://meetingmind.example.com
```

## 3. Database

```bash
# provision an empty PostgreSQL database + user, then:
cd backend
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py createsuperuser   # email is the username field
```
Migrations are forward-only Django migrations per app; run `migrate` on every deploy (see §11).

## 4. Redis

Run Redis (or Memurai on Windows) with authentication and a private bind:
```conf
# redis.conf
bind 127.0.0.1
requirepass <redis password>
```
Point `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` at it. See
[REDIS_SETUP.md](REDIS_SETUP.md).

## 5. Celery worker

Run the worker as a managed/supervised service (systemd, NSSM on Windows, etc.):
```bash
cd backend
venv/Scripts/celery -A config worker -l info      # add --pool=solo on Windows
```
Scale by running additional workers, optionally pinned to queues:
```bash
celery -A config worker -Q media,ai -l info       # dedicate a worker to heavy AI/media work
```
See [CELERY_SETUP.md](CELERY_SETUP.md).

## 6. Ollama & FFmpeg

```bash
ollama serve
ollama pull llama3.2:3b
ollama pull nomic-embed-text
# ensure ffmpeg/ffprobe are installed and on PATH, or set FFMPEG_BINARY/FFPROBE_BINARY
```
See [OLLAMA_ACTIVATION.md](OLLAMA_ACTIVATION.md), [FFMPEG_SETUP.md](FFMPEG_SETUP.md),
[STT_ACTIVATION.md](STT_ACTIVATION.md).

## 7. Application server

Serve Django via a WSGI/ASGI server (e.g. gunicorn/uvicorn) behind the reverse proxy rather than
`runserver`:
```bash
cd backend
venv/Scripts/python.exe -m gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```
Build and serve the frontend:
```bash
cd frontend
npm ci && npm run build
npx next start -p 3000
```

## 8. Reverse proxy & HTTPS

Put a reverse proxy (nginx/Caddy/Traefik) in front:
- Terminate **HTTPS** (valid certificate); redirect HTTP→HTTPS.
- Route `/api/` → Django (`127.0.0.1:8000`), everything else → Next.js (`127.0.0.1:3000`).
- Set forwarded headers; raise `client_max_body_size` to at least `MAX_UPLOAD_SIZE_MB` (500 MB
  default) for uploads.

## 9. Static files

```bash
cd backend
venv/Scripts/python.exe manage.py collectstatic --noinput
```
Serve the collected static dir via the proxy (or WhiteNoise). The SPA's own assets are served by
Next.js.

## 10. Media

- User media lives under `MEDIA_ROOT` (`.../media`, private files under `.../media/private`).
- Put `MEDIA_ROOT` on **persistent** storage; it is **not** served by the web root — downloads go
  through the owner-checked API endpoint.
- The `STORAGE_BACKEND` setting is the seam for a future object-store backend; `local` is the
  shipped implementation.

## 11. Database migration strategy

- Migrations are per-app and forward-only. Deploy order: **back up DB → `migrate` → restart app +
  workers**.
- For zero-downtime, apply additive migrations before deploying code that depends on them.
- Never edit an applied migration; add a new one.

## 12. Backup & recovery

- **Back up together:** PostgreSQL dump **and** `MEDIA_ROOT`. They must be restored as a pair —
  the DB references media by storage key.
- **Backup:**
  ```bash
  pg_dump meetingmind > meetingmind_$(date +%F).sql
  tar czf media_$(date +%F).tgz -C backend media
  ```
- **Restore:** provision an empty DB, `psql < dump.sql`, restore `media/`, run `migrate` (no-op if
  the dump is current), restart services, hit `/api/health/`.
- Test restores regularly. Full DR procedure in
  [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

## 13. Post-deploy verification

```bash
curl -fsS https://meetingmind.example.com/api/health/            # aggregate
curl -fsS https://meetingmind.example.com/api/health/workers/    # expect {"mode":"worker",…}
```
Then run the real smoke test from [TESTING.md](TESTING.md) §6.

---

See also: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) · [SECURITY.md](SECURITY.md) ·
[ADMIN_GUIDE](../../docs/ADMIN_GUIDE.md).
