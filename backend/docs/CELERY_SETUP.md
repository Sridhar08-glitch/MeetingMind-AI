# Celery Setup — real async processing (local dev)

The background-processing platform (Phase 5) runs in **eager mode** by default
(tasks run in-process). To process jobs **asynchronously** through Redis + a real
worker is a **configuration change only** — no code changes.

Prerequisite: **Redis running** (see [REDIS_SETUP.md](REDIS_SETUP.md)).

## 1. Disable eager mode (`backend/.env`)

```dotenv
CELERY_TASK_ALWAYS_EAGER=False
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

## 2. Start a worker (Windows uses the `solo` pool)

From `backend/`, with the venv Python:

```bash
venv/Scripts/python.exe -m celery -A config worker \
  --loglevel=info --pool=solo \
  --queues=default,media,ai,exports,notifications,maintenance
```

On startup you should see: `Connected to redis://127.0.0.1:6379/0` and
`celery@<HOST> ready.`, with `jobs.run_pipeline_job` registered.

> **Windows:** always use `--pool=solo` (the default `prefork` pool doesn't work
> on Windows). It processes one task at a time — fine for local dev.

## 3. Verify

```bash
curl http://127.0.0.1:8000/api/health/workers/
# -> {"status":"ok","mode":"worker","workers":["celery@<HOST>"]}
```

Upload a meeting and watch the job go **queued → running → completed** (the web
returns immediately with `queued` — proof it's async, not eager). The worker log
prints `Task jobs.run_pipeline_job[...] received` then `... succeeded`.

## Tests stay eager

The test suite must not depend on a running worker. Run pytest with the env
override (no code change) so tasks execute in-process during tests:

```bash
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest apps
```

## Note

`config/settings.py` defines `CELERY_TASK_QUEUES` as `kombu.Queue` objects (real
workers require Queue instances, not plain dicts). Queues, routing, priorities,
`acks_late`, prefetch and time limits are all preconfigured.

## Troubleshooting

- **Worker exits with `'dict' object has no attribute 'name'`:** `task_queues`
  must be `kombu.Queue(...)` objects (already fixed in settings).
- **Jobs stay `queued`:** no worker running, or it isn't consuming the task's
  queue — start the worker with all `--queues` above.
- **`health/workers` shows `mode: eager`:** `.env` still has
  `CELERY_TASK_ALWAYS_EAGER=True`, or the web process wasn't restarted after the
  change.
