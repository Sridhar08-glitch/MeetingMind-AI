# MeetingMind AI — Production Readiness

An operational audit and go-live checklist for MeetingMind AI v1.0. Pair with
[DEPLOYMENT.md](DEPLOYMENT.md) (how to deploy) and [SECURITY.md](SECURITY.md) (security model).

Legend: ✅ ready · ⚙️ config required · 📋 operator action.

---

## 1. Configuration

| Item | Status | Notes |
|---|---|---|
| Env-driven config (`django-environ`) | ✅ | Everything configurable via `.env`; nothing hard-coded |
| `DEBUG` off in prod | ⚙️ | `DJANGO_DEBUG=False` |
| `ALLOWED_HOSTS` tightened | ⚙️ | Set to the real host(s) |
| CORS/CSRF origins pinned | ⚙️ | Set to the real frontend origin |
| Provider selection | ✅ | `AI_PROVIDER`/`STT_PROVIDER`/`EMBEDDING_PROVIDER` switches with safe fallbacks |

## 2. Secrets management

| Item | Status | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` from env | ⚙️ | Dev placeholder must be replaced with a real random secret |
| DB / Redis credentials from env | ⚙️ | Never commit; inject via env or a secrets manager |
| Cloud AI keys optional & blank by default | ✅ | `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` empty; not required |
| Reset tokens stored hashed | ✅ | Only SHA-256 of the token is persisted |

## 3. Health checks

| Item | Status | Notes |
|---|---|---|
| Liveness/readiness endpoints | ✅ | `/api/health/{,database,redis,storage,workers}` (no auth) |
| Component-level status | ✅ | DB returns 503 when down; workers report `worker` vs `eager` |
| 📋 Wire to monitor | 📋 | Poll `/api/health/` from your uptime monitor / load balancer |

## 4. Logging

| Item | Status | Notes |
|---|---|---|
| Structured module logging | ✅ | Split logging config; **0 `print()`** in app code |
| Pipeline/stage logs | ✅ | `JobLog` + `ProcessingLog` capture per-stage status/timing |
| Domain audit trails | ✅ | `MeetingEvent`, `KnowledgeEvent`, `ActivityLog`, run-step tables |
| 📋 Ship logs | 📋 | Forward stdout/worker logs to your aggregator; set level per env |

## 5. Monitoring

| Item | Status | Notes |
|---|---|---|
| Job metrics | ✅ | `/api/jobs/metrics/` (throughput, failures) + per-job `timeline` |
| Executive/observability metrics | ✅ | Run tables record latencies, retries, quality scores |
| 📋 Dashboards/alerts | 📋 | Build alerts on health-check failures, job failure rate, queue depth |

## 6. Backups

| Item | Status | Notes |
|---|---|---|
| DB backup procedure | 📋 | `pg_dump`; schedule + retain |
| Media backup procedure | 📋 | Back up `MEDIA_ROOT` **with** the DB (paired) |
| Backup verification | 📋 | Periodically restore to a scratch env |

## 7. Restore & disaster recovery

Documented, repeatable restore:
1. Provision empty PostgreSQL + `MEDIA_ROOT` volume.
2. `psql < latest.sql`; restore `media/` from the paired archive.
3. `manage.py migrate` (no-op if current); restart API + workers.
4. Verify `/api/health/` and run the smoke test ([TESTING.md](TESTING.md) §6).

**RPO/RTO** are set by your backup cadence — choose a schedule that matches your tolerance and
**test the restore**, since DB and media must be consistent with each other.

## 8. Temporary file cleanup

| Item | Status | Notes |
|---|---|---|
| Temp WAVs during extract/normalize | ✅ generated in temp dir | Created via `NamedTemporaryFile`; ensure the OS temp dir has space |
| 📋 Cleanup policy | 📋 | Schedule cleanup of orphaned temp files; monitor temp-dir usage |

## 9. Upload cleanup & retention

| Item | Status | Notes |
|---|---|---|
| Uploads versioned & private | ✅ | UUID names under `MEDIA_ROOT/private`; old versions retained |
| Soft delete | ✅ | Meetings/files soft-delete; `all_objects` exposes them |
| 📋 Retention/pruning | 📋 | Define a retention policy; hard-delete + purge media past retention |

## 10. Celery retry policy

| Item | Status | Notes |
|---|---|---|
| Per-stage retries with backoff | ✅ | Pipeline retries transient stage errors; non-retryable fail fast |
| `max_attempts` per job | ✅ | Default 3; `acks_late` + `reject_on_worker_lost` prevent loss |
| Time limits | ✅ | `CELERY_TASK_TIME_LIMIT=3600`, soft `3300` bound runaways |
| Manual recovery | ✅ | `POST /api/jobs/{id}/retry|requeue/` after inspecting logs |

## 11. Worker monitoring

| Item | Status | Notes |
|---|---|---|
| Worker health endpoint | ✅ | `/api/health/workers/` reports mode + count |
| Cooperative locks | ✅ | `locked_at`/`locked_by` prevent double-processing |
| 📋 Supervise workers | 📋 | Run under systemd/NSSM; alert if worker count drops or queue backs up |

## 12. Database migration strategy

| Item | Status | Notes |
|---|---|---|
| Per-app forward-only migrations | ✅ | Standard Django migrations |
| Deploy order | 📋 | Back up → `migrate` → restart; apply additive migrations before dependent code |
| No editing applied migrations | 📋 | Always add a new migration |

## 13. Dependency pinning

| Item | Status | Notes |
|---|---|---|
| Backend deps pinned | ✅ | `requirements.txt`/`requirements-stt.txt` pin exact versions |
| Frontend deps locked | ✅ | `package-lock.json`; use `npm ci` in CI/deploy |
| Python version fixed | ✅ | 3.12 only (Whisper wheel constraint) |
| 📋 Update cadence | 📋 | Periodically bump + re-run the test suite before promoting |

## 14. Release checklist

- [ ] Backend suite green: `CELERY_TASK_ALWAYS_EAGER=True pytest -q` (248 tests)
- [ ] Frontend gates green: `tsc --noEmit`, `eslint`, `next build`
- [ ] Migrations generated + reviewed
- [ ] `.env` set for the target environment (secrets, hosts, origins, providers)
- [ ] Real smoke test passes on a staging box
- [ ] `CHANGELOG.md` / `RELEASE_NOTES_*` updated

## 15. Operational checklist (daily/weekly)

- [ ] Health checks green (DB, redis, storage, workers)
- [ ] Job failure rate within threshold; retry/requeue stuck jobs
- [ ] Queue depth not growing unbounded
- [ ] Disk headroom for media + temp + Whisper model cache
- [ ] Backups succeeded (and a recent restore was tested)

## 16. Known production considerations

- **AI hardware:** CPU Ollama/Whisper are fine for modest volume; GPU is the biggest throughput
  lever for larger models or higher concurrency.
- **LLM endpoint throttling:** add per-endpoint throttles to agent/planner/collaboration run
  endpoints to prevent local resource exhaustion.
- **Single-node vs. scaled:** the app is stateless behind the DB + broker + media volume; scale by
  adding app servers and workers pointed at the same PostgreSQL/Redis/media.
- **Verification pedigree:** v1.0 was built and certified against the **real** local stack
  (real Faster-Whisper, Ollama, Celery worker) — not mocks — end to end.

---

See also: [DEPLOYMENT.md](DEPLOYMENT.md) · [SECURITY.md](SECURITY.md) ·
[PERFORMANCE.md](PERFORMANCE.md) · [ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md).
