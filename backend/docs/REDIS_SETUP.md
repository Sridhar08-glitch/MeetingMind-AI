# Redis Setup (Windows, local dev)

MeetingMind uses Redis as the Celery **broker** and **result backend**. On Windows
we use **Memurai** (a drop-in Redis-compatible server) — verified running Redis
server v8.1 protocol.

## Install

- **Memurai (used here):** https://www.memurai.com/ — installs to
  `C:\Program Files\Memurai\`. (Docker `docker run -p 6379:6379 redis:7` or WSL2
  `sudo apt install redis-server` also work.)

## Start the server

Memurai installs a Windows service (`Memurai`, StartType=Automatic) but starting
the **service** needs admin. Without admin, run the binary directly:

```powershell
# Option A — service (needs admin):
Start-Service Memurai

# Option B — no admin (what we use): launch the binary detached
Start-Process -FilePath "C:\Program Files\Memurai\memurai.exe" `
  -ArgumentList '"C:\Program Files\Memurai\memurai.conf"' -WindowStyle Hidden
```

## Verify

```powershell
& "C:\Program Files\Memurai\memurai-cli.exe" ping          # -> PONG
Get-NetTCPConnection -LocalPort 6379 -State Listen         # -> LISTENING
curl http://127.0.0.1:8000/api/health/redis/               # -> {"status":"ok", ...}
```

## Configuration (`backend/.env`)

```dotenv
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

## Survives restart

The `Memurai` service is `Automatic`, so it starts on boot **once started by an
admin**. In the no-admin/direct-binary mode you must relaunch the binary after a
reboot (see the command above), or have an admin start the service once.

## Troubleshooting

- **`ping` fails / 6379 not listening:** the server isn't running — start it.
- **Django `health/redis` shows `degraded, eager mode`:** Redis unreachable *or*
  `CELERY_TASK_ALWAYS_EAGER=True`. Start Redis and set it to `False` (see
  [CELERY_SETUP.md](CELERY_SETUP.md)).
- **Port 6379 already in use:** another Redis/Memurai instance is running — reuse
  it or stop the other one.
